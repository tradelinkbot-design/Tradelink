"""
jobs/management/commands/disable_paystack_otp.py
=================================================
Management command to request and finalize disabling OTP requirement for Paystack Transfers.

Usage:
  Step 1 (Request OTP):
    python manage.py disable_paystack_otp

    Paystack will send an OTP to the registered phone number/email of the business owner.

  Step 2 (Finalize with OTP):
    python manage.py disable_paystack_otp --otp 123456

    This permanently disables OTP on the Paystack account so all future escrow transfers
    execute automatically with no manual OTP needed.

  Optional (Re-enable OTP):
    python manage.py disable_paystack_otp --enable
"""

from django.core.management.base import BaseCommand
from jobs.service.escrow_service import (
    request_disable_transfer_otp,
    finalize_disable_transfer_otp,
    enable_transfer_otp,
)


class Command(BaseCommand):
    help = "Request or finalize disabling OTP requirement for Paystack transfers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--otp",
            type=str,
            help="The OTP received from Paystack to finalize disabling the transfer OTP requirement.",
        )
        parser.add_argument(
            "--enable",
            action="store_true",
            help="Re-enable OTP requirement on Paystack.",
        )

    def handle(self, *args, **options):
        otp = options.get("otp")
        enable = options.get("enable")

        if enable:
            self.stdout.write(self.style.WARNING("Attempting to re-enable OTP requirement on Paystack..."))
            result = enable_transfer_otp()
            if result.get("status"):
                self.stdout.write(self.style.SUCCESS(f"Success: {result.get('message', 'OTP requirement enabled.')}"))
            else:
                self.stdout.write(self.style.ERROR(f"Error: {result.get('message', 'Failed to enable OTP.')}"))
            return

        if otp:
            self.stdout.write(self.style.WARNING(f"Submitting OTP '{otp}' to disable transfer OTP on Paystack..."))
            result = finalize_disable_transfer_otp(otp)
            if result.get("status"):
                self.stdout.write(self.style.SUCCESS(
                    f"SUCCESS: {result.get('message', 'OTP requirement for transfers has been disabled.')}\n"
                    "All future escrow payouts will now transfer automatically without OTP!"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"FAILED: {result.get('message', 'Invalid OTP or request failed.')}"
                ))
        else:
            self.stdout.write(self.style.WARNING(
                "Requesting OTP from Paystack to disable transfer OTP requirement..."
            ))
            result = request_disable_transfer_otp()
            if result.get("status"):
                self.stdout.write(self.style.SUCCESS(
                    f"SUCCESS: {result.get('message')}\n\n"
                    "Check your Paystack-registered mobile number or email for the OTP.\n"
                    "Then run:\n"
                    "  python manage.py disable_paystack_otp --otp <YOUR_OTP>\n"
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    f"FAILED: {result.get('message', 'Could not request OTP from Paystack.')}\n"
                    "Note: If OTP is already disabled on your Paystack account, you can also verify this in "
                    "Paystack Dashboard -> Settings -> Preferences -> Transfer."
                ))
