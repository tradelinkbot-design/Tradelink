import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')
django.setup()

from jobs.models import Milestone
from jobs.service.escrow_service import mark_milestone_released

try:
    milestone = Milestone.objects.get(paystack_transfer_ref='TRF_sivny2lmuxi5wjg9')
    print(f"Current status: {milestone.status}")
    
    if milestone.status != Milestone.Status.RELEASED:
        milestone.status = Milestone.Status.RELEASED
        milestone.save()
        mark_milestone_released(milestone)
        print("Milestone successfully updated to RELEASED!")
    else:
        print("Milestone is already RELEASED.")
except Milestone.DoesNotExist:
    print("Milestone with that transfer code not found.")
except Exception as e:
    print(f"Error: {e}")
