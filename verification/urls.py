"""
verification/urls.py
"""

from django.urls import path
from . import views

app_name = 'verify'

urlpatterns = [
    path('',           views.VerificationDashboardView.as_view(), name='dashboard'),
    path('nin/',       views.NINVerifyView.as_view(),              name='nin'),
    path('bvn/',       views.BVNVerifyView.as_view(),              name='bvn'),
    path('cac/',       views.CACVerifyView.as_view(),              name='cac'),
    path('status/',    views.VerificationStatusView.as_view(),     name='status'),
]
