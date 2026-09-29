import os
from pathlib import Path

model_path = os.environ.get('TEXT_ENCODER_MODEL_PATH')
if model_path:
    modules = Path(model_path) / 'modules.json'
    print(f"modules.json exists: {modules.exists()}")
else:
    print("TEXT_ENCODER_MODEL_PATH not set")