"""
jobs/service/text_encoder.py
=============================
Sentence-transformer singleton for text-to-text semantic similarity.

Responsibilities
────────────────
  • Load the sentence-transformer model ONCE per process (lazy singleton).
  • Expose encode() and encode_batch() with L2-normalised outputs.
  • Never touch the database.

Model choice: all-mpnet-base-v2
────────────────────────────────
  Chosen because:
    • Best-in-class semantic similarity scores on STSB / STS benchmarks.
    • 768-dim embeddings — richer than CLIP's 512-dim.
    • Handles up to 512 tokens — covers any realistic bio or job description.
    • ~420 MB model size, ~30–80 ms/inference on CPU.

  Alternatives (if CPU budget is tight):
    • all-MiniLM-L6-v2  — 90% of the quality at 5× the speed, 80 MB.
    • paraphrase-multilingual-mpnet-base-v2  — if you add Yoruba/Hausa support.

Install
───────
    pip install sentence-transformers

Usage
─────
    from jobs.service.text_encoder import text_encoder
    vec = text_encoder.encode("Electrician Lagos solar panel installation")
"""

import logging
import threading
import os
import time
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
# Fallback model name (HuggingFace hub id) used ONLY if no path is configured.
# NOTE: do not resolve os.environ here at module level — Django settings and
# os.environ.setdefault() calls in settings.py may not have run yet when this
# module is first imported.  The path is resolved lazily inside _ensure_loaded().
_DEFAULT_MODEL_NAME = 'sentence-transformers/all-mpnet-base-v2'
EMBEDDING_DIM       = 768   # matches all-mpnet-base-v2 output

# HuggingFace Inference API endpoint for sentence-transformers
_HF_API_URL = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "sentence-transformers/all-mpnet-base-v2"
)


# ── HF API helpers (production path) ─────────────────────────────────────────

def _hf_api_encode(text: str) -> List[float]:
    """
    Encode a single string via the HuggingFace Serverless Inference API.
    Returns an L2-normalised 768-dim float list — identical contract to the
    local SentenceTransformer path.

    Used when AI_BACKEND='hf_api' (i.e. production on Render).
    """
    import requests

    token = os.environ.get('HF_TOKEN', '')
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    payload = {
        "inputs": text,
        "options": {"wait_for_model": True},
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                _HF_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 503:
                # Model is loading on HF's side — wait and retry
                wait = 20 * (attempt + 1)
                logger.warning(
                    "HF API: model loading (503) — retrying in %ss (attempt %d/3)",
                    wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            vec = np.array(resp.json(), dtype=np.float32)
            # L2-normalise to match local SentenceTransformer(normalize_embeddings=True)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec.tolist()
        except Exception as exc:
            logger.warning("HF API encode attempt %d failed: %s", attempt + 1, exc)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("_hf_api_encode: all retries exhausted")


def _hf_api_encode_batch(texts: List[str]) -> List[List[float]]:
    """
    Encode a list of strings via the HF API in one call.
    Returns a list of L2-normalised 768-dim float lists.
    """
    import requests

    token = os.environ.get('HF_TOKEN', '')
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Replace empty strings with a placeholder to avoid API errors,
    # then zero the output — same contract as the local path.
    placeholders = {i for i, t in enumerate(texts) if not t.strip()}
    safe_texts   = [t if t.strip() else 'placeholder' for t in texts]

    payload = {
        "inputs": safe_texts,
        "options": {"wait_for_model": True},
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                _HF_API_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )
            if resp.status_code == 503:
                wait = 20 * (attempt + 1)
                logger.warning(
                    "HF API batch: model loading (503) — retrying in %ss (attempt %d/3)",
                    wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            raw = resp.json()   # list of lists
            result = []
            for idx, vec_list in enumerate(raw):
                vec = np.array(vec_list, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                result.append(vec.tolist())
            # Zero out placeholder slots
            for idx in placeholders:
                result[idx] = [0.0] * EMBEDDING_DIM
            return result
        except Exception as exc:
            logger.warning("HF API batch attempt %d failed: %s", attempt + 1, exc)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError("_hf_api_encode_batch: all retries exhausted")


# ── TextEncoder singleton ─────────────────────────────────────────────────────

class TextEncoder:
    """
    Lazy-loading singleton for the sentence-transformer text encoder.

    Routing:
        AI_BACKEND=local   → loads all-mpnet-base-v2 from local disk (dev)
        AI_BACKEND=hf_api  → calls HuggingFace Inference API (production)

    Usage:
        from jobs.service.text_encoder import text_encoder
        vec   = text_encoder.encode("some text")
        vecs  = text_encoder.encode_batch(["text1", "text2"])
        score = text_encoder.cosine_similarity(vec_a, vec_b)
    """

    _instance: Optional['TextEncoder'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'TextEncoder':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._model       = None
                    obj._model_lock  = threading.Lock()
                    cls._instance    = obj
        return cls._instance

    # ── Private ─────────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """Load the model on first call (local backend only). No-op for hf_api."""
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return

            model_path = os.environ.get('TEXT_ENCODER_MODEL_PATH', '').strip()
            if not model_path:
                logger.warning(
                    "TEXT_ENCODER_MODEL_PATH is not set. "
                    "Falling back to hub name '%s'. "
                    "Set TEXT_ENCODER_MODEL_PATH to the absolute snapshot "
                    "directory to guarantee offline loading.",
                    _DEFAULT_MODEL_NAME,
                )
                model_path = _DEFAULT_MODEL_NAME
            else:
                if not os.path.isdir(model_path):
                    raise FileNotFoundError(
                        f"TEXT_ENCODER_MODEL_PATH does not exist: {model_path!r}\n"
                        "Check your settings.py SNAPSHOT_HASH and that the model "
                        "has been downloaded."
                    )

            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading sentence-transformer from %r …", model_path)
                self._model = SentenceTransformer(model_path, local_files_only=True)
                logger.info("Text encoder ready (dim=%d).", EMBEDDING_DIM)
            except Exception as exc:
                logger.exception("Failed to load text encoder from %r: %s", model_path, exc)
                raise

    # ── Public API ───────────────────────────────────────────────────────────

    def encode(self, text: str) -> List[float]:
        """
        Encode a single text string into a normalised 768-dim float list.

        Routes to HuggingFace Inference API (AI_BACKEND=hf_api) in production,
        or local SentenceTransformer model (AI_BACKEND=local) in development.
        """
        text = text.strip()
        if not text:
            raise ValueError("Cannot encode an empty string.")

        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            logger.debug("text_encoder.encode → HF API")
            return _hf_api_encode(text)

        # Local dev path — loads cached model from disk
        self._ensure_loaded()
        vec = self._model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vec.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Encode a list of strings.

        In production (hf_api) sends them all in one API call.
        In development, runs a batched forward pass through the local model.
        """
        if not texts:
            return []

        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            logger.debug("text_encoder.encode_batch (%d texts) → HF API", len(texts))
            return _hf_api_encode_batch(texts)

        # Local dev path
        self._ensure_loaded()
        placeholders = {i: '' for i, t in enumerate(texts) if not t.strip()}
        safe_texts   = [t if t.strip() else 'placeholder' for t in texts]

        vecs = self._model.encode(
            safe_texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )

        result = vecs.tolist()
        for idx in placeholders:
            result[idx] = [0.0] * EMBEDDING_DIM

        return result

    @property
    def is_ready(self) -> bool:
        """
        True if the model is loaded (local) or API backend is configured.
        Non-blocking.
        """
        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            return bool(os.environ.get('HF_TOKEN', ''))
        return self._model is not None

    @property
    def embedding_dim(self) -> int:
        return EMBEDDING_DIM

    # ── Similarity helpers ───────────────────────────────────────────────────

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """
        Cosine similarity between two vectors.
        Because encode() normalises outputs, this equals the dot product.
        Returns float in [-1.0, 1.0].
        """
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))

    @staticmethod
    def batch_cosine_similarity(
        query: List[float],
        candidates: List[List[float]],
    ) -> List[float]:
        """
        Vectorised cosine similarity: one query vs many candidates.
        Single NumPy matrix-multiply — O(N·D) vs O(N·D) Python loop.
        """
        if not candidates:
            return []
        q = np.array(query, dtype=np.float32)
        C = np.array(candidates, dtype=np.float32)   # shape (N, 768)

        nq = np.linalg.norm(q)
        if nq == 0:
            return [0.0] * len(candidates)
        q = q / nq

        norms = np.linalg.norm(C, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-8, norms)
        C = C / norms

        return (C @ q).tolist()


# Module-level singleton — import this anywhere
text_encoder = TextEncoder()


def encode_text(text: str) -> List[float]:
    """Convenience functional wrapper around text_encoder.encode."""
    return text_encoder.encode(text)
