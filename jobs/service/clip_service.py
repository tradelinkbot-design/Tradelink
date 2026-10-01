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

def is_clip_enabled() -> bool:
    """
    Check if CLIP multimodal cross-matching is enabled.
    Disabled by default on memory-constrained servers (like Railway 512MB RAM)
    because loading two AI models simultaneously causes Linux OOM (SIGKILL).
    When disabled, returns False and encoders return zero vectors safely.
    To enable on instances with >=2GB RAM, set ENABLE_CLIP=True in environment.
    """
    return os.environ.get('ENABLE_CLIP', 'False').strip().lower() in ('true', '1')

# HuggingFace Inference API endpoint for CLIP
_HF_CLIP_API_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "openai/clip-vit-base-patch32/pipeline/feature-extraction"
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

    token = (os.environ.get('HF_TOKEN') or os.environ.get('HF_API_TOKEN') or os.environ.get('HUGGINGFACE_TOKEN') or '').strip()
    if not token:
        logger.warning(
            "HF_TOKEN / HF_API_TOKEN is not set in environment variables! "
            "Returning zero vector for CLIP image embedding."
        )
        return [0.0] * CLIP_EMBED_DIM

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "image/jpeg",
    }

    try:
        resp = requests.post(
            _HF_CLIP_API_URL,
            headers=headers,
            data=image_bytes,
            timeout=(8, 30),
        )
        if resp.status_code in (400, 401, 403, 503):
            return [0.0] * CLIP_EMBED_DIM
        resp.raise_for_status()
        raw = resp.json()
        vec = np.array(raw, dtype=np.float32)
        if vec.ndim > 1:
            vec = vec.flatten()[:CLIP_EMBED_DIM]
        norm = np.linalg.norm(vec)
        return (vec / norm if norm > 0 else vec).tolist()
    except requests.exceptions.Timeout:
        logger.warning("HF CLIP image encode timed out — using zero vector.")
        return [0.0] * CLIP_EMBED_DIM
    except Exception as exc:
        logger.warning("HF CLIP image encode failed: %s — using zero vector.", exc)
        return [0.0] * CLIP_EMBED_DIM


def _hf_clip_encode_text(text: str) -> List[float]:
    """
    Encode text via the HuggingFace Inference API for CLIP (cross-modal space).
    Returns an L2-normalised 512-dim float list.
    """
    import requests

    token = (os.environ.get('HF_TOKEN') or os.environ.get('HF_API_TOKEN') or os.environ.get('HUGGINGFACE_TOKEN') or '').strip()
    if not token:
        return [0.0] * CLIP_EMBED_DIM

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "inputs": [text],
        "options": {"wait_for_model": True},
    }

    try:
        resp = requests.post(
            _HF_CLIP_API_URL,
            headers=headers,
            json=payload,
            timeout=(8, 30),
        )
        if resp.status_code in (400, 401, 403, 503):
            return [0.0] * CLIP_EMBED_DIM
        resp.raise_for_status()
        raw = resp.json()
        vec = np.array(raw, dtype=np.float32)
        if vec.ndim > 1:
            vec = vec.flatten()[:CLIP_EMBED_DIM]
        norm = np.linalg.norm(vec)
        return (vec / norm if norm > 0 else vec).tolist()
    except requests.exceptions.Timeout:
        logger.warning("HF CLIP text encode timed out — using zero vector.")
        return [0.0] * CLIP_EMBED_DIM
    except Exception as exc:
        logger.warning("HF CLIP text encode failed: %s — using zero vector.", exc)
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
        """Load CLIP locally via torch. No-op when AI_BACKEND=hf_api or fastembed."""
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
                logger.warning("Failed to load local PyTorch CLIP model: %s — will fallback gracefully.", exc)
                self._model = None

    # ── Image encoding ───────────────────────────────────────────────────────

    def encode_image_file(self, image_path: str) -> List[float]:
        """Encode an image file at the given path. Returns 512-dim float list."""
        if not is_clip_enabled():
            return [0.0] * CLIP_EMBED_DIM

        try:
            backend = os.environ.get('AI_BACKEND', 'fastembed')
            if backend == 'hf_api':
                with open(image_path, 'rb') as f:
                    return _hf_clip_encode_image(f.read())

            if backend == 'fastembed':
                try:
                    from fastembed import ImageEmbedding
                    cache_dir = os.environ.get('FASTEMBED_CACHE_PATH', '').strip() or None
                    model = ImageEmbedding(model_name="Qdrant/clip-ViT-B-32-vision", cache_dir=cache_dir)
                    embeddings = list(model.embed([image_path]))
                    vec = np.array(embeddings[0], dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    return (vec / norm if norm > 0 else vec).tolist()
                except Exception as exc:
                    logger.warning("FastEmbed CLIP image encode failed: %s — returning zero vector.", exc)
                    return [0.0] * CLIP_EMBED_DIM

            self._ensure_loaded()
            if self._model is not None:
                image = Image.open(image_path).convert('RGB')
                return self._encode_pil(image)
        except Exception as exc:
            logger.warning("encode_image_file failed for %s: %s — returning zero vector.", image_path, exc)

        return [0.0] * CLIP_EMBED_DIM

    def encode_image_bytes(self, image_bytes: bytes) -> List[float]:
        """Encode raw image bytes. Returns 512-dim float list."""
        if not is_clip_enabled():
            return [0.0] * CLIP_EMBED_DIM

        try:
            backend = os.environ.get('AI_BACKEND', 'fastembed')
            if backend == 'hf_api':
                return _hf_clip_encode_image(image_bytes)

            self._ensure_loaded()
            if self._model is not None:
                image = Image.open(BytesIO(image_bytes)).convert('RGB')
                return self._encode_pil(image)
        except Exception as exc:
            logger.warning("encode_image_bytes failed: %s — returning zero vector.", exc)

        return [0.0] * CLIP_EMBED_DIM

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
        if not is_clip_enabled():
            return [0.0] * CLIP_EMBED_DIM

        try:
            backend = os.environ.get('AI_BACKEND', 'fastembed')
            if backend == 'hf_api':
                return _hf_clip_encode_text(text)

            if backend == 'fastembed':
                try:
                    from fastembed import TextEmbedding
                    cache_dir = os.environ.get('FASTEMBED_CACHE_PATH', '').strip() or None
                    model = TextEmbedding(model_name="Qdrant/clip-ViT-B-32-text", cache_dir=cache_dir)
                    embeddings = list(model.embed([text]))
                    vec = np.array(embeddings[0], dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    return (vec / norm if norm > 0 else vec).tolist()
                except Exception as exc:
                    logger.warning("FastEmbed CLIP text encode failed: %s — returning zero vector.", exc)
                    return [0.0] * CLIP_EMBED_DIM

            self._ensure_loaded()
            if self._model is not None:
                with self._torch.no_grad():
                    tokens    = self._clip.tokenize([text], truncate=True).to(self._device)
                    embedding = self._model.encode_text(tokens)
                    embedding = embedding / embedding.norm(dim=-1, keepdim=True)
                    return embedding.cpu().float().numpy()[0].tolist()
        except Exception as exc:
            logger.warning("encode_text_for_image_comparison failed: %s — returning zero vector.", exc)

        return [0.0] * CLIP_EMBED_DIM

    encode_text = encode_text_for_image_comparison

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