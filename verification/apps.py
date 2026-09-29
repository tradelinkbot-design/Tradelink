from django.apps import AppConfig


class VerificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'verification'
    verbose_name = 'Identity Verification'

    def ready(self):
        import verification.signals  # noqa: F401
