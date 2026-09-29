from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ContactInquiryForm
from .models import ContactInquiry


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def contact_us(request):
    """
    Public Contact Us & Support page for TradeLink NG.
    """
    inquiry_submitted = False
    ref_id = None

    if request.method == "POST":
        form = ContactInquiryForm(request.POST, user=request.user)
        if form.is_valid():
            inquiry = form.save(commit=False)
            if request.user.is_authenticated:
                inquiry.user = request.user
            inquiry.ip_address = get_client_ip(request)
            inquiry.save()

            ref_id = f"TL-{inquiry.id:05d}"
            messages.success(
                request,
                f"Thank you, <strong>{inquiry.name}</strong>! Your inquiry <strong>#{ref_id}</strong> has been received. "
                "Our Nigerian support team will reach back out within 24 hours.",
            )
            return redirect("contacts:contact_us")
    else:
        form = ContactInquiryForm(user=request.user)

    # Frequently Asked Questions for fast resolution
    faqs = [
        {
            "q": "How does technician verification work on TradeLink NG?",
            "a": "Technicians submit government-issued identification (NIN, Driver's License, or Voter's Card), proof of trade certifications, and photos of past projects. Our verification team reviews and assigns Blue, Gold, or Green trust badges.",
        },
        {
            "q": "How do clients pay technicians safely?",
            "a": "TradeLink NG uses a milestone-based escrow system. Employers fund the job milestone before work begins; funds are only released to the artisan once the employer approves the completed job.",
        },
        {
            "q": "What should I do if there is a dispute on a job?",
            "a": "You can select 'Dispute or Safety Concern' in the contact form or use the dispute button on your milestone contract. Our dispute resolution specialists will mediate between both parties.",
        },
        {
            "q": "Is TradeLink NG available across all states in Nigeria?",
            "a": "Yes! While we have active hubs in Lagos, Abuja, Port Harcourt, and Ibadan, skilled technicians and employers can register and post jobs anywhere across Nigeria.",
        },
    ]

    context = {
        "form": form,
        "faqs": faqs,
        "whatsapp_number": "+2348008723354",  # TradeLink support line
        "support_email": "support@tradelink.ng",
        "phone_display": "+234 (0) 800-TRADELINK",
    }
    return render(request, "contacts/contact_us.html", context)
