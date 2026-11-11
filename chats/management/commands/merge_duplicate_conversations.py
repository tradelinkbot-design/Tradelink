"""
chats/management/commands/merge_duplicate_conversations.py
===========================================================
One-time (and idempotent) command that collapses duplicate Conversation
rows between the same two users.

What counts as a duplicate?
  Two conversations are duplicates when:
    • They share the exact same pair of participants (regardless of order), AND
    • Both have product=NULL  (i.e. they are direct-message threads, not
      product-enquiry threads).

  Product-scoped conversations (product != NULL) are intentionally left alone
  because one conversation per product per user-pair is by design.

What the merge does:
  For each duplicate group:
    1. Keep the OLDEST conversation (lowest created_at) as the canonical one.
    2. Re-parent all Message rows from the newer duplicates to the canonical.
    3. Add all participants of the duplicate to the canonical (should be
       identical, but this is defensive).
    4. Update canonical.last_message_at to reflect the newest message.
    5. Delete the now-empty duplicate Conversation rows.

Usage:
  python manage.py merge_duplicate_conversations
  python manage.py merge_duplicate_conversations --dry-run   # preview only
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Merge duplicate direct-message conversations between the same user pairs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Show what would happen without making any changes.',
        )

    def handle(self, *args, **options):
        from chats.models import Conversation, Message

        dry_run = options['dry_run']
        verb    = '[DRY RUN] ' if dry_run else ''

        # -----------------------------------------------------------------
        # Step 1: Collect all direct-message (product=None) conversations
        #         grouped by their sorted participant-pair.
        # -----------------------------------------------------------------
        direct_convs = (
            Conversation.objects
            .filter(product__isnull=True)
            .prefetch_related('participants')
            .order_by('created_at')   # oldest first → canonical = qs[0]
        )

        pair_map: dict = {}  # frozenset({user_pk, user_pk}) → [conv, ...]

        for conv in direct_convs:
            pks = frozenset(conv.participants.values_list('pk', flat=True))
            pair_map.setdefault(pks, []).append(conv)

        # Only pairs with more than one conversation are duplicates
        duplicates = {pks: convs for pks, convs in pair_map.items() if len(convs) > 1}

        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate conversations found. All clean!'))
            return

        total_merged   = 0
        total_messages = 0

        for pair_pks, convs in duplicates.items():
            # Oldest conversation is the canonical one
            canonical = convs[0]
            duplicates_to_merge = convs[1:]

            msg_count = sum(
                c.messages.count() for c in duplicates_to_merge
            )
            self.stdout.write(
                f'{verb}Merging {len(duplicates_to_merge)} duplicate(s) '
                f'into conversation {canonical.pk} '
                f'(participants: {set(pair_pks)}, messages to move: {msg_count})'
            )

            if not dry_run:
                with transaction.atomic():
                    for dup in duplicates_to_merge:
                        # Re-parent messages
                        moved = Message.objects.filter(
                            conversation=dup
                        ).update(conversation=canonical)

                        # Merge participants (defensive — should already match)
                        for participant in dup.participants.all():
                            canonical.participants.add(participant)

                        self.stdout.write(
                            f'  • Moved {moved} message(s) from {dup.pk} → {canonical.pk}, '
                            f'then deleted {dup.pk}.'
                        )
                        dup.delete()

                    # Refresh last_message_at from the now-consolidated messages
                    latest_msg = (
                        canonical.messages
                        .order_by('-created_at')
                        .values_list('created_at', flat=True)
                        .first()
                    )
                    if latest_msg:
                        Conversation.objects.filter(pk=canonical.pk).update(
                            last_message_at=latest_msg,
                        )

            total_merged   += len(duplicates_to_merge)
            total_messages += msg_count

        style = self.style.WARNING if dry_run else self.style.SUCCESS
        action = 'Would merge' if dry_run else 'Merged'
        self.stdout.write(
            style(
                f'\n{action} {total_merged} duplicate conversation(s) '
                f'({total_messages} message(s) re-parented).'
            )
        )
