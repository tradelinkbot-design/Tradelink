"""
Initial migration for the bot app.
Creates WhatsAppSession and WhatsAppMessage tables.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WhatsAppSession',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'phone_number',
                    models.CharField(
                        db_index=True,
                        help_text='E.164 format without leading + e.g. 2348012345678',
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    'flow',
                    models.CharField(
                        choices=[
                            ('idle', 'Idle'),
                            ('post_job', 'Post Job Request'),
                            ('search_jobs', 'Search Jobs'),
                            ('search_products', 'Search Products'),
                            ('link_account', 'Link Account'),
                        ],
                        default='idle',
                        max_length=30,
                    ),
                ),
                (
                    'step',
                    models.CharField(
                        blank=True,
                        help_text='Current step within the active flow e.g. "ask_category".',
                        max_length=60,
                    ),
                ),
                (
                    'data',
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text=(
                            'Accumulated inputs from multi-turn conversation '
                            'e.g. {"title": "Fix roof", "category_id": "...", "state": "lagos"}.'
                        ),
                    ),
                ),
                ('last_activity', models.DateTimeField(auto_now=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        blank=True,
                        help_text=(
                            'Linked TradeLink NG account — null until the user links via the bot.'
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='whatsapp_sessions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'WhatsApp Session',
                'verbose_name_plural': 'WhatsApp Sessions',
                'ordering': ['-last_activity'],
            },
        ),
        migrations.CreateModel(
            name='WhatsAppMessage',
            fields=[
                (
                    'id',
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    'direction',
                    models.CharField(
                        choices=[
                            ('inbound', 'Inbound (user → bot)'),
                            ('outbound', 'Outbound (bot → user)'),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    'message_id',
                    models.CharField(
                        blank=True,
                        help_text='WhatsApp wamid.xxx… for inbound messages; empty for outbound.',
                        max_length=200,
                    ),
                ),
                (
                    'content',
                    models.TextField(help_text='Plain text of the message body.'),
                ),
                ('created', models.DateTimeField(auto_now_add=True)),
                (
                    'session',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='messages',
                        to='bot.whatsappsession',
                    ),
                ),
            ],
            options={
                'verbose_name': 'WhatsApp Message',
                'verbose_name_plural': 'WhatsApp Messages',
                'ordering': ['-created'],
            },
        ),
    ]
