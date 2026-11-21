"""
digital_skills/forms.py
=======================
Forms for the digital_skills app.
"""

from django import forms
from .models import (
    DigitalWorkerProfile,
    DigitalPortfolioItem,
    DigitalGig,
    DigitalApplication,
)


# ── Digital Worker Profile Setup Form ────────────────────────────────────────

class DigitalWorkerProfileForm(forms.ModelForm):
    """
    Used in the profile setup and edit views.
    sub_skills is handled separately via AJAX / multi-step widget.
    """

    class Meta:
        model  = DigitalWorkerProfile
        fields = [
            'primary_category',
            'headline',
            'bio',
            'experience_level',
            'years_experience',
            'hourly_rate',
            'project_rate',
            'state',
            'lga',
            'remote_ok',
            'availability',
            'employment_preference',
            'open_to_employment',
            'expected_monthly_salary',
            'notice_period',
            'whatsapp_number',
            'portfolio_url',
            'linkedin_url',
            'twitter_url',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': 'Describe your skills, experience, and what makes you stand out...',
                'class': 'form-control',
            }),
            'headline': forms.TextInput(attrs={
                'placeholder': 'e.g. Expert Graphic Designer | Branding Specialist | 5 yrs exp',
                'class': 'form-control',
            }),
            'primary_category': forms.Select(attrs={'class': 'form-select'}),
            'experience_level': forms.Select(attrs={'class': 'form-select'}),
            'availability': forms.Select(attrs={'class': 'form-select'}),
            'employment_preference': forms.Select(attrs={'class': 'form-select'}),
            'state': forms.Select(attrs={'class': 'form-select'}),
            'hourly_rate': forms.NumberInput(attrs={
                'placeholder': '0.00', 'class': 'form-control', 'min': '0',
            }),
            'project_rate': forms.NumberInput(attrs={
                'placeholder': '0.00', 'class': 'form-control', 'min': '0',
            }),
            'expected_monthly_salary': forms.NumberInput(attrs={
                'placeholder': '0.00', 'class': 'form-control', 'min': '0',
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'placeholder': '+2348012345678', 'class': 'form-control',
            }),
            'portfolio_url': forms.URLInput(attrs={
                'placeholder': 'https://yourportfolio.com', 'class': 'form-control',
            }),
            'linkedin_url': forms.URLInput(attrs={
                'placeholder': 'https://linkedin.com/in/yourname', 'class': 'form-control',
            }),
            'twitter_url': forms.URLInput(attrs={
                'placeholder': 'https://twitter.com/yourhandle', 'class': 'form-control',
            }),
        }

    def clean_whatsapp_number(self):
        num = self.cleaned_data.get('whatsapp_number', '').strip()
        if num and not num.startswith('+'):
            # Normalise Nigerian numbers
            digits = num.lstrip('0')
            if len(digits) == 10 and digits.isdigit():
                num = f'+234{digits}'
        return num


# ── Portfolio Item Form ───────────────────────────────────────────────────────

class DigitalPortfolioItemForm(forms.ModelForm):
    class Meta:
        model  = DigitalPortfolioItem
        fields = ['item_type', 'title', 'description', 'image', 'external_url', 'display_order']
        widgets = {
            'item_type':    forms.Select(attrs={'class': 'form-select'}),
            'title':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Project title'}),
            'description':  forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'external_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }


# ── Digital Gig Create / Edit Form (Employer) ─────────────────────────────────

class DigitalGigForm(forms.ModelForm):
    class Meta:
        model  = DigitalGig
        fields = [
            'title', 'description', 'category', 'required_sub_skills',
            'budget_type', 'budget_min', 'budget_max',
            'work_type', 'state', 'deadline', 'status',
        ]
        widgets = {
            'title':              forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Design a logo for my fintech startup'}),
            'description':        forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'category':           forms.Select(attrs={'class': 'form-select'}),
            'required_sub_skills': forms.CheckboxSelectMultiple(),
            'budget_type':        forms.Select(attrs={'class': 'form-select'}),
            'budget_min':         forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0'}),
            'budget_max':         forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0'}),
            'work_type':          forms.Select(attrs={'class': 'form-select'}),
            'state':              forms.Select(attrs={'class': 'form-select'}),
            'deadline':           forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status':             forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned = super().clean()
        bmin = cleaned.get('budget_min')
        bmax = cleaned.get('budget_max')
        if bmin and bmax and bmin > bmax:
            raise forms.ValidationError('Budget minimum cannot exceed budget maximum.')
        return cleaned


# ── Digital Application Form (Digital Worker) ────────────────────────────────

class DigitalApplicationForm(forms.ModelForm):
    class Meta:
        model  = DigitalApplication
        fields = ['cover_note', 'proposed_rate']
        widgets = {
            'cover_note':    forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
                'placeholder': 'Tell the employer why you are perfect for this gig...',
            }),
            'proposed_rate': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '0.00', 'min': '0',
            }),
        }

    def clean_cover_note(self):
        note = self.cleaned_data.get('cover_note', '').strip()
        if len(note) < 30:
            raise forms.ValidationError(
                'Cover note must be at least 30 characters. Tell the employer about yourself!'
            )
        return note
