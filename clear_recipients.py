import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')
django.setup()

from jobs.models import WorkerBankAccount

updated = WorkerBankAccount.objects.update(paystack_recipient_code='')
print(f'Cleared {updated} old recipient codes.')
