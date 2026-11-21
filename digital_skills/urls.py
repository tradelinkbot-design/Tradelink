"""digital_skills/urls.py"""
from django.urls import path
from . import views

app_name = 'digital'

urlpatterns = [
    # ── Public ──────────────────────────────────────────────────────────────
    path('',                                   views.DigitalWorkerDirectoryView.as_view(), name='directory'),
    path('profile/<str:username>/',            views.DigitalPublicProfileView.as_view(),   name='public_profile'),
    path('gigs/',                              views.DigitalGigListView.as_view(),          name='gig_list'),
    path('gigs/<uuid:pk>/',                    views.DigitalGigDetailView.as_view(),        name='gig_detail'),
    path('ajax/sub-skills/',                   views.DigitalSubSkillsAjaxView.as_view(),    name='ajax_sub_skills'),

    # ── Digital Worker ───────────────────────────────────────────────────────
    path('dashboard/',                         views.DigitalWorkerDashboardView.as_view(),  name='dashboard'),
    path('profile/setup/',                     views.DigitalProfileSetupView.as_view(),     name='profile_setup'),
    path('profile/edit/',                      views.DigitalProfileEditView.as_view(),      name='profile_edit'),
    path('portfolio/',                         views.DigitalPortfolioView.as_view(),        name='portfolio'),
    path('portfolio/<uuid:pk>/delete/',        views.DigitalPortfolioDeleteView.as_view(),  name='portfolio_delete'),
    path('gigs/<uuid:pk>/apply/',              views.DigitalApplyView.as_view(),            name='apply'),
    path('my-applications/',                   views.DigitalMyApplicationsView.as_view(),   name='my_applications'),
    path('gigs/<uuid:pk>/save/',               views.DigitalToggleSaveGigView.as_view(),    name='save_gig'),
    path('applications/<uuid:pk>/withdraw/',  views.DigitalWithdrawApplicationView.as_view(), name='withdraw_application'),

    # ── Employer ─────────────────────────────────────────────────────────────
    path('gigs/create/',                       views.DigitalGigCreateView.as_view(),        name='gig_create'),
    path('gigs/<uuid:pk>/edit/',               views.DigitalGigEditView.as_view(),          name='gig_edit'),
    path('gigs/<uuid:pk>/delete/',             views.DigitalGigDeleteView.as_view(),        name='gig_delete'),
    path('gigs/<uuid:pk>/applicants/',         views.DigitalGigApplicantsView.as_view(),    name='gig_applicants'),
    path('applications/<uuid:pk>/action/',     views.DigitalApplicationActionView.as_view(), name='application_action'),
]
