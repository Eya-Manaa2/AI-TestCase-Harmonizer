from __future__ import annotations

import re
from typing import Any

ACTION_PATTERNS = [
    ("NAVIGATE", re.compile(r"\b(open|go to|navigate|visit)\b", re.I)),
    ("INPUT", re.compile(r"\b(enter|type|input|fill)\b", re.I)),
    ("CLICK", re.compile(r"\b(click|press|tap|select)\b", re.I)),
    ("ASSERT_TEXT", re.compile(r"\b(verify|check|assert|confirm|expect)\b", re.I)),
    ("WAIT", re.compile(r"\b(wait|pause)\b", re.I)),
]
STOP_WORDS = {
    "a", "an", "and", "at", "button", "click", "enter", "field", "for", "go",
    "in", "into", "login", "on", "open", "page", "press", "the", "to", "type",
    "user", "with",
}


def _split_steps(text: str) -> list[str]:
    return [part.strip(" \t-*0123456789.)") for part in re.split(r"[\n;]+", text) if part.strip()]


def keyword_for_step(step: str) -> str:
    for keyword, pattern in ACTION_PATTERNS:
        if pattern.search(step):
            return keyword
    return "MANUAL_REVIEW"


def standardize_case(case: dict[str, Any]) -> dict[str, Any]:
    steps = _split_steps(str(case.get("steps", "")))
    formatted = [
        f"{index}. {keyword_for_step(step)} — {step.rstrip('.')}."
        for index, step in enumerate(steps, start=1)
    ]
    expected = str(case.get("expected_result", "")).strip()
    if expected:
        formatted.append(f"{len(formatted) + 1}. ASSERT_TEXT — {expected.rstrip('.')}.")
    return {
        "standardized_steps": "\n".join(formatted),
        "unrecognized_steps": [step for step in steps if keyword_for_step(step) == "MANUAL_REVIEW"],
        "missing_expected_result": not bool(expected),
    }


def _target(step: str, keyword: str) -> str:
    cleaned = re.sub(r"^[\s\d.*)-]+", "", step)
    cleaned = re.sub(
        r"^(open|go to|navigate to|visit|enter|type|input|fill|click|press|tap|select|verify|check|assert|confirm|expect)\s*",
        "",
        cleaned,
        flags=re.I,
    )
    return cleaned.strip(" .,:;") or "REVIEW_REQUIRED"


def discover_keywords(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: dict[str, list[str]] = {}
    for case in cases:
        for step in _split_steps(str(case.get("steps", ""))):
            keyword = keyword_for_step(step)
            if keyword != "MANUAL_REVIEW":
                examples.setdefault(keyword, []).append(_target(step, keyword))
    parameter_names = {
        "NAVIGATE": "destination",
        "INPUT": "field_or_value",
        "CLICK": "element",
        "ASSERT_TEXT": "expected_text_or_condition",
        "WAIT": "duration_or_condition",
    }
    return [
        {
            "Keyword": keyword,
            "Paramètres": parameter_names[keyword],
            "Occurrences": len(values),
            "Exemples": " | ".join(dict.fromkeys(values[:3])),
        }
        for keyword, values in sorted(examples.items())
    ]
