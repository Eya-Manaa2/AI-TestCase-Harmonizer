from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


class HarmonizerAPIError(RuntimeError):
    """Raised when the configured Harmonizer API fails or returns invalid data."""


def analyze_via_api(
    base_url: str,
    cases: list[dict[str, Any]],
    *,
    threshold: float,
    engine: str,
    embedding_model: str = "",
) -> dict[str, Any]:
    payload = json.dumps(
        {
            "cases": cases,
            "threshold": threshold,
            "engine": engine,
            "embedding_model": embedding_model
            or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}/analyze",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise HarmonizerAPIError(f"L’API a répondu HTTP {exc.code} : {message}") from exc
    except (URLError, TimeoutError) as exc:
        raise HarmonizerAPIError(f"Impossible de joindre l’API du Harmonizer : {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HarmonizerAPIError("L’API a retourné une réponse JSON invalide.") from exc
    if not isinstance(result, dict) or not isinstance(result.get("pairs"), list):
        raise HarmonizerAPIError("La réponse de l’API ne respecte pas le format attendu.")
    return result
