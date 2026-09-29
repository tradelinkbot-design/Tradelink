import os
import sys
import django
import logging

# Configure Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'technicians.settings')
django.setup()

from marketplace.models import Order
from marketplace.service.market_place_service_escrow import release_order_to_seller

# Turn on logging to see exactly what Paystack returns
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('marketplace.service.market_place_service_escrow')
logger.setLevel(logging.DEBUG)

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_release.py <order_id_prefix>")
        print("Example: python test_release.py B5F6D6A7")
        sys.exit(1)

    prefix = sys.argv[1].strip()
    
    order = None
    for o in Order.objects.all():
        if str(o.id).upper().startswith(prefix.upper()):
            order = o
            break

    if not order:
        print(f"❌ Order starting with '{prefix}' not found.")
        return

    print("==================================================")
    print(f"📦 Found Order: {order.id}")
    print(f"📊 Status: {order.status}")
    print(f"💰 Seller payout amount: ₦{order.seller_payout_amount}")
    
    bank = getattr(order.seller, 'bank_account', None)
    if bank:
        print(f"🏦 Bank: {bank.account_number} ({bank.bank_name})")
        print(f"🔗 Recipient code: {bank.paystack_recipient_code}")
    else:
        print("❌ No bank account found for seller!")
        return

    print("==================================================")
    print("🚀 Attempting to release funds via Paystack now...\n")
    
    try:
        success = release_order_to_seller(str(order.id))
        print("\n==================================================")
        print(f"✅ release_order_to_seller returned: {success}")
        
        order.refresh_from_db()
        print(f"🆕 New Status: {order.status}")
        print(f"🧾 Transfer Ref: {order.paystack_transfer_ref}")
        
        if success:
            print("\n🎉 SUCCESS! Paystack accepted the transfer.")
        else:
            print("\n❌ FAILED. Check the error logs above for the Paystack rejection reason.")
            
    except Exception as e:
        print(f"\n💥 Exception occurred: {e}")

if __name__ == '__main__':
    main()
