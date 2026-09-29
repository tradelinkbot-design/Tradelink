#!/usr/bin/env python
"""
Diagnostic script for offline sentence-transformer model.

Run this from your project root (where manage.py is).
It will:
  1. Check the TEXT_ENCODER_MODEL_PATH from environment/settings.
  2. Verify all required files exist.
  3. Attempt to load the model with offline flags forced.
  4. Test encoding a sentence.
"""

import os
import sys
from pathlib import Path

# ========== 1. REPLICATE THE PATH LOGIC FROM YOUR SETTINGS ==========
# This is the same logic you have in settings.py (without importing Django)
SNAPSHOT_HASH = 'e8c3b32edf5434bc2275fc9bab85f82640a19130'
DEFAULT_CACHE = os.path.join(os.path.expanduser('~'), '.hf_cache')

# Set environment variables as in settings.py (so the script behaves identically)
os.environ.setdefault('HUGGINGFACE_HUB_SYMLINKS_MODE', 'copy')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('TRANSFORMERS_CACHE', DEFAULT_CACHE)
os.environ.setdefault('HF_HOME', DEFAULT_CACHE)
os.environ.setdefault('SENTENCE_TRANSFORMERS_HOME', DEFAULT_CACHE)

# The model path (same as TEXT_ENCODER_MODEL_PATH)
model_path = os.environ.get(
    'TEXT_ENCODER_MODEL_PATH',
    os.path.join(
        os.path.expanduser('~'),
        '.hf_cache', 'hub',
        'models--sentence-transformers--all-mpnet-base-v2',
        'snapshots',
        SNAPSHOT_HASH,
    )
)
os.environ.setdefault('TEXT_ENCODER_MODEL_PATH', model_path)

# Force offline mode BEFORE any import
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

# ========== 2. PRINT PATHS AND CHECK DIRECTORY ==========
print("\n" + "="*60)
print("OFFLINE MODEL DIAGNOSTIC")
print("="*60)
print(f"Model path: {model_path}")
print(f"Cache dir : {DEFAULT_CACHE}\n")

if not os.path.isdir(model_path):
    print(f"❌ ERROR: Model directory does not exist at:\n   {model_path}")
    print("\nPossible fixes:")
    print("  - Download the model online first (see steps below).")
    print("  - Or update SNAPSHOT_HASH to the correct hash.")
    sys.exit(1)
else:
    print(f"✅ Model directory exists.\n")

# ========== 3. CHECK REQUIRED FILES ==========
required_files = [
    'config.json',
    'tokenizer_config.json',
    'tokenizer.json',
    'vocab.txt',
    'special_tokens_map.json',
    'sentence_bert_config.json',
    'modules.json',   # <<-- CRITICAL! Often missing
]
weight_files = ['pytorch_model.bin', 'model.safetensors']

print("Checking required files...")
all_ok = True
for fname in required_files:
    fpath = os.path.join(model_path, fname)
    if os.path.isfile(fpath):
        print(f"  ✅ {fname}")
    else:
        print(f"  ❌ {fname}  -> MISSING")
        all_ok = False

weight_found = False
for wf in weight_files:
    wpath = os.path.join(model_path, wf)
    if os.path.isfile(wpath):
        size_mb = os.path.getsize(wpath) / (1024*1024)
        print(f"  ✅ {wf} ({size_mb:.1f} MB)")
        weight_found = True
        break
if not weight_found:
    print(f"  ❌ No weight file found (needs {weight_files[0]} or {weight_files[1]})")
    all_ok = False

if not all_ok:
    print("\n❌ Missing files detected. The model download is incomplete.")
    print("To download the full model with internet, run:")
    print("    python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-mpnet-base-v2')\"")
    print("Then locate the snapshot folder in ~/.hf_cache/hub/... and update SNAPSHOT_HASH accordingly.")
    sys.exit(1)

print("\n✅ All required files present.")

# ========== 4. ATTEMPT TO LOAD MODEL OFFLINE ==========
print("\nAttempting to load model with offline mode enforced...")
try:
    from sentence_transformers import SentenceTransformer
    import torch
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Run: pip install sentence-transformers torch")
    sys.exit(1)

try:
    model = SentenceTransformer(model_path)
    print("✅ Model loaded successfully (offline).")
except Exception as e:
    print(f"❌ Model loading FAILED with offline mode:\n   {type(e).__name__}: {e}")
    print("\nThis indicates the model files are corrupted or missing critical components.")
    print("Try re-downloading the model with internet access, then test again.")
    sys.exit(1)

# ========== 5. TEST ENCODING ==========
print("\nTesting encoding a sample sentence...")
test_sentence = "I need an electrician in Lagos"
try:
    embeddings = model.encode(test_sentence, normalize_embeddings=True, show_progress_bar=False)
    print(f"✅ Encoding successful. Output shape: {embeddings.shape}")
    print(f"   First 5 values: {embeddings[:5].tolist()}")
except Exception as e:
    print(f"❌ Encoding failed: {e}")
    sys.exit(1)

# ========== 6. SIMULATE THE SEARCH SERVICE CALL (OPTIONAL) ==========
print("\nSimulating search service call...")
try:
    from numpy import dot
    from numpy.linalg import norm
    # Simulate batch similarity
    dummy_job_embed = embeddings  # pretend it's a job embedding
    query_vec = embeddings
    similarity = dot(query_vec, dummy_job_embed) / (norm(query_vec) * norm(dummy_job_embed))
    print(f"✅ Cosine similarity (self-similarity): {similarity:.6f} (should be ~1.0)")
except Exception as e:
    print(f"⚠️ Similarity test failed: {e}")

print("\n" + "="*60)
print("✅ OFFLINE MODEL WORKS CORRECTLY")
print("="*60)
print("\nIf your Django server still crashes, the issue is NOT the model files.")
print("It could be:")
print("  - The background thread in apps.py (try synchronous preload)")
print("  - tokenizers parallelism (set TOKENIZERS_PARALLELISM=false)")
print("  - A crash inside PyTorch on Windows (try upgrading torch)")