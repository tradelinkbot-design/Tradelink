from django import forms
from .models import ContactInquiry


class ContactInquiryForm(forms.ModelForm):
    class Meta:
        model = ContactInquiry
        fields = ["name", "email", "phone", "category", "subject", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control has-icon",
                    "placeholder": "e.g. Chukwuma Adebayo",
                    "autocomplete": "name",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control has-icon",
                    "placeholder": "name@example.com",
                    "autocomplete": "email",
                    "required": True,
                }
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control has-icon",
                    "placeholder": "+234 800 000 0000",
                    "autocomplete": "tel",
                }
            ),
            "category": forms.Select(
                attrs={
                    "class": "form-control has-icon form-select",
                    "required": True,
                }
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control has-icon",
                    "placeholder": "Brief summary of your question or issue",
                    "required": True,
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Tell us how we can help you in detail...",
                    "required": True,
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.is_authenticated:
            # Pre-fill name and email from profile/user
            full_name = getattr(user, "get_full_name", lambda: "")() or user.username
            if not self.initial.get("name"):
                self.initial["name"] = full_name
            if not self.initial.get("email"):
                self.initial["email"] = user.email
            if hasattr(user, "profile") and getattr(user.profile, "phone_number", None):
                if not self.initial.get("phone"):
                    self.initial["phone"] = user.profile.phone_number
