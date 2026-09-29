"""
bot/models.py
=============
WhatsApp bot session tracking and message logging for TradeLink NG.

WhatsAppSession
    Tracks conversation state per phone number.  The `flow` + `step` fields
    drive the state machine in handlers.py.  The `data` JSONField accumulates
    form inputs during multi-turn flows (e.g. collecting title, category, state,
    and description before creating a Job).

WhatsAppMessage
    Immutable audit log of every inbound / outbound message — useful for
    debugging conversation flows and replaying failed messages.
"""

import uuid

from django.conf import settings
from django.db import models


class WhatsAppSession(models.Model):
    """One session per WhatsApp phone number, upserted on every inbound message."""

    class Flow(models.TextChoices):
        IDLE            = 'idle',            'Idle'
        POST_JOB        = 'post_job',        'Post Job Request'
        SEARCH_JOBS     = 'search_jobs',     'Search Jobs'
        SEARCH_PRODUCTS = 'search_products', 'Search Products'
        LINK_ACCOUNT    = 'link_account',    'Link Account'

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(
        max_length=20, unique=True, db_index=True,
        help_text='E.164 format without leading + e.g. 2348012345678',
    )
    user         = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='whatsapp_sessions',
        help_text='Linked TradeLink NG account — null until the user links via the bot.',
    )
    flow         = models.CharField(
        max_length=30,
        choices=Flow.choices,
        default=Flow.IDLE,
    )
    step         = models.CharField(
        max_length=60, blank=True,
        help_text='Current step within the active flow e.g. "ask_category".',
    )
    data         = models.JSONField(
        default=dict, blank=True,
        help_text='Accumulated inputs from multi-turn conversation '
                  'e.g. {"title": "Fix roof", "category_id": "...", "state": "lagos"}.',
    )
    last_activity = models.DateTimeField(auto_now=True)
    created       = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'WhatsApp Session'
        verbose_name_plural = 'WhatsApp Sessions'
        ordering            = ['-last_activity']

    def __str__(self):
        user_str = self.user.username if self.user else 'Unlinked'
        return f'+{self.phone_number} ({user_str}) — {self.flow}'

    def reset(self, extra_fields=None):
        """
        Return session to idle state, clearing flow data.

        Pass ``extra_fields`` when you have also mutated other fields on
        the session that must be persisted in the same UPDATE, e.g.::

            session.user = user
            session.reset(extra_fields=['user'])
        """
        self.flow = self.Flow.IDLE
        self.step = ''
        self.data = {}
        fields = ['flow', 'step', 'data']
        if extra_fields:
            fields.extend(extra_fields)
        self.save(update_fields=fields)


class WhatsAppMessage(models.Model):
    """Append-only log of every message sent or received by the bot."""

    class Direction(models.TextChoices):
        INBOUND  = 'inbound',  'Inbound (user → bot)'
        OUTBOUND = 'outbound', 'Outbound (bot → user)'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session    = models.ForeignKey(
        WhatsAppSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    direction  = models.CharField(max_length=10, choices=Direction.choices)
    message_id = models.CharField(
        max_length=200, blank=True,
        help_text='WhatsApp wamid.xxx… for inbound messages; empty for outbound.',
    )
    content    = models.TextField(help_text='Plain text of the message body.')
    created    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'WhatsApp Message'
        verbose_name_plural = 'WhatsApp Messages'
        ordering            = ['-created']

    def __str__(self):
        arrow = '←' if self.direction == self.Direction.INBOUND else '→'
        return f'[{arrow}] +{self.session.phone_number}: {self.content[:60]}'
