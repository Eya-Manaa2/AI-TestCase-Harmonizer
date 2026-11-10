from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any
import unicodedata
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from harmonizer.io import load_cases


def normalized_text_key(case: dict[str, Any]) -> str:
    parts = []
    for field in ("title", "preconditions", "steps", "expected_result"):
        value = unicodedata.normalize("NFKC", str(case.get(field, ""))).casefold()
        parts.append(" ".join(re.findall(r"\w+", value)))
    return "\n".join(parts)


def profile_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[normalized_text_key(case)].append(case)
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    return {
        "case_count": len(cases),
        "unique_normalized_cases": len(groups),
        "duplicate_groups": duplicate_groups,
        "duplicate_pairs": sum(len(group) * (len(group) - 1) // 2 for group in duplicate_groups),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Profile le contenu et les répétitions textuelles exactes d’un référentiel."
    )
    parser.add_argument("--dataset", required=True, type=Path)
    args = parser.parse_args()
    cases = load_cases(args.dataset.read_bytes(), args.dataset.name)
    result = profile_cases(cases)
    print(f"Cas importés : {result['case_count']}")
    print(f"Cas textuellement distincts après normalisation : {result['unique_normalized_cases']}")
    print(f"Groupes de répétitions exactes : {len(result['duplicate_groups'])}")
    print(f"Paires dans ces groupes : {result['duplicate_pairs']}")
    print("Ces répétitions sont des doublons de contenu normalisé, pas une annotation d’équivalence fonctionnelle.")
    for group in result["duplicate_groups"]:
        print(
            ", ".join(case["id"] for case in group),
            "|",
            group[0]["title"].replace("\n", " ")[:100],
        )


if __name__ == "__main__":
    main()
