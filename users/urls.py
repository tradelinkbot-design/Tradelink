from django.urls import path
from django.contrib.auth import views as auth_views

from .views import (
    RegisterView,
    SignInView,
    SignOutView,
    EditProfileView,
    BankAccountProfileView,
    BankResolveAPIView,
    BankListAPIView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('signin/',   SignInView.as_view(),   name='signin'),
    path('signout/',  SignOutView.as_view(),   name='signout'),

    # ── Profile & Bank Account ───────────────────────────────────────────────
    path('profile/edit/',         EditProfileView.as_view(),        name='edit_profile'),
    path('profile/bank-account/', BankAccountProfileView.as_view(), name='bank_account_profile'),
    path('bank-resolve/',         BankResolveAPIView.as_view(),     name='bank_resolve'),
    path('bank-list/',            BankListAPIView.as_view(),         name='bank_list'),

    # ── Password reset ──────────────────────────────────────────────────────
    path(
        'password-reset/',
        PasswordResetRequestView.as_view(),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html'
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/confirm/<uidb64>/<token>/',
        PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html'
        ),
        name='password_reset_complete',
    ),
]