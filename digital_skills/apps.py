from django.apps import AppConfig


class DigitalSkillsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'digital_skills'
    verbose_name       = 'TradeLink NG — Digital Skills'

    def ready(self):
        import digital_skills.signals  # noqa: F401
