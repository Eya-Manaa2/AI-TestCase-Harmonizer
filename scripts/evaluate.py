from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from harmonizer.analyzer import analyze_cases
from harmonizer.io import load_cases

REDUNDANT_DECISIONS = {"duplicate", "equivalent"}
NEGATIVE_DECISIONS = {"related", "different"}
LEGACY_DECISIONS = {
    "related_not_equivalent": "related",
    "not_related": "different",
    "insufficient_information": "uncertain",
}


def normalize_decision(value: str) -> str:
    normalized = value.strip().casefold().replace(" ", "_")
    return LEGACY_DECISIONS.get(normalized, normalized)


def parse_thresholds(value: str) -> list[float]:
    try:
        thresholds = [float(item.strip()) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Les seuils doivent être des nombres séparés par des virgules.") from exc
    if not thresholds or any(not 0 <= threshold <= 1 for threshold in thresholds):
        raise argparse.ArgumentTypeError("Chaque seuil doit être compris entre 0 et 1.")
    return sorted(set(thresholds))


def get_labels(cases: list[dict[str, Any]], label_column: str) -> list[str]:
    labels = []
    for case in cases:
        label = case["raw"].get(label_column)
        if label is None or not str(label).strip():
            raise ValueError(f"Annotation absente dans la colonne '{label_column}' pour {case['id']}.")
        labels.append(str(label).strip())
    return labels


def evaluate_thresholds(
    cases: list[dict[str, Any]],
    labels: list[str],
    thresholds: list[float],
    embedding_model: Any | None = None,
) -> list[dict[str, Any]]:
    all_pairs = set(combinations(range(len(cases)), 2))
    actual = {
        pair
        for pair in all_pairs
        if labels[pair[0]] == labels[pair[1]] and labels[pair[0]].casefold() not in {"unique", "none"}
    }
    results = []
    for threshold in thresholds:
        analysis = analyze_cases(cases, threshold, embedding_model=embedding_model)
        predicted = {(pair["left"], pair["right"]) for pair in analysis["pairs"]}
        true_positive = len(predicted & actual)
        precision = true_positive / len(predicted) if predicted else 0.0
        recall = true_positive / len(actual) if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results.append(
            {
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "predicted_pairs": len(predicted),
                "actual_equivalent_pairs": len(actual),
                "true_positive": true_positive,
                "false_positive": len(predicted - actual),
                "false_negative": len(actual - predicted),
            }
        )
    return results


def evaluate_pair_annotations(
    cases: list[dict[str, Any]],
    annotations: pd.DataFrame,
    thresholds: list[float],
    embedding_model: Any | None = None,
) -> list[dict[str, Any]]:
    case_indices = {case["id"]: index for index, case in enumerate(cases)}
    required = {"case_id_a", "case_id_b", "decision"}
    decision_column = (
        "adjudicated_decision"
        if "adjudicated_decision" in annotations.columns
        else "decision"
    )
    required.discard("decision")
    required.add(decision_column)
    if not required.issubset(annotations.columns):
        raise ValueError(f"Le fichier d’annotations doit contenir : {', '.join(sorted(required))}.")

    labels: dict[tuple[int, int], bool] = {}
    decision_counts: Counter[str] = Counter()
    seen_pairs: set[tuple[int, int]] = set()
    unresolved_pairs = 0
    insufficient_pairs = 0
    for row_number, row in enumerate(annotations.to_dict(orient="records"), start=2):
        id_a, id_b = str(row["case_id_a"]).strip(), str(row["case_id_b"]).strip()
        if not id_a or not id_b or id_a.casefold() == "nan" or id_b.casefold() == "nan":
            raise ValueError(f"Identifiant manquant dans la ligne {row_number} des annotations.")
        if id_a not in case_indices or id_b not in case_indices:
            raise ValueError(f"Paire annotée inconnue : {id_a}, {id_b}.")
        left, right = sorted((case_indices[id_a], case_indices[id_b]))
        if left == right:
            raise ValueError(f"Une paire doit contenir deux cas différents : {id_a}.")
        pair = (left, right)
        if pair in seen_pairs:
            raise ValueError(f"Paire présente plusieurs fois : {id_a}, {id_b}.")
        seen_pairs.add(pair)
        raw_decision = row[decision_column]
        if pd.isna(raw_decision) or not str(raw_decision).strip():
            unresolved_pairs += 1
            continue
        decision = normalize_decision(str(raw_decision))
        if decision == "uncertain":
            insufficient_pairs += 1
            continue
        if decision not in REDUNDANT_DECISIONS | NEGATIVE_DECISIONS:
            raise ValueError(f"Décision d’annotation non reconnue : {decision}.")
        decision_counts[decision] += 1
        labels[pair] = decision in REDUNDANT_DECISIONS
    if not labels:
        if unresolved_pairs or insufficient_pairs:
            return [
                {
                    "threshold": threshold,
                    "precision": None,
                    "recall": None,
                    "f1": None,
                    "annotated_pairs": 0,
                    "unresolved_pairs": unresolved_pairs,
                    "uncertain_pairs": insufficient_pairs,
                    "insufficient_information_pairs": insufficient_pairs,
                    "duplicate_pairs": decision_counts["duplicate"],
                    "equivalent_pairs": decision_counts["equivalent"],
                    "related_pairs": decision_counts["related"],
                    "different_pairs": decision_counts["different"],
                    "true_positive": 0,
                    "false_positive": 0,
                    "false_negative": 0,
                    "true_negative": 0,
                }
                for threshold in thresholds
            ]
        raise ValueError("Aucune paire annotée exploitable dans le jeu.")

    result_rows = []
    for threshold in thresholds:
        analysis = analyze_cases(cases, threshold, embedding_model=embedding_model)
        predicted = {(pair["left"], pair["right"]) for pair in analysis["pairs"]}
        true_positive = sum(labels[pair] and pair in predicted for pair in labels)
        false_positive = sum(not labels[pair] and pair in predicted for pair in labels)
        false_negative = sum(labels[pair] and pair not in predicted for pair in labels)
        true_negative = sum(not labels[pair] and pair not in predicted for pair in labels)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result_rows.append(
            {
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "annotated_pairs": len(labels),
                "unresolved_pairs": unresolved_pairs,
                "uncertain_pairs": insufficient_pairs,
                "insufficient_information_pairs": insufficient_pairs,
                "duplicate_pairs": decision_counts["duplicate"],
                "equivalent_pairs": decision_counts["equivalent"],
                "related_pairs": decision_counts["related"],
                "different_pairs": decision_counts["different"],
                "true_positive": true_positive,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "true_negative": true_negative,
            }
        )
    return result_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Évalue les paires détectées contre les annotations humaines.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "sample_test_cases.csv",
        help="CSV/JSON/TXT/XLSX annoté (défaut : jeu synthétique fourni).",
    )
    parser.add_argument("--label-column", default="equivalence_group")
    parser.add_argument(
        "--pair-annotations",
        type=Path,
        help="CSV généré par prepare_annotations.py avec adjudicated_decision renseigné.",
    )
    parser.add_argument("--thresholds", type=parse_thresholds, default=parse_thresholds("0.20,0.30,0.40,0.50,0.60,0.70,0.80"))
    parser.add_argument("--engine", choices=("tfidf", "sentence-transformers"), default="tfidf")
    parser.add_argument(
        "--embedding-model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    parser.add_argument("--output", type=Path, help="Fichier CSV de résultats optionnel.")
    args = parser.parse_args()

    cases = load_cases(args.dataset.read_bytes(), args.dataset.name)
    embedding_model = None
    if args.engine == "sentence-transformers":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise SystemExit(
                "Sentence Transformers n’est pas installé. "
                "Installez requirements-embeddings.txt."
            ) from exc
        embedding_model = SentenceTransformer(args.embedding_model)

    if args.pair_annotations:
        annotations = pd.read_csv(args.pair_annotations)
        results = evaluate_pair_annotations(
            cases, annotations, args.thresholds, embedding_model
        )
        annotation_description = f"Annotations paire-à-paire : {args.pair_annotations}"
    else:
        labels = get_labels(cases, args.label_column)
        results = evaluate_thresholds(cases, labels, args.thresholds, embedding_model)
        annotation_description = f"Familles annotées : {len(set(labels))}"
    frame = pd.DataFrame(results)
    print(f"Dataset: {args.dataset}")
    print(f"Cas: {len(cases)} | Moteur: {args.engine} | {annotation_description}")
    print(frame.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"Résultats sauvegardés dans : {args.output}")
    print("Note : régler un seuil sur ces résultats ne constitue pas une évaluation indépendante.")


if __name__ == "__main__":
    main()
