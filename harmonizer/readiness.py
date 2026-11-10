from __future__ import annotations

from typing import Any

from harmonizer.standardizer import _split_steps, keyword_for_step


def assess_readiness(case: dict[str, Any]) -> dict[str, Any]:
    steps = _split_steps(str(case.get("steps", "")))
    criteria = {
        "Clarté des étapes": 20 if len(steps) >= 2 else 10 if steps else 0,
        "Préconditions documentées": 15 if case.get("preconditions", "").strip() else 0,
        "Résultat attendu documenté": 25 if case.get("expected_result", "").strip() else 0,
        "Étapes reconnues": (
            20 * sum(keyword_for_step(step) != "MANUAL_REVIEW" for step in steps) / len(steps)
            if steps
            else 0
        ),
        "Étapes actionnables": (
            20 * sum(len(step.split()) >= 3 for step in steps) / len(steps)
            if steps
            else 0
        ),
    }
    score = round(sum(criteria.values()))
    recommendations: list[str] = []
    if not case.get("preconditions", "").strip():
        recommendations.append("Préciser les préconditions et données de test.")
    if not case.get("expected_result", "").strip():
        recommendations.append("Définir un résultat attendu observable.")
    if not steps:
        recommendations.append("Ajouter des étapes explicites.")
    elif any(keyword_for_step(step) == "MANUAL_REVIEW" for step in steps):
        recommendations.append("Clarifier les étapes non reconnues ou créer un keyword adapté.")
    if score < 70:
        recommendations.append("Faire relire le scénario avant de l’automatiser.")
    level = "Élevé" if score >= 80 else "Moyen" if score >= 50 else "Faible"
    return {
        "score": score,
        "level": level,
        "criteria": criteria,
        "recommendations": recommendations,
    }
