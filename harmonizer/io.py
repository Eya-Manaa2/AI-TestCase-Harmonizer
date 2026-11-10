from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

ALIASES = {
    "id": ("id", "test_id", "test_case_id", "case_id", "case no.", "case no"),
    "title": ("title", "name", "test_name", "test_case", "test cases", "summary"),
    "preconditions": ("preconditions", "precondition", "setup", "precondition_steps"),
    "steps": ("steps", "test_steps", "test steps", "procedure", "actions", "description"),
    "expected_result": (
        "expected_result",
        "expected",
        "expected_results",
        "expected_output",
        "expected output",
    ),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def records_to_cases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        normalized = {str(key).strip().lower(): value for key, value in record.items()}
        case: dict[str, Any] = {}
        for field, names in ALIASES.items():
            if field == "steps" and any(
                name in normalized
                for name in ("steps", "test_steps", "test steps", "procedure", "actions")
            ):
                names = tuple(name for name in names if name != "description")
            case[field] = next(
                (_text(normalized[name]) for name in names if name in normalized and _text(normalized[name])),
                "",
            )
        if not case["title"] and case["steps"]:
            first_step = next((line.strip() for line in case["steps"].splitlines() if line.strip()), "")
            case["title"] = first_step[:100]
        if not case["title"]:
            continue
        if not case["steps"]:
            case["steps"] = case["title"]
        case["id"] = case["id"] or f"TC-{index:03d}"
        if case["id"] in used_ids:
            raise ValueError(f"Identifiant de test dupliqué : {case['id']}")
        used_ids.add(case["id"])
        case["raw"] = record
        cases.append(case)
    return cases


def load_cases(content: bytes, filename: str) -> list[dict[str, Any]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = content.decode("utf-8-sig")
        records = list(csv.DictReader(io.StringIO(text)))
        if not records:
            raise ValueError("Le CSV doit contenir une ligne d’en-tête et au moins un cas.")
    elif suffix == ".json":
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("test_cases", data.get("cases", [data]))
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("Le JSON doit être une liste d’objets ou contenir une clé 'test_cases'.")
        records = data
    elif suffix == ".txt":
        text = content.decode("utf-8-sig")
        records = [
            {"title": line.strip(), "steps": line.strip()}
            for line in text.splitlines()
            if line.strip()
        ]
    elif suffix == ".xlsx":
        try:
            import pandas as pd
        except ImportError as exc:
            raise ValueError("L’import Excel nécessite pandas et openpyxl.") from exc
        try:
            with pd.ExcelFile(io.BytesIO(content)) as workbook:
                records = []
                for sheet_name in workbook.sheet_names:
                    preview = pd.read_excel(
                        workbook, sheet_name=sheet_name, header=None, nrows=20
                    )
                    header_row = next(
                        (
                            row_index
                            for row_index, row in preview.iterrows()
                            if {"test cases", "test steps", "expected output"}.issubset(
                                {
                                    str(value).strip().casefold()
                                    for value in row
                                    if pd.notna(value)
                                }
                            )
                        ),
                        None,
                    )
                    if header_row is None:
                        continue
                    frame = pd.read_excel(
                        workbook, sheet_name=sheet_name, header=header_row
                    )
                    frame = frame.astype(object).where(pd.notna(frame), "")
                    description_column = next(
                        (
                            column
                            for column in frame.columns
                            if str(column).strip().casefold() == "description"
                        ),
                        None,
                    )
                    if description_column is not None:
                        frame = frame[
                            frame[description_column].astype(str).str.strip().str.casefold()
                            != "header"
                        ]
                    records = frame.to_dict(orient="records")
                    if records:
                        break
                if not records:
                    frame = pd.read_excel(
                        workbook, sheet_name=workbook.sheet_names[0]
                    )
                    records = (
                        frame.astype(object)
                        .where(pd.notna(frame), "")
                        .to_dict(orient="records")
                    )
        except ImportError as exc:
            raise ValueError("L’import Excel nécessite openpyxl. Installez les dépendances du projet.") from exc
        except (BadZipFile, OSError, ValueError) as exc:
            raise ValueError(f"Classeur Excel invalide ou illisible : {exc}") from exc
    else:
        raise ValueError(f"Format non pris en charge : {suffix or 'inconnu'}")

    cases = records_to_cases(records)
    if not cases:
        raise ValueError("Aucun cas exploitable : chaque ligne doit contenir un titre ou des étapes.")
    return cases
