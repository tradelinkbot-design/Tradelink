from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'jobs'
    verbose_name       = 'TradeLink NG Marketplace'

    def ready(self):
        import jobs.signals  # noqa: F401

        # NOTE: We do NOT pre-load the sentence-transformer model here.
        #
        # Rationale:
        #   • The TextEncoder singleton (jobs/service/text_encoder.py) already
        #     implements thread-safe lazy loading — it loads the model on the
        #     first encode() call, not at import time.
        #   • Pre-loading in ready() interferes with Daphne's (ASGI) async
        #     event loop because heavy CPU/IO work blocks the GIL and can cause
        #     the server process to become unresponsive and exit.
        #   • The local HuggingFace snapshot is already on disk, so the first
        #     encode() call typically takes < 2 seconds — acceptable for a
        #     one-time warm-up on the very first search request.
        #   • Celery workers load the model independently as needed; no
        #     co-ordination with the web server process is required.