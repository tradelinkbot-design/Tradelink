"""
users/migrations/0004_user_account_type.py
==========================================
Adds the account_type field to the User model.

Existing users default to 'worker' (backward-compatible).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_alter_user_phone_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='account_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('worker',         'Artisan / Tradesperson'),
                    ('digital_worker', 'Digital Skilled Worker'),
                    ('employer',       'Employer'),
                ],
                default='worker',
                db_index=True,
            ),
        ),
    ]
