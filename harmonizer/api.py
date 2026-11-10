from __future__ import annotations

from functools import lru_cache
from importlib.util import find_spec
from io import BytesIO, StringIO
import csv
import json
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from harmonizer.analyzer import analyze_cases
from harmonizer.io import records_to_cases
from harmonizer.readiness import assess_readiness
from harmonizer.standardizer import discover_keywords, standardize_case

MAX_CASES = 1000
MAX_CASE_TEXT_LENGTH = 20_000

app = FastAPI(
    title="AI Test Case Harmonizer API",
    description="API locale d’analyse et d’harmonisation de référentiels de tests.",
    version="1.0.0",
)


class AnalysisRequest(BaseModel):
    cases: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_CASES)
    threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    engine: Literal["tfidf", "sentence-transformers"] = "tfidf"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class StandardizationRequest(BaseModel):
    cases: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_CASES)


class ExportRequest(BaseModel):
    cases: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_CASES)
    format: Literal["json", "csv", "xlsx"] = "json"


def _normalize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        cases = records_to_cases(records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not cases:
        raise HTTPException(status_code=422, detail="Aucun cas exploitable dans la requête.")
    for case in cases:
        if any(len(str(case.get(field, ""))) > MAX_CASE_TEXT_LENGTH for field in (
            "title", "preconditions", "steps", "expected_result"
        )):
            raise HTTPException(
                status_code=413,
                detail=f"Le texte d’un cas dépasse {MAX_CASE_TEXT_LENGTH} caractères.",
            )
    return cases


@lru_cache(maxsize=2)
def _load_embedding_model(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
def analyze(request: AnalysisRequest) -> dict[str, Any]:
    cases = _normalize(request.cases)
    embedding_model = None
    if request.engine == "sentence-transformers":
        if find_spec("sentence_transformers") is None:
            raise HTTPException(
                status_code=503,
                detail="Installez requirements-embeddings.txt pour activer Sentence Transformers.",
            )
        try:
            embedding_model = _load_embedding_model(request.embedding_model)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=503, detail=f"Impossible de charger le modèle d’embeddings : {exc}"
            ) from exc

    result = analyze_cases(cases, request.threshold, embedding_model=embedding_model)
    pairs = [
        {
            "left_id": cases[pair["left"]]["id"],
            "right_id": cases[pair["right"]]["id"],
            "similarity": pair["score"],
            "exact_duplicate": pair["exact"],
        }
        for pair in result["pairs"]
    ]
    return {
        "engine": request.engine,
        "threshold": request.threshold,
        "case_count": len(cases),
        "pairs": pairs,
        "clusters": [[cases[index]["id"] for index in group] for group in result["clusters"]],
        "readiness": [
            {"id": case["id"], **assess_readiness(case)} for case in cases
        ],
        "keywords": discover_keywords(cases),
        "standardizations": [
            {"id": case["id"], **standardize_case(case)} for case in cases
        ],
    }


@app.post("/standardize")
def standardize(request: StandardizationRequest) -> dict[str, Any]:
    cases = _normalize(request.cases)
    return {
        "cases": [
            {
                "id": case["id"],
                "title": case["title"],
                "preconditions": case["preconditions"],
                **standardize_case(case),
                "expected_result": case["expected_result"],
                "approved": False,
            }
            for case in cases
        ]
    }


@app.post("/export")
def export(request: ExportRequest) -> Response:
    if not request.cases:
        raise HTTPException(status_code=422, detail="Aucun cas à exporter.")
    if len(request.cases) > MAX_CASES:
        raise HTTPException(status_code=422, detail=f"Maximum {MAX_CASES} cas par export.")
    if any(case.get("approved") is not True for case in request.cases):
        raise HTTPException(
            status_code=422,
            detail="L’export est réservé aux cas explicitement approuvés par un humain.",
        )
    if request.format == "json":
        content = json.dumps(request.cases, ensure_ascii=False, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="standardized_test_cases.json"'},
        )
    if request.format == "csv":
        output = StringIO(newline="")
        fieldnames = list(dict.fromkeys(key for case in request.cases for key in case))
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(request.cases)
        return Response(
            content="\ufeff" + output.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="standardized_test_cases.csv"'},
        )
    buffer = BytesIO()
    pd.DataFrame(request.cases).to_excel(buffer, index=False)
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="standardized_test_cases.xlsx"'},
    )
