"""
marketplace/forms.py
====================
ModelForms and helper forms for the marketplace app.
Views import from here — keep this file in sync with models.py.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    WorkerProfile,
    PortfolioItem,
    EmployerProfile,
    Job,
    JobApplication,
    Review,
    Skill,
    TradeCategory,
    NIGERIAN_STATES,
)


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

class WorkerProfileForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'we-skill-check-input'}),
        required=False,
    )

    class Meta:
        model  = WorkerProfile
        fields = [
            'trade_category', 'experience_level', 'years_experience',
            'skills', 'bio', 'state', 'lga', 'is_willing_to_relocate',
            'hourly_rate', 'daily_rate', 'availability',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 5,
                'placeholder': 'Describe your skills, experience, and the kind of work you do…'}),
            'lga': forms.Select(attrs={'class': 'we-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['skills'].initial = self.instance.skills.all()

        if 'trade_category' in self.data:
            try:
                trade_id = self.data.get('trade_category')
                self.fields['skills'].queryset = Skill.objects.filter(category_id=trade_id, is_active=True)
            except (ValueError, TypeError):
                self.fields['skills'].queryset = Skill.objects.none()
        elif self.instance.pk and self.instance.trade_category:
            self.fields['skills'].queryset = Skill.objects.filter(category=self.instance.trade_category, is_active=True)
        else:
            self.fields['skills'].queryset = Skill.objects.none()

        # Dynamic Nigerian LGA choices based on selected/saved state
        from .locations import get_lgas_for_state
        state_code = None
        if 'state' in self.data:
            state_code = self.data.get('state')
        elif self.instance and self.instance.pk and self.instance.state:
            state_code = self.instance.state

        if state_code:
            lgas = get_lgas_for_state(state_code)
            lga_choices = [('', '— Select LGA —')] + [(lga_name, lga_name) for lga_name in lgas]
            # Ensure saved value is preserved even if it's custom or from legacy text input
            current_lga = self.instance.lga if (self.instance and self.instance.pk) else ''
            if current_lga and current_lga not in lgas:
                lga_choices.append((current_lga, current_lga))
            self.fields['lga'].widget = forms.Select(choices=lga_choices, attrs={'class': 'we-select'})
        else:
            self.fields['lga'].widget = forms.Select(
                choices=[('', '— Select State first —')],
                attrs={'class': 'we-select'}
            )

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            self.save_skills(profile)
        return profile

    def save_skills(self, profile):
        selected_skills = self.cleaned_data.get('skills', [])
        from .models import WorkerSkill
        
        existing_skills = WorkerSkill.objects.filter(worker=profile)
        existing_skill_ids = list(existing_skills.values_list('skill_id', flat=True))
        
        selected_ids = [s.id for s in selected_skills]
        
        for skill in selected_skills:
            if skill.id not in existing_skill_ids:
                WorkerSkill.objects.create(worker=profile, skill=skill)
                
        WorkerSkill.objects.filter(worker=profile).exclude(skill_id__in=selected_ids).delete()


class PortfolioItemForm(forms.ModelForm):
    class Meta:
        model  = PortfolioItem
        fields = ['image', 'caption', 'youtube_url', 'trade_context', 'display_order']
        widgets = {
            'caption': forms.TextInput(attrs={
                'placeholder': 'Short description of this work'
            }),
            'youtube_url': forms.URLInput(attrs={
                'placeholder': 'https://www.youtube.com/watch?v=… (optional)',
            }),
        }

# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER PROFILE
# ──────────────────────────────────────────────────────────────────────────────

class EmployerProfileForm(forms.ModelForm):
    class Meta:
        model  = EmployerProfile
        fields = [
            'company_name', 'company_type',
            'description', 'website', 'phone', 'state', 'lga',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4,
                'placeholder': 'Tell workers about your company or project…'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://'}),
            'phone': forms.TextInput(attrs={'placeholder': 'e.g. +234 801 234 5678'}),
        }

# ──────────────────────────────────────────────────────────────────────────────
#  JOB
# ──────────────────────────────────────────────────────────────────────────────

class JobForm(forms.ModelForm):
    class Meta:
        model  = Job
        fields = [
            'trade_category', 'required_skills', 'title', 'description',
            'job_type', 'pay_type', 'pay_min', 'pay_max', 'slots',
            'state', 'lga', 'is_remote', 'deadline',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6,
                'placeholder': 'Describe the job, requirements, and what you expect…'}),
            'required_skills': forms.CheckboxSelectMultiple(),
            'deadline': forms.DateInput(attrs={'type': 'date'}),
            'lga': forms.TextInput(attrs={'placeholder': 'e.g. Victoria Island'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter skills to those belonging to the selected trade category
        if 'trade_category' in self.data:
            try:
                trade_id = self.data.get('trade_category')
                self.fields['required_skills'].queryset = (
                    Skill.objects.filter(category_id=trade_id, is_active=True)
                )
            except (ValueError, TypeError):
                self.fields['required_skills'].queryset = Skill.objects.none()
        elif self.instance.pk and self.instance.trade_category:
            self.fields['required_skills'].queryset = (
                Skill.objects.filter(
                    category=self.instance.trade_category, is_active=True
                )
            )
        else:
            self.fields['required_skills'].queryset = Skill.objects.none()

    def clean(self):
        cleaned = super().clean()
        pay_min = cleaned.get('pay_min')
        pay_max = cleaned.get('pay_max')
        if pay_min and pay_max and pay_min > pay_max:
            raise ValidationError('Minimum pay cannot be greater than maximum pay.')
        return cleaned


# ──────────────────────────────────────────────────────────────────────────────
#  JOB APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

class JobApplicationForm(forms.ModelForm):
    class Meta:
        model  = JobApplication
        fields = ['cover_note']
        widgets = {
            'cover_note': forms.Textarea(attrs={'rows': 4,
                'placeholder': (
                    'Briefly introduce yourself and explain why you are '
                    'a good fit for this job…'
                )}),
        }


# ──────────────────────────────────────────────────────────────────────────────
#  REVIEW
# ──────────────────────────────────────────────────────────────────────────────

class ReviewForm(forms.ModelForm):
    class Meta:
        model  = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.RadioSelect(
                choices=[(i, f'{i} star{"s" if i > 1 else ""}') for i in range(1, 6)]
            ),
            'comment': forms.Textarea(attrs={'rows': 3,
                'placeholder': 'Share your experience…'}),
        }


# ──────────────────────────────────────────────────────────────────────────────
#  JOB SEARCH / FILTER (unbound, used in JobListView)
# ──────────────────────────────────────────────────────────────────────────────

class JobFilterForm(forms.Form):
    q        = forms.CharField(
                required=False, label='Keyword',
                widget=forms.TextInput(attrs={'placeholder': 'e.g. Electrician…'}))
    trade    = forms.ModelChoiceField(
                queryset=TradeCategory.objects.filter(is_active=True),
                required=False, label='Trade', empty_label='All Trades')
    state    = forms.ChoiceField(
                choices=[('', 'All States')] + list(NIGERIAN_STATES),
                required=False, label='State')
    job_type = forms.ChoiceField(
                choices=[('', 'All Types')] + list(Job.JobType.choices),
                required=False, label='Job Type')
    pay_type = forms.ChoiceField(
                choices=[('', 'Any Pay Type')] + list(Job.PayType.choices),
                required=False, label='Pay Type')
    is_remote = forms.BooleanField(required=False, label='Remote only')