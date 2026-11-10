from __future__ import annotations

import re
import unicodedata
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SYNONYMS = {
    "open": "navigate",
    "go": "navigate",
    "navigate": "navigate",
    "visit": "navigate",
    "screen": "page",
    "authentication": "login",
    "authenticate": "login",
    "credentials": "username password",
    "type": "enter",
    "input": "enter",
    "fill": "enter",
    "press": "click",
    "tap": "click",
    "select": "click",
    "verify": "assert",
    "check": "assert",
    "validate": "assert",
}


def _canonicalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"\b(log ?in|sign ?in)\b", "login", text)
    text = re.sub(r"\b(username|user name)\b", "username", text)
    text = re.sub(r"\b(password|passcode)\b", "password", text)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(SYNONYMS.get(token, token) for token in text.split())


def _exact_key(case: dict[str, Any]) -> str:
    text = unicodedata.normalize("NFKC", _document(case)).casefold()
    return " ".join(re.findall(r"\w+", text))


def _document(case: dict[str, Any]) -> str:
    return " ".join(
        str(case.get(field, ""))
        for field in ("title", "preconditions", "steps", "expected_result")
    )


def analyze_cases(
    cases: list[dict[str, Any]],
    threshold: float = 0.65,
    embedding_model: Any | None = None,
) -> dict[str, Any]:
    count = len(cases)
    if count == 0:
        return {"similarity": np.zeros((0, 0)), "pairs": [], "clusters": []}

    original_documents = [_document(case) for case in cases]
    documents = [_canonicalize(document) for document in original_documents]
    if embedding_model is None and not any(documents):
        similarities = np.eye(count)
        pairs = []
        clusters = [[index] for index in range(count)]
        return {"similarity": similarities, "pairs": pairs, "clusters": clusters}
    if embedding_model is not None:
        vectors = embedding_model.encode(
            original_documents, normalize_embeddings=True, convert_to_numpy=True
        )
        similarities = cosine_similarity(vectors)
    else:
        word_vectors = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit_transform(documents)
        char_vectors = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True
        ).fit_transform(documents)
        similarities = (
            0.8 * cosine_similarity(word_vectors) + 0.2 * cosine_similarity(char_vectors)
        )
    np.fill_diagonal(similarities, 1.0)

    exact_keys = [_exact_key(case) for case in cases]
    pairs = []
    for left in range(count):
        for right in range(left + 1, count):
            exact = bool(exact_keys[left]) and exact_keys[left] == exact_keys[right]
            if exact or similarities[left, right] >= threshold:
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "score": float(similarities[left, right]),
                        "exact": exact,
                    }
                )
    pairs.sort(key=lambda pair: pair["score"], reverse=True)

    if count == 1:
        labels = np.array([0])
    else:
        distance_threshold = max(0.001, 1.0 - threshold)
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=distance_threshold,
        )
        labels = model.fit_predict(1.0 - similarities)
    clusters: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(index)
    return {
        "similarity": similarities,
        "pairs": pairs,
        "clusters": list(clusters.values()),
    }
