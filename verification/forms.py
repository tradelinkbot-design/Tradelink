"""
verification/forms.py
=====================
Forms for the three verification tiers: NIN, BVN, CAC.
"""

from django import forms


class NINForm(forms.Form):
    nin = forms.CharField(
        label='National Identification Number (NIN)',
        max_length=11,
        min_length=11,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your 11-digit NIN',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'maxlength': '11',
            'class': 'ver-input',
            'id': 'id_nin',
        }),
        help_text='Your 11-digit NIN as shown on your NIMC slip or National ID card.',
    )

    def clean_nin(self):
        nin = self.cleaned_data['nin'].strip()
        if not nin.isdigit():
            raise forms.ValidationError('NIN must contain digits only.')
        if len(nin) != 11:
            raise forms.ValidationError('NIN must be exactly 11 digits.')
        return nin


class BVNForm(forms.Form):
    bvn = forms.CharField(
        label='Bank Verification Number (BVN)',
        max_length=11,
        min_length=11,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your 11-digit BVN',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'maxlength': '11',
            'class': 'ver-input',
            'id': 'id_bvn',
        }),
        help_text='Your 11-digit BVN. Dial *565*0# on any MTN/Airtel line to retrieve it.',
    )

    def clean_bvn(self):
        bvn = self.cleaned_data['bvn'].strip()
        if not bvn.isdigit():
            raise forms.ValidationError('BVN must contain digits only.')
        if len(bvn) != 11:
            raise forms.ValidationError('BVN must be exactly 11 digits.')
        return bvn


class CACForm(forms.Form):
    rc_number = forms.CharField(
        label='CAC Registration Number (RC Number)',
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. RC1234567',
            'autocomplete': 'off',
            'class': 'ver-input',
            'id': 'id_rc_number',
        }),
        help_text='Your company RC Number from the Corporate Affairs Commission (CAC).',
    )
    company_name = forms.CharField(
        label='Registered Company Name',
        max_length=200,
        widget=forms.TextInput(attrs={
            'placeholder': 'Full registered company name',
            'class': 'ver-input',
            'id': 'id_company_name',
        }),
    )

    def clean_rc_number(self):
        rc = self.cleaned_data['rc_number'].strip().upper()
        # Strip leading "RC" prefix if the user typed it
        if rc.startswith('RC'):
            rc = rc[2:]
        if not rc:
            raise forms.ValidationError('Please enter a valid RC number.')
        return rc
