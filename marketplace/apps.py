"""
marketplace/apps.py
====================
AppConfig for the TradeLink NG tool & equipment marketplace app.
"""

from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'marketplace'
    verbose_name       = 'TradeLink NG — Tool Marketplace'

    def ready(self):
        import marketplace.signals  