"""
chats/tasks.py
===============
Celery tasks for the TradeLink NG chat system.

Tasks
──────
  cleanup_orphan_attachments_task
      Nightly: deletes MessageAttachment records that were uploaded but
      never linked to a message (user abandoned the send flow).

  reset_stale_online_status_task
      Runs every 10 minutes: marks users as offline if their last_seen
      is older than 5 minutes and they are still flagged as is_online.
      Guards against the case where a WebSocket disconnect signal is lost
      (e.g. server restart, network partition).

Add to your settings.py CELERY_BEAT_SCHEDULE:

    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        ...
        'cleanup-orphan-chat-attachments': {
            'task':     'chats.tasks.cleanup_orphan_attachments_task',
            'schedule': crontab(hour=3, minute=30),
        },
        'reset-stale-chat-online-status': {
            'task':     'chats.tasks.reset_stale_online_status_task',
            'schedule': crontab(minute='*/10'),
        },
    }
"""

import logging
from datetime import timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def cleanup_orphan_attachments_task() -> None:
    """
    Removes MessageAttachment rows where message is still NULL after 24 hours.

    These are files the user uploaded for a chat image but never sent —
    either because they cancelled, closed the tab, or had an error.
    The actual files on disk are deleted along with the DB row.
    """
    from django.utils import timezone
    from chats.models import MessageAttachment

    cutoff  = timezone.now() - timedelta(hours=24)
    orphans = MessageAttachment.objects.filter(
        message__isnull=True,
        created_at__lt=cutoff,
    )

    deleted = 0
    for att in orphans:
        try:
            att.file.delete(save=False)   # remove from storage
        except Exception:
            logger.warning(
                'cleanup_orphan_attachments_task: could not delete file for %s', att.pk
            )
        att.delete()
        deleted += 1

    logger.info(
        'cleanup_orphan_attachments_task: removed %d orphan attachment(s).', deleted
    )


@shared_task(ignore_result=True)
def reset_stale_online_status_task() -> None:
    """
    Marks users as offline if they have not sent a WebSocket heartbeat
    in the last 5 minutes (last_seen is more than 5 minutes ago) but
    their record still shows is_online=True.

    This guards against crashed browsers, dropped connections, and server
    restarts where ChatConsumer.disconnect() was never called.
    """
    from django.utils import timezone
    from chats.models import UserOnlineStatus

    cutoff  = timezone.now() - timedelta(minutes=5)
    updated = UserOnlineStatus.objects.filter(
        is_online=True,
        last_seen__lt=cutoff,
    ).update(is_online=False)

    if updated:
        logger.info(
            'reset_stale_online_status_task: marked %d user(s) as offline.', updated
        )