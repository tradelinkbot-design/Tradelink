import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')
django.setup()

from marketplace.models import Order
from jobs.models import WorkerBankAccount

try:
    order = Order.objects.get(pk='B5F6D6A7-0000-0000-0000-000000000000') # UUIDs usually look like this, wait let's just use startswith
except ValueError:
    orders = Order.objects.filter(id__startswith='B5F6D6A7')
    if orders.exists():
        order = orders.first()
    else:
        # try case insensitive or just check all
        order = None
        for o in Order.objects.all():
            if str(o.id).upper().startswith('B5F6D6A7'):
                order = o
                break

if not order:
    print("No order found starting with B5F6D6A7")
    sys.exit(0)

print(f"Order ID: {order.pk}")
print(f"Status: {order.status}")
print(f"Confirmed At: {order.confirmed_at}")
print(f"Completed At: {order.completed_at}")
print(f"Seller: {order.seller.user.username}")
print(f"Seller Payout Amount: {order.seller_payout_amount}")
has_bank = hasattr(order.seller, 'bank_account')
print(f"Seller has bank account? {has_bank}")

if has_bank:
    bank = order.seller.bank_account
    print(f"Bank Account: {bank.account_number} ({bank.bank_name})")
    print(f"Recipient code: {bank.paystack_recipient_code}")
else:
    print("NO BANK ACCOUNT FOUND FOR SELLER")

# Let's also check Celery tasks or Paystack logs if possible
