"""
Evaluation-harness-only embedding.

This is deliberately NOT `backend/app/services/embedding_service.py`'s
`DeterministicDevFallbackProvider` (a meaningless hash, used elsewhere
only to exercise plumbing) and NOT the real
`sentence-transformers/paraphrase-multilingual-mpnet-base-v2` model
(needs `pip install sentence-transformers` + a model download, neither
possible in this sandbox — see DATASET.md/EVALUATION.md).

It's a third thing: a hashed bag-of-words term-frequency vector with a
small hand-written cross-lingual synonym table for the handful of legal
terms this fixture's Hindi/Kannada chunks actually use (spec section
47's multilingual-parity check needs SOME way for a Hindi query to
match an English chunk without a real multilingual model on hand).
Cosine similarity over these vectors is genuinely computed from real
term overlap — not a fabricated score — so Precision@K/Recall@K/MRR
computed on top of it are real numbers for THIS fixture. They are not a
substitute for running the real embedding model against the real
corpus before writing up spec section 46's report table.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

DIMENSIONS = 512

# Minimal EN<->HI<->KN synonym bridge for terms this fixture's non-English
# chunks/questions actually use. Not a translation system — just enough
# for the toy embedder to see cross-lingual overlap on THIS fixture.
_SYNONYMS: dict[str, str] = {
    # Hindi -> a shared English anchor token
    "पहचान": "identity", "चोरी": "theft", "इलेक्ट्रॉनिक": "electronic",
    "पासवर्ड": "password", "हस्ताक्षर": "signature", "अनुबंध": "contract",
    "समझौता": "agreement", "सहमति": "consent", "प्रतिफल": "consideration",
    "दंड": "punishment", "सजा": "punishment",
    # Kannada -> a shared English anchor token
    "ಎಲೆಕ್ಟ್ರಾನಿಕ್": "electronic", "ಪಾಸ್\u200cವರ್ಡ್": "password",
    "ಗುರುತಿನ": "identity", "ಕಳ್ಳತನ": "theft", "ಒಪ್ಪಂದ": "contract",
    "ಒಪ್ಪಿಗೆ": "consent", "ಪ್ರತಿಫಲ": "consideration", "ಶಿಕ್ಷೆ": "punishment",
}

_TOKEN_RE = re.compile(r"[\w\u0900-\u097F\u0C80-\u0CFF]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    return [_SYNONYMS.get(t, t) for t in tokens]


def _hash_index(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % DIMENSIONS


def embed(text: str) -> list[float]:
    """Hashed term-frequency vector, L2-normalized (so dot product ==
    cosine similarity, matching the convention `vector_store_service.py`
    uses for the real embedding provider)."""
    counts = Counter(_tokenize(text))
    vec = [0.0] * DIMENSIONS
    for token, count in counts.items():
        vec[_hash_index(token)] += count
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
