"""
hiring/forms.py
===============
Forms for the TradeLink NG hiring / LinkedIn-mode app.

Forms
─────
  WorkHistoryForm          — add / edit a past job entry
  CertificationForm        — add a trade certificate
  TalentSearchForm         — employer searches the worker pool
  HiringInterestForm       — employer sends direct outreach to a worker
  HiringInterestReplyForm  — worker replies (interested / declined + message)
  WorkerEmploymentPrefForm — worker updates Open-to-Work preferences
"""

from django import forms
from django.core.exceptions import ValidationError
import datetime

from .models import WorkHistory, Certification, HiringInterest
from jobs.models import (
    TradeCategory,
    WorkerProfile,
    NIGERIAN_STATES,
)


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — WORK HISTORY
# ──────────────────────────────────────────────────────────────────────────────

class WorkHistoryForm(forms.ModelForm):
    class Meta:
        model  = WorkHistory
        fields = [
            'employer_name', 'role_title', 'trade_category',
            'description', 'start_date', 'end_date',
            'is_current', 'location_state',
        ]
        widgets = {
            'employer_name': forms.TextInput(attrs={
                'placeholder': 'e.g. Julius Berger Nigeria, Dangote Refinery, Self-Employed'
            }),
            'role_title': forms.TextInput(attrs={
                'placeholder': 'e.g. Lead Electrician, Site Foreman, Master Plumber'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': (
                    'Describe what you did: projects completed, tools used, '
                    'team size, achievements…'
                ),
            }),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date':   forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'is_current': 'I currently work here',
        }

    def clean(self):
        cleaned = super().clean()
        start    = cleaned.get('start_date')
        end      = cleaned.get('end_date')
        current  = cleaned.get('is_current')

        if current and end:
            raise ValidationError(
                'A current role cannot have an end date. '
                'Either clear the end date or untick "I currently work here".'
            )
        if not current and not end:
            raise ValidationError(
                'Please enter an end date, or tick "I currently work here".'
            )
        if start and end and end < start:
            raise ValidationError('End date cannot be earlier than start date.')
        if start and start > datetime.date.today():
            raise ValidationError('Start date cannot be in the future.')
        return cleaned


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — CERTIFICATION
# ──────────────────────────────────────────────────────────────────────────────

class CertificationForm(forms.ModelForm):
    class Meta:
        model  = Certification
        fields = ['name', 'issuing_body', 'year_obtained', 'certificate_image']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g. NABTEB Electrical Installation Certificate'
            }),
            'issuing_body': forms.TextInput(attrs={
                'placeholder': 'e.g. NABTEB, SON, City & Guilds, COREN, ITF'
            }),
            'year_obtained': forms.NumberInput(attrs={
                'placeholder': 'e.g. 2020', 'min': 1980, 'max': 2100
            }),
        }
        help_texts = {
            'certificate_image': (
                'Upload a photo or scan of your certificate. '
                'Admins will review it and add a verified badge to your profile.'
            ),
        }


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — EMPLOYMENT PREFERENCES
#  (fields added to WorkerProfile in jobs/models.py)
# ──────────────────────────────────────────────────────────────────────────────

class WorkerEmploymentPrefForm(forms.ModelForm):
    """
    Lets a worker update their Open-to-Work status, salary expectations,
    and employment type preference.  Bound to the WorkerProfile model.
    """

    class Meta:
        model  = WorkerProfile
        fields = [
            'open_to_employment',
            'employment_preference',
            'expected_monthly_salary',
            'notice_period',
        ]
        widgets = {
            'expected_monthly_salary': forms.NumberInput(attrs={
                'placeholder': 'e.g. 150000',
            }),
            'notice_period': forms.TextInput(attrs={
                'placeholder': 'e.g. Available immediately, 2 weeks, 1 month',
            }),
        }
        labels = {
            'open_to_employment': 'I am open to being contacted by employers',
            'expected_monthly_salary': 'Expected monthly salary (₦)',
        }
        help_texts = {
            'open_to_employment': (
                'Turning this on shows an "Open to Work" badge on your profile '
                'and makes you discoverable in employer talent searches.'
            ),
        }


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — TALENT SEARCH
# ──────────────────────────────────────────────────────────────────────────────

class TalentSearchForm(forms.Form):
    """
    Employer-facing search form for the talent pool.

    All fields are optional.  With no filters applied, returns all workers
    ordered by profile_completion desc.  With a keyword, the AI matching
    engine re-orders results by cosine similarity.
    """

    keyword = forms.CharField(
        required=False,
        label='Keyword / AI Job Description',
        widget=forms.TextInput(attrs={
            'class': 'form-control search-keyword-input',
            'placeholder': 'e.g. Solar panel installer with inverter & battery experience in Lagos...',
            'autocomplete': 'off',
        }),
        help_text='Powered by AI — describe the role or skills in plain English.',
    )
    trade = forms.ModelChoiceField(
        queryset=TradeCategory.objects.filter(is_active=True),
        required=False,
        empty_label='All Trades',
        label='Trade / Discipline',
        widget=forms.Select(attrs={'class': 'form-control select-custom'}),
    )
    state = forms.ChoiceField(
        choices=[('', 'All States')] + list(NIGERIAN_STATES),
        required=False,
        label='State / Location',
        widget=forms.Select(attrs={'class': 'form-control select-custom'}),
    )
    experience_level = forms.ChoiceField(
        choices=[('', 'Any Experience Level')] + list(WorkerProfile.ExperienceLevel.choices),
        required=False,
        label='Experience Level',
        widget=forms.Select(attrs={'class': 'form-control select-custom'}),
    )
    employment_preference = forms.ChoiceField(
        choices=[
            ('', 'Any Employment Type'),
            ('full_time',  'Full-Time Only'),
            ('part_time',  'Part-Time Only'),
            ('either',     'Open to Either'),
        ],
        required=False,
        label='Employment Type',
        widget=forms.Select(attrs={'class': 'form-control select-custom'}),
    )
    open_to_work_only = forms.BooleanField(
        required=False,
        initial=False,
        label='Only show workers open to employment',
        widget=forms.CheckboxInput(attrs={'class': 'custom-checkbox'}),
    )
    verified_only = forms.BooleanField(
        required=False,
        initial=False,
        label='Verified workers only',
        widget=forms.CheckboxInput(attrs={'class': 'custom-checkbox'}),
    )


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — HIRING INTEREST (direct outreach)
# ──────────────────────────────────────────────────────────────────────────────

class HiringInterestForm(forms.ModelForm):
    """
    Employer fills this out when contacting a worker directly.
    """

    class Meta:
        model  = HiringInterest
        fields = ['job', 'message', 'salary_offer']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': (
                    'Introduce your company, describe the role, '
                    'and explain why you think this worker is a great fit…'
                ),
            }),
            'salary_offer': forms.NumberInput(attrs={
                'placeholder': 'e.g. 200000 (optional)',
            }),
        }
        labels = {
            'job':          'Link to a job posting (optional)',
            'salary_offer': 'Indicative monthly salary offer (₦, optional)',
        }
        help_texts = {
            'salary_offer': (
                'Showing a salary range increases response rates by ~40%. '
                'Workers can see this but it is not legally binding.'
            ),
        }

    def __init__(self, *args, employer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if employer:
            # Only show the employer's own active full-time / contract jobs
            from jobs.models import Job
            self.fields['job'].queryset = Job.objects.filter(
                employer=employer,
                status=Job.Status.ACTIVE,
                job_type__in=[Job.JobType.FULL_TIME, Job.JobType.PART_TIME, Job.JobType.CONTRACT],
            )
        self.fields['job'].required = False


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — HIRING INTEREST REPLY
# ──────────────────────────────────────────────────────────────────────────────

class HiringInterestReplyForm(forms.Form):
    """
    Worker responds to an employer's outreach.
    """

    RESPONSE_CHOICES = [
        ('interested', '✅ I am Interested — please get in touch'),
        ('declined',   '❌ No thanks — I am not interested at this time'),
    ]

    response = forms.ChoiceField(
        choices=RESPONSE_CHOICES,
        widget=forms.RadioSelect,
        label='Your Response',
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': (
                'Optional: add a message to the employer, '
                'e.g. your availability, preferred contact method, questions…'
            ),
        }),
        label='Message to employer (optional)',
    )
