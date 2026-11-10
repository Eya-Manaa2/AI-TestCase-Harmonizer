from __future__ import annotations

import argparse
import csv
from itertools import combinations
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from harmonizer.io import load_cases

MAX_CASES = 200
OUTPUT_COLUMNS = [
    "pair_id",
    "case_id_a",
    "title_a",
    "preconditions_a",
    "steps_a",
    "expected_result_a",
    "case_id_b",
    "title_b",
    "preconditions_b",
    "steps_b",
    "expected_result_b",
    "annotator_1_decision",
    "annotator_1_rationale",
    "annotator_2_decision",
    "annotator_2_rationale",
    "adjudicated_decision",
    "adjudicator_rationale",
]
CASE_COLUMNS = [
    "pair_id",
    "case_id_a",
    "title_a",
    "preconditions_a",
    "steps_a",
    "expected_result_a",
    "case_id_b",
    "title_b",
    "preconditions_b",
    "steps_b",
    "expected_result_b",
]


def build_annotation_rows(cases: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for pair_number, (left, right) in enumerate(combinations(cases, 2), start=1):
        row = {column: "" for column in OUTPUT_COLUMNS}
        row["pair_id"] = f"PAIR-{pair_number:05d}"
        for suffix, case in (("a", left), ("b", right)):
            for field in ("id", "title", "preconditions", "steps", "expected_result"):
                column = "case_id" if field == "id" else field
                row[f"{column}_{suffix}"] = case[field]
        rows.append(row)
    return rows


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prépare une feuille de paires à annoter indépendamment par deux testeurs. "
            "Décisions : duplicate, equivalent, related, different, uncertain."
        )
    )
    parser.add_argument("--dataset", required=True, type=Path, help="Référentiel anonymisé CSV, JSON, TXT ou XLSX.")
    parser.add_argument("--output", required=True, type=Path, help="Fichier CSV de paires à produire.")
    parser.add_argument("--overwrite", action="store_true", help="Autorise le remplacement d’un fichier existant.")
    parser.add_argument(
        "--blind",
        action="store_true",
        help="Crée deux feuilles séparées pour annotateurs et un modèle d’arbitrage.",
    )
    args = parser.parse_args()

    cases = load_cases(args.dataset.read_bytes(), args.dataset.name)
    if len(cases) > MAX_CASES:
        parser.error(
            f"{len(cases)} cas produiraient trop de paires. "
            f"Réduisez le dataset à {MAX_CASES} cas maximum ou préparez des lots."
        )
    rows = build_annotation_rows(cases)
    if args.blind:
        outputs = {
            args.output.with_name(f"{args.output.stem}_annotator_1{args.output.suffix}"): (
                CASE_COLUMNS + ["annotator_1_decision", "annotator_1_rationale"],
                [
                    {key: value for key, value in row.items() if key in CASE_COLUMNS}
                    for row in rows
                ],
            ),
            args.output.with_name(f"{args.output.stem}_annotator_2{args.output.suffix}"): (
                CASE_COLUMNS + ["annotator_2_decision", "annotator_2_rationale"],
                [
                    {key: value for key, value in row.items() if key in CASE_COLUMNS}
                    for row in rows
                ],
            ),
            args.output.with_name(f"{args.output.stem}_adjudication{args.output.suffix}"): (
                ["pair_id", "case_id_a", "case_id_b", "adjudicated_decision", "adjudicator_rationale"],
                [
                    {
                        "pair_id": row["pair_id"],
                        "case_id_a": row["case_id_a"],
                        "case_id_b": row["case_id_b"],
                    }
                    for row in rows
                ],
            ),
        }
        existing = [path for path in outputs if path.exists()]
        if existing and not args.overwrite:
            parser.error(
                f"Fichier(s) déjà présent(s) : {', '.join(map(str, existing))}. "
                "Utilisez --overwrite pour les remplacer."
            )
        for path, (columns, file_rows) in outputs.items():
            write_rows(path, columns, file_rows)
        print(f"{len(cases)} cas ; {len(rows)} paires par annotateur.")
        print("Fichiers créés :")
        for path in outputs:
            print(f"  {path}")
        print("Ne partagez pas les feuilles d’annotation entre testeurs avant leur remise.")
    else:
        if args.output.exists() and not args.overwrite:
            parser.error(f"{args.output} existe déjà ; utilisez --overwrite pour le remplacer.")
        write_rows(args.output, OUTPUT_COLUMNS, rows)
        print(f"{len(cases)} cas ; {len(rows)} paires créées dans {args.output}")
        print("Pour une annotation aveugle, préférez l’option --blind.")


if __name__ == "__main__":
    main()
