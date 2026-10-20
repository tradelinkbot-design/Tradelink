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
        self.stdout.write(self.style.SUCCESS(
            "Notice: TradeLink has migrated to Flutterwave. "
            "Flutterwave transfers execute automatically and do not require OTP management."
        ))
