from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path
import random
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from harmonizer.analyzer import analyze_cases
from harmonizer.io import load_cases
from scripts.prepare_annotations import (
    CASE_COLUMNS,
    build_annotation_rows,
    write_rows,
)


def build_batches(
    cases: list[dict[str, Any]],
    *,
    pilot_size: int = 20,
    batch_size: int = 100,
    seed: int = 42,
) -> list[tuple[str, list[dict[str, str]]]]:
    if pilot_size < 0 or batch_size < 1:
        raise ValueError("pilot_size doit être positif et batch_size doit être supérieur à zéro.")
    rows = build_annotation_rows(cases)
    if pilot_size > len(rows):
        raise ValueError(f"Le pilote demande {pilot_size} paires, mais seulement {len(rows)} existent.")
    if pilot_size == 0:
        remaining = rows
        batches = []
    else:
        similarities = analyze_cases(cases, threshold=0.0)["similarity"]
        pairs = list(combinations(range(len(cases)), 2))
        pair_indices = {pair: index for index, pair in enumerate(pairs)}
        ranked_pairs = sorted(
            pairs,
            key=lambda pair: (-float(similarities[pair[0], pair[1]]), pair),
        )
        high_count = pilot_size // 2
        selected_pairs = set(ranked_pairs[:high_count])
        low_ranked = ranked_pairs[high_count:]
        low_candidates = low_ranked[-min(len(low_ranked), max(pilot_size, high_count)):]
        randomizer = random.Random(seed)
        low_count = pilot_size - len(selected_pairs)
        selected_pairs.update(randomizer.sample(low_candidates, low_count))
        selected_row_numbers = {pair_indices[pair] for pair in selected_pairs}
        pilot = [row for index, row in enumerate(rows) if index in selected_row_numbers]
        remaining = [row for index, row in enumerate(rows) if index not in selected_row_numbers]
        batches = [("pilot", pilot)]
    for batch_number, start in enumerate(range(0, len(remaining), batch_size), start=1):
        batches.append(
            (f"batch_{batch_number:03d}", remaining[start : start + batch_size])
        )
    return batches


def _blind_outputs(
    rows: list[dict[str, str]], output_dir: Path, batch_name: str
) -> dict[Path, tuple[list[str], list[dict[str, str]]]]:
    stem = f"{batch_name}"
    return {
        output_dir / f"{stem}_annotator_1.csv": (
            CASE_COLUMNS + ["annotator_1_decision", "annotator_1_rationale"],
            [
                {key: value for key, value in row.items() if key in CASE_COLUMNS}
                for row in rows
            ],
        ),
        output_dir / f"{stem}_annotator_2.csv": (
            CASE_COLUMNS + ["annotator_2_decision", "annotator_2_rationale"],
            [
                {key: value for key, value in row.items() if key in CASE_COLUMNS}
                for row in rows
            ],
        ),
        output_dir / f"{stem}_adjudication.csv": (
            [
                "pair_id",
                "case_id_a",
                "case_id_b",
                "adjudicated_decision",
                "adjudicator_rationale",
            ],
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crée un pilote enrichi et des lots aveugles de paires identiques pour les annotateurs."
    )
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--pilot-size", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        cases = load_cases(args.dataset.read_bytes(), args.dataset.name)
        batches = build_batches(
            cases,
            pilot_size=args.pilot_size,
            batch_size=args.batch_size,
            seed=args.seed,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    output_files = {
        path: content
        for batch_name, rows in batches
        for path, content in _blind_outputs(rows, args.output_dir, batch_name).items()
    }
    existing = [path for path in output_files if path.exists()]
    if existing and not args.overwrite:
        parser.error(
            f"Fichier(s) déjà présent(s) : {', '.join(map(str, existing))}. "
            "Utilisez --overwrite pour les remplacer."
        )
    for path, (columns, rows) in output_files.items():
        write_rows(path, columns, rows)

    print(f"{len(cases)} cas ; {sum(len(rows) for _, rows in batches)} paires réparties.")
    print(f"Pilote : {args.pilot_size} paires (à exclure des métriques finales).")
    print(f"Lots restants : {len(batches) - (1 if args.pilot_size else 0)} de maximum {args.batch_size} paires.")
    print(f"Fichiers créés dans : {args.output_dir}")
    print("Ne communiquez pas aux annotateurs la sélection des paires ni les scores du modèle.")


if __name__ == "__main__":
    main()
