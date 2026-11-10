from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.prepare_annotations import OUTPUT_COLUMNS

DECISION_ALIASES = {
    "related_not_equivalent": "related",
    "not_related": "different",
    "insufficient_information": "uncertain",
}
VALID_DECISIONS = {"duplicate", "equivalent", "related", "different", "uncertain"}


def merge_annotation_sheets(
    annotator_1: pd.DataFrame,
    annotator_2: pd.DataFrame,
    adjudication: pd.DataFrame,
) -> pd.DataFrame:
    sheets = {
        "annotator 1": annotator_1,
        "annotator 2": annotator_2,
        "adjudication": adjudication,
    }
    key_columns = ["pair_id", "case_id_a", "case_id_b"]
    required_columns = {
        "annotator 1": {"annotator_1_decision", "annotator_1_rationale"},
        "annotator 2": {"annotator_2_decision", "annotator_2_rationale"},
        "adjudication": {"adjudicated_decision", "adjudicator_rationale"},
    }
    for name, sheet in sheets.items():
        missing = (set(key_columns) | required_columns[name]) - set(sheet.columns)
        if missing:
            raise ValueError(f"Colonnes d’identification manquantes ({name}) : {', '.join(sorted(missing))}.")
        if sheet["pair_id"].duplicated().any():
            raise ValueError(f"Identifiant de paire dupliqué dans la feuille {name}.")

    base = annotator_1.merge(
        annotator_2,
        on=key_columns,
        how="outer",
        suffixes=("", "_duplicate"),
        validate="one_to_one",
        indicator="_annotator_merge",
    )
    if not base["_annotator_merge"].eq("both").all():
        raise ValueError("Les feuilles des deux annotateurs ne contiennent pas le même ensemble de paires.")
    base = base.drop(columns="_annotator_merge")
    for column in ("title_a", "preconditions_a", "steps_a", "expected_result_a",
                   "title_b", "preconditions_b", "steps_b", "expected_result_b"):
        duplicate_column = f"{column}_duplicate"
        if duplicate_column in base.columns:
            if not base[column].fillna("").eq(base[duplicate_column].fillna("")).all():
                raise ValueError(f"Le contexte de cas diffère entre feuilles : {column}.")
            base = base.drop(columns=duplicate_column)

    base = base.merge(
        adjudication[
            key_columns + ["adjudicated_decision", "adjudicator_rationale"]
        ],
        on=key_columns,
        how="outer",
        validate="one_to_one",
        indicator="_adjudication_merge",
    )
    if not base["_adjudication_merge"].eq("both").all():
        raise ValueError("La feuille d’arbitrage ne contient pas le même ensemble de paires.")
    base = base.drop(columns="_adjudication_merge")
    for index, row in base.iterrows():
        decision_1 = _normalize_decision(row["annotator_1_decision"])
        decision_2 = _normalize_decision(row["annotator_2_decision"])
        adjudicated = _normalize_decision(row["adjudicated_decision"])
        if (
            not adjudicated
            and decision_1 in VALID_DECISIONS
            and decision_1 == decision_2
        ):
            base.at[index, "adjudicated_decision"] = decision_1
    for column in OUTPUT_COLUMNS:
        if column not in base:
            base[column] = ""
    return base[OUTPUT_COLUMNS]


def _normalize_decision(value: object) -> str:
    normalized = str(value).strip().casefold().replace(" ", "_")
    return DECISION_ALIASES.get(normalized, normalized)


def read_annotation_files(paths: list[Path]) -> pd.DataFrame:
    if not paths:
        raise ValueError("Indiquez au moins une feuille d’annotation.")
    frames = [
        pd.read_csv(path, dtype="string", keep_default_na=False)
        for path in paths
    ]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fusionne les feuilles remplies après annotations indépendantes."
    )
    parser.add_argument("--annotator-1", required=True, type=Path, nargs="+")
    parser.add_argument("--annotator-2", required=True, type=Path, nargs="+")
    parser.add_argument("--adjudication", required=True, type=Path, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.overwrite:
        parser.error(f"{args.output} existe déjà ; utilisez --overwrite pour le remplacer.")
    try:
        merged = merge_annotation_sheets(
            read_annotation_files(args.annotator_1),
            read_annotation_files(args.annotator_2),
            read_annotation_files(args.adjudication),
        )
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"{len(merged)} paires fusionnées dans {args.output}")


if __name__ == "__main__":
    main()
