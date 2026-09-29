from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ContactInquiry(models.Model):
    """
    Customer support and platform inquiries submitted via the Contact Us page.
    """

    CATEGORY_CHOICES = [
        ("general", "General Inquiry"),
        ("verification", "Technician Verification & Badges"),
        ("hiring", "Employer & Hiring Support"),
        ("billing", "Billing, Payments & Escrow"),
        ("dispute", "Dispute or Safety Concern"),
        ("partnership", "Business Partnership & Press"),
        ("technical", "Technical Issue / Bug Report"),
    ]

    STATUS_CHOICES = [
        ("new", "New (Unread)"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("closed", "Closed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_inquiries",
        help_text="Registered user who submitted this inquiry (if authenticated)",
    )

    name = models.CharField(max_length=120, verbose_name="Full Name")
    email = models.EmailField(verbose_name="Email Address")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Phone Number / WhatsApp")
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default="general",
        verbose_name="Inquiry Topic",
    )
    subject = models.CharField(max_length=200, verbose_name="Subject")
    message = models.TextField(verbose_name="Message")

    # Admin Management
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        db_index=True,
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes for support agents handling this inquiry",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact Inquiry"
        verbose_name_plural = "Contact Inquiries"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.subject} - {self.name}"
