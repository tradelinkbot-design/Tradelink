from django.apps import AppConfig


class HiringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hiring'
    verbose_name = 'Hiring & Talent'

    def ready(self):
        import hiring.signals  # noqa: F401 — registers all post_save signals
