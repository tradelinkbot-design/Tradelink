"""
Management command: python manage.py download_ai_model

Downloads the sentence-transformers/all-mpnet-base-v2 model to the
HuggingFace cache directory (HF_HOME) if it is not already present.

Designed to run as the last step in build.sh on Render so that the
Celery worker can load the model in offline mode (HF_HUB_OFFLINE=1).

Usage:
    python manage.py download_ai_model
    python manage.py download_ai_model --force   # re-download even if cached
"""

import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Download the sentence-transformer AI model to disk if not already cached."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-download even if the model is already cached.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        # Check if model is already present at the configured path
        model_path = os.environ.get("TEXT_ENCODER_MODEL_PATH", "").strip()
        if model_path and os.path.isdir(model_path) and not force:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✔ AI model already exists at:\n  {model_path}\n  Skipping download."
                )
            )
            return

        # Temporarily disable offline mode so huggingface_hub can download
        original_offline     = os.environ.get("HF_HUB_OFFLINE")
        original_tf_offline  = os.environ.get("TRANSFORMERS_OFFLINE")
        os.environ["HF_HUB_OFFLINE"]      = "0"
        os.environ["TRANSFORMERS_OFFLINE"] = "0"

        model_name = "sentence-transformers/all-mpnet-base-v2"
        hf_home = os.environ.get(
            "HF_HOME",
            os.path.join(os.path.expanduser("~"), ".hf_cache"),
        )

        self.stdout.write(
            f"⬇  Downloading {model_name} ...\n"
            f"   Cache directory: {hf_home}"
        )

        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)

            self.stdout.write(
                self.style.SUCCESS(
                    f"✔ Model downloaded successfully.\n"
                    f"  Cache: {hf_home}"
                )
            )

            # Print the exact snapshot path so you can copy it into
            # the TEXT_ENCODER_MODEL_PATH env var on Render.
            try:
                snapshot_dir = model[0].auto_model.config._name_or_path
                self.stdout.write(
                    f"\n📌 Snapshot path (copy this as TEXT_ENCODER_MODEL_PATH):\n"
                    f"   {snapshot_dir}\n"
                )
            except Exception:
                pass  # Not critical if we can't retrieve the path

        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"✘ Failed to download model: {exc}")
            )
            raise
        finally:
            # Restore original offline settings
            if original_offline is not None:
                os.environ["HF_HUB_OFFLINE"] = original_offline
            else:
                os.environ.pop("HF_HUB_OFFLINE", None)

            if original_tf_offline is not None:
                os.environ["TRANSFORMERS_OFFLINE"] = original_tf_offline
            else:
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
