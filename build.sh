#!/usr/bin/env bash
set -o errexit

# ── Install dependencies ──────────────────────────────────────────────────────
# Production uses requirements-prod.txt (no PyTorch/sentence-transformers).
# AI inference is handled by the HuggingFace Inference API (AI_BACKEND=hf_api).
# Local dev uses requirements.txt which includes torch and sentence-transformers.
pip install -r requirements-prod.txt

python manage.py collectstatic --no-input

python manage.py migrate

# Ensure Celery Beat and Results tables exist (Django Admin monitoring)
python manage.py migrate django_celery_beat
python manage.py migrate django_celery_results