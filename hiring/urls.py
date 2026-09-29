"""
hiring/urls.py
==============
URL patterns for the TradeLink NG hiring / LinkedIn-mode app.

Registered in technicians/urls.py as:
    path('hire/', include('hiring.urls', namespace='hiring'))

All URLs are auth-protected at the view level (mixin).
"""

from django.urls import path

from .views import (
    # Worker — profile
    WorkerProfileEnhancedView,
    WorkHistoryCreateView,
    WorkHistoryUpdateView,
    WorkHistoryDeleteView,
    CertificationCreateView,
    CertificationDeleteView,
    WorkerEmploymentPrefView,
    # Worker — inbox & CV
    WorkerHiringInboxView,
    HiringInterestReplyView,
    CVDownloadView,
    # Endorsement (shared)
    EndorseSkillView,
    # Employer — search & profile
    TalentSearchView,
    WorkerDetailEnhancedView,
    SaveWorkerToggleView,
    SavedWorkersView,
    # Employer — outreach
    SendHiringInterestView,
    HiringOutboxView,
    UpdateHiringStatusView,
    HiringPipelineView,
)

app_name = 'hiring'

urlpatterns = [

    # ── Worker: Professional Profile Hub ────────────────────────────────────
    path(
        'profile/',
        WorkerProfileEnhancedView.as_view(),
        name='worker_profile_enhanced',
    ),
    path(
        'profile/employment-prefs/',
        WorkerEmploymentPrefView.as_view(),
        name='employment_prefs',
    ),
    path(
        'profile/cv/',
        CVDownloadView.as_view(),
        name='cv_download',
    ),

    # ── Worker: Work History ─────────────────────────────────────────────────
    path(
        'profile/history/add/',
        WorkHistoryCreateView.as_view(),
        name='history_add',
    ),
    path(
        'profile/history/<uuid:pk>/edit/',
        WorkHistoryUpdateView.as_view(),
        name='history_edit',
    ),
    path(
        'profile/history/<uuid:pk>/delete/',
        WorkHistoryDeleteView.as_view(),
        name='history_delete',
    ),

    # ── Worker: Certifications ───────────────────────────────────────────────
    path(
        'profile/certifications/add/',
        CertificationCreateView.as_view(),
        name='cert_add',
    ),
    path(
        'profile/certifications/<uuid:pk>/delete/',
        CertificationDeleteView.as_view(),
        name='cert_delete',
    ),

    # ── Worker: Inbox ─────────────────────────────────────────────────────────
    path(
        'inbox/',
        WorkerHiringInboxView.as_view(),
        name='worker_inbox',
    ),
    path(
        'inbox/<uuid:pk>/reply/',
        HiringInterestReplyView.as_view(),
        name='inbox_reply',
    ),

    # ── Shared: Skill Endorsement (AJAX, any logged-in user) ────────────────
    path(
        'workers/<uuid:pk>/endorse/<uuid:skill_pk>/',
        EndorseSkillView.as_view(),
        name='endorse_skill',
    ),

    # ── Employer: Talent Search ──────────────────────────────────────────────
    path(
        'talent/',
        TalentSearchView.as_view(),
        name='talent_search',
    ),

    # ── Employer + Public: Enhanced Worker Profile ───────────────────────────
    path(
        'workers/<uuid:pk>/',
        WorkerDetailEnhancedView.as_view(),
        name='worker_detail',
    ),
    path(
        'workers/<uuid:pk>/save/',
        SaveWorkerToggleView.as_view(),
        name='save_worker',
    ),
    path(
        'workers/<uuid:pk>/contact/',
        SendHiringInterestView.as_view(),
        name='send_interest',
    ),

    # ── Employer: Saved Workers Shortlist ────────────────────────────────────
    path(
        'saved/',
        SavedWorkersView.as_view(),
        name='saved_workers',
    ),

    # ── Employer: Outreach Management ────────────────────────────────────────
    path(
        'outreach/',
        HiringOutboxView.as_view(),
        name='outreach_list',
    ),
    path(
        'outreach/<uuid:pk>/stage/',
        UpdateHiringStatusView.as_view(),
        name='update_stage',
    ),

    # ── Employer: Hiring Pipeline ────────────────────────────────────────────
    path(
        'pipeline/',
        HiringPipelineView.as_view(),
        name='pipeline',
    ),
]
