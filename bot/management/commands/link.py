from django.core.management.base import BaseCommand

from bot.models import WhatsAppSession
from jobs.models import WorkerProfile


class Command(BaseCommand):
    help = "Create/link WhatsApp sessions for worker profiles with phone numbers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--trade",
            default="",
            help="Worker trade category slug, e.g. plumber",
        )

        parser.add_argument(
            "--username",
            default="",
            help="Link only one username.",
        )

    def handle(self, *args, **options):

        trade_slug = options["trade"].strip()
        username = options["username"].strip()

        workers = (
            WorkerProfile.objects
            .select_related("user", "trade_category")
            .filter(user__isnull=False)
        )

        if trade_slug:
            workers = workers.filter(
                trade_category__slug=trade_slug
            )

        if username:
            workers = workers.filter(
                user__username=username
            )

        linked = 0
        skipped = 0

        for worker in workers:

            user = worker.user

            if not user.phone_number:
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP {user.username}: no phone number"
                    )
                )
                skipped += 1
                continue

            phone = str(user.phone_number).lstrip("+")

            session, created = WhatsAppSession.objects.get_or_create(
                phone_number=phone,
                defaults={
                    "user": user,
                    "flow": WhatsAppSession.Flow.IDLE,
                },
            )

            if session.user_id != user.id:
                session.user = user
                session.flow = WhatsAppSession.Flow.IDLE
                session.step = ""
                session.data = {}
                session.save(
                    update_fields=[
                        "user",
                        "flow",
                        "step",
                        "data",
                    ]
                )

            action = "created" if created else "linked"

            self.stdout.write(
                self.style.SUCCESS(
                    f"{action}: {user.username} → +{phone}"
                )
            )

            linked += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Linked {linked} worker(s); "
                f"skipped {skipped}."
            )
        )