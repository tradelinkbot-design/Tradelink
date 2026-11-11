"""blog/forms.py — Comment submission form."""
from django import forms
from .models import Comment


class CommentForm(forms.ModelForm):
    class Meta:
        model  = Comment
        fields = ['body']
        widgets = {
            'body': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Share your thoughts…',
                'class': 'form-control',
            }),
        }
        labels = {'body': ''}
