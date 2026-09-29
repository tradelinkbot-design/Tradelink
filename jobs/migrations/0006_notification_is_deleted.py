from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0005_add_escrow_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='is_deleted',
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
