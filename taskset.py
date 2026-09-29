from jobs.models import CLIPMatch
from bot.models import WhatsAppSession

job_id = "2d0db13e-bb95-437a-a51a-6fcb5620958d"

matches = (
    CLIPMatch.objects
    .filter(job_id=job_id, score__gte=0.65)
    .select_related("worker__user")
    .order_by("-score")
)

for match in matches:
    worker = match.worker
    user = worker.user

    print("\n================================")
    print("Worker:", worker)
    print("User ID:", user.pk if user else None)
    print("Username:", user.username if user else None)
    print("Phone:", user.phone_number if user else None)
    print("Score:", match.score)

    if user:
        sessions = WhatsAppSession.objects.filter(
            user=user
        )

        print(
            "WhatsApp sessions:",
            list(
                sessions.values(
                    "id",
                    "phone_number",
                    "user_id",
                )
            )
        )