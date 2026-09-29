"""
jobs/service/clip_service.py
=============================
CLIP image encoder singleton.

Role in the hybrid system
──────────────────────────
  CLIP is used ONLY for the image side of matching:
    • Encodes portfolio photos into 512-dim vectors.
    • Scores are compared against the job's sentence-transformer text embedding
      using cross-modal cosine similarity.

  Text-to-text similarity is handled entirely by text_encoder.py
  (sentence-transformers), which is more accurate for the purpose.

Why keep CLIP at all?
──────────────────────
  The image↔text cross-modal capability is unique to CLIP.
  An employer who writes "solar panel installation on a Lagos rooftop" can
  match workers whose PORTFOLIO PHOTOS visually look like that — something
  no text-only model can do.

Backend routing
───────────────
  AI_BACKEND=local   (DEBUG=True)  → loads ViT-B/32 locally via openai/clip
  AI_BACKEND=hf_api  (DEBUG=False) → calls HuggingFace Inference API (free tier)

Install (local only)
───────
    pip install git+https://github.com/openai/CLIP.git torch torchvision Pillow

Usage
─────
    from jobs.service.clip_service import clip_image_encoder
    vec = clip_image_encoder.encode_image_file("/path/to/photo.jpg")
    vec = clip_image_encoder.encode_image_bytes(raw_bytes)
    vec = clip_image_encoder.encode_text("solar panel installation")  # for job side
"""

import logging
import os
import threading
import time
from io import BytesIO
from typing import List, Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

CLIP_MODEL_NAME  = 'ViT-B/32'
CLIP_EMBED_DIM   = 512

# HuggingFace Inference API endpoint for CLIP
_HF_CLIP_API_URL = (
    "https://api-inference.huggingface.co/pipeline/feature-extraction/"
    "openai/clip-vit-base-patch32"
)


# ── HF API helpers (production path) ─────────────────────────────────────────

def _hf_clip_encode_image(image_bytes: bytes) -> List[float]:
    """
    Encode an image via the HuggingFace Inference API for CLIP.
    Sends raw image bytes with Content-Type: image/jpeg.
    Returns an L2-normalised 512-dim float list.
    Falls back to a zero vector on failure so text-based matching still works.
    """
    import requests

    token = os.environ.get('HF_TOKEN', '')
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "image/jpeg",
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                _HF_CLIP_API_URL,
                headers=headers,
                data=image_bytes,
                timeout=30,
            )
            if resp.status_code == 503:
                wait = 20 * (attempt + 1)
                logger.warning(
                    "HF CLIP API: model loading (503) — retrying in %ss (attempt %d/3)",
                    wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            vec = np.array(resp.json(), dtype=np.float32)
            norm = np.linalg.norm(vec)
            return (vec / norm if norm > 0 else vec).tolist()
        except Exception as exc:
            logger.warning("HF CLIP image encode attempt %d failed: %s", attempt + 1, exc)
            if attempt == 2:
                logger.error(
                    "HF CLIP API failed after 3 attempts — returning zero vector. "
                    "Text-based matching will still work."
                )
                return [0.0] * CLIP_EMBED_DIM
            time.sleep(2 ** attempt)

    return [0.0] * CLIP_EMBED_DIM


def _hf_clip_encode_text(text: str) -> List[float]:
    """
    Encode text via the HuggingFace Inference API for CLIP (cross-modal space).
    Returns an L2-normalised 512-dim float list.
    """
    import requests

    token = os.environ.get('HF_TOKEN', '')
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "inputs": text,
        "options": {"wait_for_model": True},
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                _HF_CLIP_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 503:
                wait = 20 * (attempt + 1)
                logger.warning(
                    "HF CLIP text API: model loading (503) — retrying in %ss",
                    wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            vec = np.array(resp.json(), dtype=np.float32)
            norm = np.linalg.norm(vec)
            return (vec / norm if norm > 0 else vec).tolist()
        except Exception as exc:
            logger.warning("HF CLIP text encode attempt %d failed: %s", attempt + 1, exc)
            if attempt == 2:
                return [0.0] * CLIP_EMBED_DIM
            time.sleep(2 ** attempt)

    return [0.0] * CLIP_EMBED_DIM


# ── CLIPImageEncoder singleton ────────────────────────────────────────────────

class CLIPImageEncoder:
    """
    Lazy-loading singleton for CLIP's visual encoder.

    Routing:
        AI_BACKEND=local   → loads ViT-B/32 locally via torch (dev)
        AI_BACKEND=hf_api  → calls HuggingFace Inference API (production)

    Text encoding is also exposed so the job's sentence-transformer embedding
    can be compared against portfolio image embeddings in the same vector space.
    """

    _instance: Optional['CLIPImageEncoder'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'CLIPImageEncoder':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._model       = None
                    obj._preprocess  = None
                    obj._clip        = None
                    obj._device      = None
                    obj._model_lock  = threading.Lock()
                    cls._instance    = obj
        return cls._instance

    def _ensure_loaded(self) -> None:
        """Load CLIP locally. No-op when AI_BACKEND=hf_api."""
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return
            try:
                import clip
                import torch
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
                logger.info("Loading CLIP model %s on %s …", CLIP_MODEL_NAME, device)
                model, preprocess = clip.load(CLIP_MODEL_NAME, device=device)
                model.eval()
                self._model      = model
                self._preprocess = preprocess
                self._clip       = clip
                self._device     = device
                self._torch      = torch
                logger.info("CLIP image encoder loaded.")
            except Exception as exc:
                logger.exception("Failed to load CLIP model: %s", exc)
                raise

    # ── Image encoding ───────────────────────────────────────────────────────

    def encode_image_file(self, image_path: str) -> List[float]:
        """Encode an image file at the given path. Returns 512-dim float list."""
        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            with open(image_path, 'rb') as f:
                return _hf_clip_encode_image(f.read())

        self._ensure_loaded()
        try:
            image = Image.open(image_path).convert('RGB')
        except Exception as exc:
            raise ValueError(f"Cannot open image {image_path}: {exc}") from exc
        return self._encode_pil(image)

    def encode_image_bytes(self, image_bytes: bytes) -> List[float]:
        """Encode raw image bytes. Returns 512-dim float list."""
        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            return _hf_clip_encode_image(image_bytes)

        self._ensure_loaded()
        try:
            image = Image.open(BytesIO(image_bytes)).convert('RGB')
        except Exception as exc:
            raise ValueError(f"Cannot decode image bytes: {exc}") from exc
        return self._encode_pil(image)

    def _encode_pil(self, image: Image.Image) -> List[float]:
        with self._torch.no_grad():
            tensor    = self._preprocess(image).unsqueeze(0).to(self._device)
            embedding = self._model.encode_image(tensor)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().float().numpy()[0].tolist()

    # ── Text encoding (for cross-modal comparison) ───────────────────────────

    def encode_text_for_image_comparison(self, text: str) -> List[float]:
        """
        Encode text with CLIP's text encoder (512-dim CLIP space).

        Use this ONLY when comparing text against portfolio images — it puts
        both in the same 512-dim CLIP space so cross-modal cosine similarity
        is meaningful.

        For text-to-text similarity, use text_encoder.encode() instead.
        """
        if os.environ.get('AI_BACKEND', 'local') == 'hf_api':
            return _hf_clip_encode_text(text)

        self._ensure_loaded()
        with self._torch.no_grad():
            tokens    = self._clip.tokenize([text], truncate=True).to(self._device)
            embedding = self._model.encode_text(tokens)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().float().numpy()[0].tolist()

    # ── Similarity ───────────────────────────────────────────────────────────

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        va, vb = np.array(a, np.float32), np.array(b, np.float32)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))

    @staticmethod
    def batch_cosine_similarity(
        query: List[float], candidates: List[List[float]]
    ) -> List[float]:
        if not candidates:
            return []
        q = np.array(query, np.float32)
        C = np.array(candidates, np.float32)
        nq = np.linalg.norm(q)
        if nq == 0:
            return [0.0] * len(candidates)
        q = q / nq
        norms = np.linalg.norm(C, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-8, norms)
        return ((C / norms) @ q).tolist()


# Module-level singleton
clip_image_encoder = CLIPImageEncoder()