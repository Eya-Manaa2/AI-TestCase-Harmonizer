from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

DECISIONS = (
    "duplicate",
    "equivalent",
    "related",
    "different",
    "uncertain",
)
LEGACY_DECISIONS = {
    "related_not_equivalent": "related",
    "not_related": "different",
    "insufficient_information": "uncertain",
}


def normalize_decision(value: str) -> str:
    normalized = value.strip().casefold().replace(" ", "_")
    return LEGACY_DECISIONS.get(normalized, normalized)


def cohen_kappa(
    left: list[str], right: list[str], categories: tuple[str, ...] = DECISIONS
) -> float | None:
    left = [normalize_decision(value) for value in left]
    right = [normalize_decision(value) for value in right]
    if len(left) != len(right):
        raise ValueError("Les deux listes d’annotations doivent avoir la même longueur.")
    if not left:
        return None
    if any(value not in categories for value in left + right):
        raise ValueError("Une annotation contient une décision non reconnue.")
    count = len(left)
    observed_agreement = sum(a == b for a, b in zip(left, right)) / count
    left_counts = {category: left.count(category) for category in categories}
    right_counts = {category: right.count(category) for category in categories}
    expected_agreement = sum(
        left_counts[category] * right_counts[category] for category in categories
    ) / (count * count)
    if expected_agreement == 1:
        return None
    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def summarize_annotations(frame: pd.DataFrame) -> dict[str, Any]:
    required = {"annotator_1_decision", "annotator_2_decision"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Colonnes requises : {', '.join(sorted(required))}.")
    normalized = frame.copy()
    for column in required:
        normalized[column] = normalized[column].astype("string").fillna("").map(
            normalize_decision
        )
    has_both = normalized["annotator_1_decision"].ne("") & normalized[
        "annotator_2_decision"
    ].ne("")
    valid_mask = normalized["annotator_1_decision"].isin(DECISIONS) & normalized[
        "annotator_2_decision"
    ].isin(DECISIONS)
    invalid_count = int((has_both & ~valid_mask).sum())
    complete = normalized[has_both & valid_mask]
    left = complete["annotator_1_decision"].tolist()
    right = complete["annotator_2_decision"].tolist()
    agreement_count = sum(a == b for a, b in zip(left, right))
    kappa = cohen_kappa(left, right)
    result: dict[str, Any] = {
        "total_pairs": len(frame),
        "double_annotated_pairs": len(complete),
        "incomplete_pairs": int((~has_both).sum()),
        "invalid_decisions": invalid_count,
        "raw_agreement": agreement_count / len(complete) if len(complete) else None,
        "cohen_kappa": kappa,
        "decision_counts_annotator_1": complete["annotator_1_decision"].value_counts().to_dict(),
        "decision_counts_annotator_2": complete["annotator_2_decision"].value_counts().to_dict(),
    }
    if "adjudicated_decision" in frame.columns:
        adjudicated = (
            frame["adjudicated_decision"]
            .astype("string")
            .fillna("")
            .map(normalize_decision)
        )
        result["adjudicated_pairs"] = int(adjudicated.isin(DECISIONS).sum())
        disagreements = complete["annotator_1_decision"] != complete["annotator_2_decision"]
        result["disagreements"] = int(disagreements.sum())
        result["unresolved_disagreements"] = int(
            (
                disagreements
                & normalized.loc[complete.index, "adjudicated_decision"].fillna("").eq("")
            ).sum()
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calcule l’accord inter-annotateurs avant arbitrage."
    )
    parser.add_argument("--annotations", required=True, type=Path)
    args = parser.parse_args()
    result = summarize_annotations(pd.read_csv(args.annotations))
    print(f"Paires dans la feuille : {result['total_pairs']}")
    print(f"Paires annotées par les deux testeurs : {result['double_annotated_pairs']}")
    print(f"Paires incomplètes : {result['incomplete_pairs']}")
    print(f"Décisions invalides : {result['invalid_decisions']}")
    if result["raw_agreement"] is None:
        print("Accord brut : non calculable (pas de paires doublement annotées)")
    else:
        print(f"Accord brut : {result['raw_agreement']:.3f}")
    if result["cohen_kappa"] is None:
        print("Cohen kappa : non calculable (accord attendu égal à 1 ou aucun échantillon)")
    else:
        print(f"Cohen kappa : {result['cohen_kappa']:.3f}")
    if "adjudicated_pairs" in result:
        print(f"Paires arbitrées : {result['adjudicated_pairs']}")
        print(f"Désaccords non arbitrés : {result['unresolved_disagreements']}")


if __name__ == "__main__":
    main()
