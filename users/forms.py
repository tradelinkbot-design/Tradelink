from django import forms
from django.contrib.auth import authenticate
from .models import User


class RegisterForm(forms.ModelForm):
    """
    Registration form for the 3-step wizard template.

    Step 1  – account_type (hidden field, set by JS)
    Step 2  – first_name, last_name, username, email, phone_number
    Step 3  – password1, password2, terms (checkbox — validated client-side
               and server-side)
    """

    # ── Non-model fields ──────────────────────────────────────────────────────
    account_type = forms.ChoiceField(
        choices=[('worker', 'Tradesperson'), ('employer', 'Employer')],
        widget=forms.HiddenInput,
        required=False,
        initial='worker',
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        min_length=8,
        error_messages={
            'min_length': 'Password must be at least 8 characters long.',
        },
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone_number']

    # ── Field-level cleaning ──────────────────────────────────────────────────

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        import re
        if not re.match(r'^[a-zA-Z0-9_]{3,}$', username):
            raise forms.ValidationError(
                'Username must be at least 3 characters and contain only '
                'letters, numbers, and underscores.'
            )
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('That username is already taken.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_phone_number(self):
        """
        The template renders a static +234 prefix and only submits the local
        digits (up to 10).  We reconstruct the full E.164 number here.
        Requires PHONENUMBER_DEFAULT_REGION = 'NG' in settings.py so that
        PhoneNumberField accepts local digits before this method runs.
        """
        raw = self.cleaned_data.get('phone_number', '')
        raw_str = str(raw).strip()

        if raw_str.startswith('+'):
            # PhoneNumberField already validated and normalised the number
            # (e.g. '+2348012345678'). Run the duplicate check on this path too.
            full_number = raw_str
        else:
            # Fallback: raw local digits submitted without country code.
            digits = raw_str.replace(' ', '').lstrip('0')
            if not digits.isdigit() or len(digits) != 10:
                raise forms.ValidationError(
                    'Enter a valid 10-digit Nigerian mobile number (e.g. 8012345678).'
                )
            full_number = f'+234{digits}'

        if User.objects.filter(phone_number=full_number).exists():
            raise forms.ValidationError('An account with this phone number already exists.')

        return full_number

    # ── Cross-field validation ────────────────────────────────────────────────

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get('password1')
        pw2 = cleaned.get('password2')

        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError('Passwords do not match.')

        return cleaned

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """
    Email + password login form.
    Works with the custom User model that has USERNAME_FIELD = 'email'.
    """

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'id': 'email',
            'name': 'email',
            'class': 'form-control has-icon',
            'placeholder': 'yourname@email.com',
            'autocomplete': 'email',
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'id': 'password',
            'name': 'password',
            'class': 'form-control has-icon',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
            'style': 'padding-right: 44px;',
        })
    )

    # Populated by clean() so the view can call login() directly
    _authenticated_user = None

    def clean(self):
        cleaned_data = super().clean()
        email    = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            user = authenticate(username=email, password=password)

            if user is None:
                raise forms.ValidationError(
                    'Invalid email or password. Please try again.'
                )

            if not user.is_active:
                raise forms.ValidationError(
                    'This account has been deactivated. Please contact support.'
                )

            self._authenticated_user = user

        return cleaned_data

    def get_user(self):
        """Return the authenticated User instance after a successful clean()."""
        return self._authenticated_user