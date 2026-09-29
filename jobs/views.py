"""
marketplace/views.py
====================
All views for the TradeLink NG marketplace app.

URL namespace: 'marketplace'

View map
────────
Public
  TradeCategoryListView        GET  /trades/
  TradeCategoryDetailView      GET  /trades/<slug>/
  JobListView                  GET  /jobs/
  JobDetailView                GET  /jobs/<pk>/
  WorkerProfilePublicView      GET  /workers/<pk>/
  EmployerProfilePublicView    GET  /employers/<pk>/

Worker (login required, must have WorkerProfile)
  WorkerDashboardView          GET  /dashboard/worker/
  WorkerProfileEditView        GET/POST /profile/worker/edit/
  PortfolioItemCreateView      GET/POST /profile/worker/portfolio/add/
  PortfolioItemDeleteView      POST /profile/worker/portfolio/<pk>/delete/
  JobApplyView                 GET/POST /jobs/<pk>/apply/
  WithdrawApplicationView      POST /applications/<pk>/withdraw/
  WorkerApplicationsView       GET  /applications/
  WorkerMatchesView            GET  /matches/           ← CLIP recommendations
  ToggleSaveJobView            POST /jobs/<pk>/save/    ← AJAX

Employer (login required, must have EmployerProfile)
  EmployerDashboardView        GET  /dashboard/employer/
  EmployerProfileEditView      GET/POST /profile/employer/edit/
  JobCreateView                GET/POST /jobs/post/
  JobUpdateView                GET/POST /jobs/<pk>/edit/
  JobDeleteView                POST /jobs/<pk>/delete/
  JobToggleStatusView          POST /jobs/<pk>/toggle-status/  ← AJAX
  JobApplicationsView          GET  /employer/jobs/<pk>/applications/
  UpdateApplicationStatusView  POST /employer/applications/<pk>/update/
  JobMatchesView               GET  /employer/jobs/<pk>/matches/ ← CLIP workers

Shared
  DashboardRedirectView        GET  /dashboard/
  NotificationListView         GET  /notifications/
  MarkNotificationReadView     POST /notifications/<pk>/read/   ← AJAX
  MarkAllNotificationsReadView POST /notifications/read-all/
  SubmitReviewView             GET/POST /reviews/submit/<pk>/   (job pk)
"""

import json
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Avg, Count, Case, When, FloatField, Value
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView,
)

from .forms import (
    WorkerProfileForm,
    PortfolioItemForm,
    EmployerProfileForm,
    JobForm,
    JobApplicationForm,
    ReviewForm,
    JobFilterForm,
)
from .models import (
    TradeCategory,
    Skill,
    WorkerProfile,
    PortfolioItem,
    EmployerProfile,
    Job,
    CLIPMatch,
    JobApplication,
    SavedJob,
    Review,
    Notification,
    Contract,
    Milestone,
)


# ──────────────────────────────────────────────────────────────────────────────
#  MIXINS
# ──────────────────────────────────────────────────────────────────────────────

class WorkerRequiredMixin(LoginRequiredMixin):
    """
    Ensures the logged-in user has a WorkerProfile.
    Redirects to the profile creation page if not.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, 'worker_profile'):
            messages.info(request, 'Please complete your worker profile first.')
            return redirect('marketplace:worker_profile_edit')
        return super().dispatch(request, *args, **kwargs)

    @property
    def worker_profile(self):
        return self.request.user.worker_profile


class EmployerRequiredMixin(LoginRequiredMixin):
    """
    Ensures the logged-in user has an EmployerProfile.
    Redirects to employer profile setup if not.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, 'employer_profile'):
            messages.info(request, 'Please set up your employer profile first.')
            return redirect('marketplace:employer_profile_edit')
        return super().dispatch(request, *args, **kwargs)

    @property
    def employer_profile(self):
        return self.request.user.employer_profile


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _unread_notification_count(user):
    """Returns the count of unread, non-deleted notifications for a user."""
    if user.is_authenticated:
        return Notification.objects.filter(
            user=user, is_read=False, is_deleted=False
        ).count()
    return 0


def _get_worker_profile_or_none(user):
    return getattr(user, 'worker_profile', None)


def _get_employer_profile_or_none(user):
    return getattr(user, 'employer_profile', None)


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — TRADE CATEGORIES
# ──────────────────────────────────────────────────────────────────────────────

class TradeCategoryListView(ListView):
    """
    /trades/  — Browse all active trade disciplines.
    Shows the count of active workers and jobs per category.
    """
    model               = TradeCategory
    template_name       = 'marketplace/trades/list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        return (
            TradeCategory.objects.filter(is_active=True)
            .annotate(
                worker_count=Count('workers', distinct=True),
                job_count=Count(
                    'jobs',
                    filter=Q(jobs__status=Job.Status.ACTIVE, jobs__deadline__gte=timezone.now().date()),
                    distinct=True,
                ),
            )
            .order_by('display_order', 'name')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = _unread_notification_count(self.request.user)
        return ctx


class TradeCategoryDetailView(DetailView):
    """
    /trades/<slug>/  — All active jobs in a specific trade.
    """
    model               = TradeCategory
    template_name       = 'marketplace/trades/detail.html'
    context_object_name = 'category'
    slug_field          = 'slug'
    slug_url_kwarg      = 'slug'

    def get_queryset(self):
        return TradeCategory.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        jobs = (
            Job.objects.filter(
                trade_category=self.object,
                status=Job.Status.ACTIVE,
                deadline__gte=timezone.now().date(),
            )
            .select_related('employer', 'trade_category')
            .prefetch_related('required_skills')
            .order_by('-created')
        )
        paginator = Paginator(jobs, 12)
        ctx['jobs']          = paginator.get_page(self.request.GET.get('page'))
        ctx['workers']       = (
            WorkerProfile.objects.filter(
                trade_category=self.object,
                availability=WorkerProfile.Availability.AVAILABLE,
            )
            .select_related('user', 'trade_category')
            .prefetch_related('skills')
            .order_by('-is_featured', '-profile_completion')[:6]
        )
        ctx['unread_count']  = _unread_notification_count(self.request.user)
        return ctx


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — JOBS
# ──────────────────────────────────────────────────────────────────────────────

class JobListView(View):
    """
    /jobs/  — Browse and filter all active job listings.
 
    Search strategy
    ───────────────
    When the user types a query (q param) we attempt semantic search first:
 
      1. Apply hard filters (trade, state, job_type, pay_type, is_remote).
      2. Pass the filtered PKs + query to semantic_job_search() which encodes
         the query with the sentence-transformer and ranks results by cosine
         similarity to each job's stored text_embedding.
      3. Re-order the queryset using reorder_queryset_by_scores().
      4. Jobs with no embedding yet (newly posted) are appended at the end
         so they are never silently dropped from results.
      5. If the sentence-transformer model is unavailable (cold start / error),
         we fall back to the original icontains filter transparently.
 
    This means "fix my generator" matches "ATS & Generator Maintenance Technician"
    even though no keyword overlaps — the model understands the intent.
    """
    template_name = 'marketplace/jobs/list.html'
    per_page      = 15
 
    def get(self, request):
        from jobs.service.search_service import semantic_job_search, reorder_queryset_by_scores
 
        form = JobFilterForm(request.GET or None)
 
        # Base queryset — always active, always select_related
        base_qs = (
            Job.objects.filter(
                status=Job.Status.ACTIVE,
                deadline__gte=timezone.now().date()
            )
            .select_related('employer', 'trade_category')
            .prefetch_related('required_skills')
        )
 
        q         = None
        trade     = None
        state     = None
        job_type  = None
        pay_type  = None
        is_remote = False
 
        if form.is_valid():
            q         = form.cleaned_data.get('q', '').strip()
            trade     = form.cleaned_data.get('trade')
            state     = form.cleaned_data.get('state')
            job_type  = form.cleaned_data.get('job_type')
            pay_type  = form.cleaned_data.get('pay_type')
            is_remote = form.cleaned_data.get('is_remote')
 
        # ── Apply hard filters first (these narrow the candidate pool) ──
        filtered_qs = base_qs
        if trade:
            filtered_qs = filtered_qs.filter(trade_category=trade)
        if state:
            filtered_qs = filtered_qs.filter(state=state)
        if job_type:
            filtered_qs = filtered_qs.filter(job_type=job_type)
        if pay_type:
            filtered_qs = filtered_qs.filter(pay_type=pay_type)
        if is_remote:
            filtered_qs = filtered_qs.filter(is_remote=True)
 
        # ── Semantic search when there is a query ──────────────────────
        used_semantic = False
 
        if q:
            # Get the PKs of jobs that passed hard filters
            filtered_pks = list(filtered_qs.values_list('pk', flat=True))
 
            ranked = semantic_job_search(query=q, job_pks=filtered_pks)
 
            if ranked:
                # Semantic search succeeded — re-order by score
                used_semantic = True
                ranked_pks    = {pk for pk, _ in ranked}
 
                # Jobs WITH embeddings, ranked
                semantic_qs = reorder_queryset_by_scores(filtered_qs, ranked)
 
                # Jobs WITHOUT embeddings yet — append at end (never hide them)
                no_embedding_qs = (
                    filtered_qs
                    .filter(pk__in=filtered_pks)
                    .exclude(pk__in=ranked_pks)
                    .filter(text_embedding__isnull=True)
                    .order_by('-created')
                )
 
                # Union: semantic results first, then unembedded jobs
                # We can't union querysets with different annotations easily,
                # so we collect PKs in order and re-fetch once.
                ordered_pks = (
                    list(semantic_qs.values_list('pk', flat=True)) +
                    list(no_embedding_qs.values_list('pk', flat=True))
                )
 
                # Rebuild a single ordered queryset using CASE WHEN
                if ordered_pks:
                    ordering = Case(
                        *[When(pk=pk, then=Value(float(pos)))
                          for pos, pk in enumerate(ordered_pks)],
                        default=Value(float(len(ordered_pks))),
                        output_field=FloatField(),
                    )
                    qs = (
                        base_qs
                        .filter(pk__in=ordered_pks)
                        .annotate(final_rank=ordering)
                        .order_by('final_rank')
                    )
                else:
                    qs = filtered_qs.none()
 
            else:
                # Semantic unavailable — fall back to icontains
                qs = filtered_qs.filter(
                    Q(title__icontains=q) |
                    Q(description__icontains=q) |
                    Q(trade_category__name__icontains=q) |
                    Q(required_skills__name__icontains=q)
                ).distinct().order_by('-created')
 
        else:
            # No query — just return hard-filtered results newest first
            qs = filtered_qs.order_by('-created')
 
        # ── Pagination ─────────────────────────────────────────────────
        paginator = Paginator(qs, self.per_page)
        jobs      = paginator.get_page(request.GET.get('page'))
 
        # ── Saved job IDs for heart icons ──────────────────────────────
        saved_ids = set()
        worker    = _get_worker_profile_or_none(request.user)
        if worker:
            saved_ids = set(
                SavedJob.objects.filter(worker=worker)
                .values_list('job_id', flat=True)
            )
 
        return render(request, self.template_name, {
            'form':          form,
            'jobs':          jobs,
            'saved_ids':     saved_ids,
            'categories':    TradeCategory.objects.filter(is_active=True),
            'total_count':   qs.count(),
            'unread_count':  _unread_notification_count(request.user),
            'used_semantic': used_semantic,   # lets template show "AI search" badge
            'search_query':  q or '',
        })

   



class JobDetailView(View):
    """
    /jobs/<pk>/  — Full job details, application form, and similar jobs.
    Increments the view counter on each unique visit (session-gated).
    """
    template_name = 'marketplace/jobs/detail.html'

    def get(self, request, pk):
        job = get_object_or_404(
            Job.objects.select_related('employer', 'trade_category')
            .prefetch_related('required_skills', 'reviews'),
            pk=pk,
            status=Job.Status.ACTIVE,
            deadline__gte=timezone.now().date(),
        )

        # Increment view counter once per session
        session_key = f'viewed_job_{pk}'
        if not request.session.get(session_key):
            Job.objects.filter(pk=pk).update(views_count=job.views_count + 1)
            request.session[session_key] = True

        # Worker-specific context
        worker         = _get_worker_profile_or_none(request.user)
        has_applied    = False
        is_saved       = False
        application    = None
        clip_score     = None

        if worker:
            application = JobApplication.objects.filter(
                job=job, worker=worker
            ).first()
            has_applied = application is not None
            is_saved    = SavedJob.objects.filter(job=job, worker=worker).exists()
            match       = CLIPMatch.objects.filter(job=job, worker=worker).first()
            clip_score  = round(match.score * 100) if match else None

        # Similar jobs (same trade category, excluding this one)
        similar_jobs = (
            Job.objects.filter(
                trade_category=job.trade_category,
                status=Job.Status.ACTIVE,
            )
            .exclude(pk=pk)
            .select_related('employer')
            .order_by('-created')[:4]
        )

        return render(request, self.template_name, {
            'job':          job,
            'form':         JobApplicationForm(),
            'has_applied':  has_applied,
            'application':  application,
            'is_saved':     is_saved,
            'clip_score':   clip_score,
            'similar_jobs': similar_jobs,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC — WORKER & EMPLOYER PROFILE PAGES
# ──────────────────────────────────────────────────────────────────────────────

class WorkerProfilePublicView(View):
    """
    /workers/<pk>/  — Public-facing worker profile page.
    Shows skills, portfolio (photos + YouTube videos), and average rating.

    The portfolio queryset selects items ordered by display_order so the
    template can render each item's image and, when present, its embedded
    YouTube video via item.get_embed_url().
    """
    template_name = 'marketplace/workers/profile.html'

    def get(self, request, pk):
        worker = get_object_or_404(
            WorkerProfile.objects.select_related('user', 'trade_category')
            .prefetch_related('skills', 'portfolio'),
            pk=pk,
        )
        reviews = (
            Review.objects.filter(
                reviewee=worker.user,
                review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
                is_visible=True,
            )
            .select_related('reviewer')
            .order_by('-created_at')
        )
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

        return render(request, self.template_name, {
            'worker':       worker,
            'reviews':      reviews,
            'avg_rating':   round(avg_rating, 1) if avg_rating else None,
            'unread_count': _unread_notification_count(request.user),
        })


class EmployerProfilePublicView(View):
    """
    /employers/<pk>/  — Public-facing employer profile page.
    Shows company info, active jobs, and worker reviews.
    """
    template_name = 'marketplace/employers/profile.html'

    def get(self, request, pk):
        employer = get_object_or_404(
            EmployerProfile.objects.select_related('user'),
            pk=pk,
        )
        active_jobs = (
            Job.objects.filter(
                employer=employer, 
                status=Job.Status.ACTIVE,
                deadline__gte=timezone.now().date()
            )
            .select_related('trade_category')
            .prefetch_related('required_skills')
            .order_by('-created')
        )
        reviews = (
            Review.objects.filter(
                reviewee=employer.user,
                review_type=Review.ReviewType.WORKER_TO_EMPLOYER,
                is_visible=True,
            )
            .select_related('reviewer')
            .order_by('-created_at')
        )
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

        return render(request, self.template_name, {
            'employer':     employer,
            'active_jobs':  active_jobs,
            'reviews':      reviews,
            'avg_rating':   round(avg_rating, 1) if avg_rating else None,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  DASHBOARD — REDIRECT
# ──────────────────────────────────────────────────────────────────────────────

class DashboardRedirectView(LoginRequiredMixin, View):
    """
    /dashboard/  — Sends users to the correct dashboard based on their profile.

    Priority order:
      1. Worker (incl. workers who are ALSO employers or sellers)
         → /dashboard/worker/   (cross-role buttons shown in template)
      2. Employer-only
         → /dashboard/employer/
      3. New user with no profile
         → choose_role.html

    Note: Any authenticated user can buy (no separate buyer profile exists).
    The Buyer order list is surfaced via nav links in the dashboards.
    """

    def get(self, request):
        user = request.user
        has_worker   = hasattr(user, 'worker_profile')
        has_employer = hasattr(user, 'employer_profile')

        # Workers always land here first — template shows buttons for other roles
        if has_worker:
            return redirect('marketplace:worker_dashboard')
        if has_employer:
            return redirect('marketplace:employer_dashboard')
        # Brand-new user — let them pick a role
        return render(request, 'marketplace/dashboard/choose_role.html', {
            'unread_count': 0,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

class WorkerDashboardView(WorkerRequiredMixin, View):
    """
    /dashboard/worker/

    Surfaces:
      • top_matches   — top 5 CLIP-recommended jobs (score desc, not yet applied)
      • recent_apps   — last 5 applications with status
      • saved_jobs    — last 4 bookmarked jobs
      • portfolio     — all portfolio items including YouTube videos
      • avg_rating    — worker's average employer-to-worker rating
      • review_count  — total visible reviews received
      • unread_count  — unread notification count for the bell icon

    The portfolio queryset is passed so the template can render each item's
    photo and, when item.has_video is True, an embedded YouTube iframe via
    item.get_embed_url().
    """
    template_name = 'marketplace/dashboard/worker.html'

    def get(self, request):
        worker = self.worker_profile

        # ── Top 5 CLIP-recommended jobs ─────────────────────────────────────
        top_matches = (
            CLIPMatch.objects.filter(
                worker=worker,
                job__status=Job.Status.ACTIVE,
                is_applied=False,
            )
            .select_related('job__employer', 'job__trade_category')
            .order_by('-score')[:5]
        )

        # ── Recent applications ──────────────────────────────────────────────
        recent_apps = (
            JobApplication.objects.filter(worker=worker)
            .select_related('job__employer')
            .order_by('-applied_at')[:5]
        )

        # ── Saved / bookmarked jobs ──────────────────────────────────────────
        saved_jobs = (
            SavedJob.objects.filter(worker=worker)
            .select_related('job__employer', 'job__trade_category')
            .order_by('-saved_at')[:4]
        )

        # ── Portfolio items (photos + YouTube videos) ────────────────────────
        portfolio_items = (
            PortfolioItem.objects.filter(worker=worker)
            .select_related('trade_context')
            .order_by('display_order', '-created')
        )

        # ── Rating summary ───────────────────────────────────────────────────
        reviews_qs = Review.objects.filter(
            reviewee=worker.user,
            review_type=Review.ReviewType.EMPLOYER_TO_WORKER,
            is_visible=True,
        )
        rating_agg   = reviews_qs.aggregate(avg=Avg('rating'))
        avg_rating   = round(rating_agg['avg'], 1) if rating_agg['avg'] else None
        review_count = reviews_qs.count()

        # ── Milestones funded — work can start ───────────────────────────
        funded_milestones = (
            Milestone.objects.filter(
                contract__worker=worker,
                status=Milestone.Status.FUNDED,
            )
            .select_related('contract', 'contract__employer__user')
            .order_by('funded_at')[:5]
        )

        # ── Total Earnings ───────────────────────────────────────────────────
        # We must sum worker_amount (net after platform fee), NOT amount
        # (the gross the employer paid into escrow).
        #
        # worker_amount is populated at payout time (release_milestone_to_worker).
        # For APPROVED milestones where the payout task hasn't run yet it may be
        # null — in that case we compute it from amount × (1 − fee_pct / 100)
        # using the contract's platform_fee_pct (default 10%).
        from decimal import Decimal
        released_milestones = Milestone.objects.filter(
            contract__worker=worker,
            status__in=[Milestone.Status.RELEASED, Milestone.Status.APPROVED],
        ).select_related('contract').values(
            'amount', 'worker_amount', 'contract__platform_fee_pct'
        )
        total_earnings = Decimal('0')
        for ms in released_milestones:
            if ms['worker_amount'] is not None:
                total_earnings += ms['worker_amount']
            else:
                fee_pct = ms['contract__platform_fee_pct'] or Decimal('10.00')
                total_earnings += ms['amount'] * (Decimal('1') - fee_pct / Decimal('100'))


        # ── Milestones in review — awaiting employer approval ────────────
        in_review_milestones = (
            Milestone.objects.filter(
                contract__worker=worker,
                status=Milestone.Status.IN_REVIEW,
            )
            .select_related('contract', 'contract__employer__user')
            .order_by('auto_release_at')[:5]
        )

        # ── Cross-role flags for sidebar navigation buttons ──────────────
        # Workers are also sellers (same WorkerProfile is used by marketplace).
        # Any logged-in user can be a buyer; surface order-list link in template.
        has_employer_profile = hasattr(request.user, 'employer_profile')

        return render(request, self.template_name, {
            'worker':                worker,
            'top_matches':           top_matches,
            'recent_apps':           recent_apps,
            'saved_jobs':            saved_jobs,
            'portfolio_items':       portfolio_items,
            'avg_rating':            avg_rating,
            'review_count':          review_count,
            'funded_milestones':     funded_milestones,
            'in_review_milestones':  in_review_milestones,
            'total_earnings':        total_earnings,
            'unread_count':          _unread_notification_count(request.user),
            # Cross-role navigation
            'has_employer_profile':  has_employer_profile,
            'is_seller':             True,   # all workers can sell on marketplace
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — PROFILE EDIT
# ──────────────────────────────────────────────────────────────────────────────

class WorkerProfileEditView(LoginRequiredMixin, View):
    """
    /profile/worker/edit/
    Creates WorkerProfile if it doesn't exist yet (first-time setup).
    Triggers CLIP embedding recomputation via signal/task on save.
    """
    template_name = 'marketplace/workers/edit.html'

    def _get_or_create_profile(self, user):
        profile, _ = WorkerProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        profile = self._get_or_create_profile(request.user)
        form    = WorkerProfileForm(instance=profile)
        return render(request, self.template_name, {
            'form':         form,
            'profile':      profile,
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request):
        profile = self._get_or_create_profile(request.user)
        form    = WorkerProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('marketplace:worker_dashboard')
        return render(request, self.template_name, {
            'form':         form,
            'profile':      profile,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — PORTFOLIO
# ──────────────────────────────────────────────────────────────────────────────

class PortfolioItemCreateView(WorkerRequiredMixin, View):
    """
    /profile/worker/portfolio/add/

    Adds a portfolio item (image + optional YouTube demo video).
    The PortfolioItemForm must include the youtube_url field so workers can
    paste a YouTube link alongside their work photo.

    After save, the image is queued for CLIP embedding by a background task.
    The youtube_url is stored as-is; the embed URL is computed at render time
    via item.get_embed_url().
    """
    template_name = 'marketplace/workers/portfolio_add.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form':         PortfolioItemForm(),
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request):
        form = PortfolioItemForm(request.POST, request.FILES)
        if form.is_valid():
            item        = form.save(commit=False)
            item.worker = self.worker_profile
            item.save()
            messages.success(request, 'Portfolio item added.')
            return redirect('marketplace:worker_profile_edit')
        return render(request, self.template_name, {
            'form':         form,
            'unread_count': _unread_notification_count(request.user),
        })


class PortfolioItemDeleteView(WorkerRequiredMixin, View):
    """
    POST /profile/worker/portfolio/<pk>/delete/
    Deletes a portfolio item that belongs to the current worker.
    """

    def post(self, request, pk):
        item = get_object_or_404(PortfolioItem, pk=pk, worker=self.worker_profile)
        item.delete()
        messages.success(request, 'Portfolio item removed.')
        return redirect('marketplace:worker_profile_edit')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — APPLY TO JOB
# ──────────────────────────────────────────────────────────────────────────────

class JobApplyView(WorkerRequiredMixin, View):
    """
    /jobs/<pk>/apply/
    Submits a job application. Captures the current CLIP score as a snapshot.
    """
    template_name = 'marketplace/jobs/apply.html'

    def _get_job(self, pk):
        return get_object_or_404(Job, pk=pk, status=Job.Status.ACTIVE, deadline__gte=timezone.now().date())

    def get(self, request, pk):
        job = self._get_job(pk)
        # Redirect if already applied
        if JobApplication.objects.filter(job=job, worker=self.worker_profile).exists():
            messages.info(request, 'You have already applied for this job.')
            return redirect('marketplace:job_detail', pk=pk)

        return render(request, self.template_name, {
            'job':          job,
            'form':         JobApplicationForm(),
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request, pk):
        job  = self._get_job(pk)
        form = JobApplicationForm(request.POST)

        if JobApplication.objects.filter(job=job, worker=self.worker_profile).exists():
            messages.info(request, 'You have already applied for this job.')
            return redirect('marketplace:job_detail', pk=pk)

        if form.is_valid():
            # Snapshot the CLIP score at application time
            match = CLIPMatch.objects.filter(
                job=job, worker=self.worker_profile
            ).first()
            clip_score = match.score if match else None

            try:
                app = JobApplication.objects.create(
                    job=job,
                    worker=self.worker_profile,
                    cover_note=form.cleaned_data.get('cover_note', ''),
                    clip_match_score=clip_score,
                )
                # Mark this match as applied so it stops appearing in recommendations
                if match:
                    match.is_applied = True
                    match.save(update_fields=['is_applied'])

                # Notify the employer
                Notification.objects.create(
                    user=job.employer.user,
                    notif_type=Notification.NotifType.NEW_APPLICATION,
                    title=f'New application: {job.title}',
                    body=(
                        f'{request.user.username} applied for your job listing.'
                    ),
                    data={
                        'job_id':         str(job.pk),
                        'application_id': str(app.pk),
                    },
                )

                messages.success(request, 'Application submitted successfully!')
                return redirect('marketplace:worker_dashboard')

            except IntegrityError:
                messages.error(request, 'You have already applied for this job.')
                return redirect('marketplace:job_detail', pk=pk)

        return render(request, self.template_name, {
            'job':          job,
            'form':         form,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — WITHDRAW APPLICATION
# ──────────────────────────────────────────────────────────────────────────────

class WithdrawApplicationView(WorkerRequiredMixin, View):
    """
    POST /applications/<pk>/withdraw/
    Allows a worker to withdraw a pending application.
    """

    def post(self, request, pk):
        application = get_object_or_404(
            JobApplication,
            pk=pk,
            worker=self.worker_profile,
            status=JobApplication.Status.PENDING,
        )
        application.status = JobApplication.Status.WITHDRAWN
        application.save(update_fields=['status', 'updated_at'])

        # Re-open the CLIPMatch so it shows up in recommendations again
        CLIPMatch.objects.filter(
            job=application.job, worker=self.worker_profile
        ).update(is_applied=False)

        messages.success(request, 'Application withdrawn.')
        return redirect('marketplace:worker_applications')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — MY APPLICATIONS
# ──────────────────────────────────────────────────────────────────────────────

class WorkerApplicationsView(WorkerRequiredMixin, View):
    """
    /applications/
    Full paginated list of a worker's applications with status badges.
    """
    template_name = 'marketplace/workers/applications.html'
    per_page      = 10

    def get(self, request):
        apps = (
            JobApplication.objects.filter(worker=self.worker_profile)
            .select_related('job__employer', 'job__trade_category')
            .order_by('-applied_at')
        )
        paginator = Paginator(apps, self.per_page)

        return render(request, self.template_name, {
            'applications': paginator.get_page(request.GET.get('page')),
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — CLIP JOB MATCHES
# ──────────────────────────────────────────────────────────────────────────────

class WorkerMatchesView(WorkerRequiredMixin, View):
    """
    /matches/
    Full paginated CLIP job recommendations for the current worker.
    """
    template_name = 'marketplace/workers/matches.html'
    per_page      = 12

    def get(self, request):
        worker  = self.worker_profile
        matches = (
            CLIPMatch.objects.filter(
                worker=worker,
                job__status=Job.Status.ACTIVE,
                is_applied=False,
            )
            .select_related('job__employer', 'job__trade_category')
            .prefetch_related('job__required_skills')
            .order_by('-score')
        )
        paginator = Paginator(matches, self.per_page)

        return render(request, self.template_name, {
            'matches':      paginator.get_page(request.GET.get('page')),
            'clip_ready':   worker.text_embedding is not None,
            'unread_count': _unread_notification_count(request.user),
            'worker':   worker,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — TOGGLE SAVE JOB  (AJAX)
# ──────────────────────────────────────────────────────────────────────────────

class ToggleSaveJobView(WorkerRequiredMixin, View):
    """
    POST /jobs/<pk>/save/  (AJAX)
    Toggles saved/unsaved state for a job.
    Returns JSON: {"saved": true|false}
    """

    def post(self, request, pk):
        job    = get_object_or_404(Job, pk=pk)
        worker = self.worker_profile
        obj, created = SavedJob.objects.get_or_create(job=job, worker=worker)
        if not created:
            obj.delete()
            return JsonResponse({'saved': False})
        return JsonResponse({'saved': True})


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

class EmployerDashboardView(EmployerRequiredMixin, View):
    """
    /dashboard/employer/
    Surfaces: active jobs (paginated + filterable), recent applications,
    pending milestones, and aggregate stats.
    """
    template_name = 'marketplace/dashboard/employer.html'
    JOBS_PER_PAGE = 8

    def get(self, request):
        employer = self.employer_profile

        # ── All jobs (used for stats + filtered queryset) ────────────────
        all_jobs = (
            Job.objects.filter(employer=employer)
            .annotate(app_count=Count('applications'))
            .order_by('-created')
        )

        # ── Status filter tab ────────────────────────────────────────────
        status_filter = request.GET.get('status', 'all')
        valid_statuses = {'active', 'paused', 'draft', 'filled', 'expired', 'closed'}
        if status_filter in valid_statuses:
            filtered_jobs = all_jobs.filter(status=status_filter)
        else:
            status_filter = 'all'
            filtered_jobs = all_jobs

        # ── Pagination ───────────────────────────────────────────────────
        paginator  = Paginator(filtered_jobs, self.JOBS_PER_PAGE)
        jobs_page  = paginator.get_page(request.GET.get('page'))

        # ── Aggregate stats (always across all jobs) ─────────────────────
        from django.db.models import Sum as _Sum
        total_jobs   = all_jobs.count()
        active_count = all_jobs.filter(status=Job.Status.ACTIVE).count()
        total_apps   = (
            JobApplication.objects.filter(job__employer=employer).count()
        )

        # ── Recent pending applications ──────────────────────────────────
        recent_apps = (
            JobApplication.objects.filter(
                job__employer=employer,
                status=JobApplication.Status.PENDING,
            )
            .select_related('job', 'worker__user')
            .order_by('-applied_at')[:8]
        )
        pending_apps_total = JobApplication.objects.filter(
            job__employer=employer,
            status=JobApplication.Status.PENDING,
        ).count()

        # ── Milestones awaiting funding ──────────────────────────────────
        pending_milestones = (
            Milestone.objects.filter(
                contract__employer=employer,
                status=Milestone.Status.UNFUNDED,
            )
            .select_related('contract', 'contract__worker__user')
            .order_by('created_at')[:5]
        )
        pending_milestones_total = (
            Milestone.objects.filter(
                contract__employer=employer,
                status=Milestone.Status.UNFUNDED,
            ).count()
        )

        # ── Cross-role flags ────────────────────────────────────────────
        has_worker_profile = hasattr(request.user, 'worker_profile')

        return render(request, self.template_name, {
            'employer':    employer,
            # Paginated / filtered job listing
            'jobs_page':       jobs_page,
            'status_filter':   status_filter,
            # Sidebar recent data
            'recent_apps':     recent_apps,
            'pending_apps_total':        pending_apps_total,
            'pending_milestones':        pending_milestones,
            'pending_milestones_total':  pending_milestones_total,
            # Aggregate stats (top row)
            'stat_total_jobs':  total_jobs,
            'stat_active_jobs': active_count,
            'stat_pending_apps': pending_apps_total,
            'stat_total_apps':  total_apps,
            'unread_count':     _unread_notification_count(request.user),
            # Cross-role navigation
            'has_worker_profile': has_worker_profile,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — PROFILE EDIT
# ──────────────────────────────────────────────────────────────────────────────

class EmployerProfileEditView(LoginRequiredMixin, View):
    """
    /profile/employer/edit/
    Creates EmployerProfile if it doesn't exist yet.
    """
    template_name = 'marketplace/employers/edit.html'

    def _get_or_create_profile(self, user):
        profile, _ = EmployerProfile.objects.get_or_create(user=user)
        return profile

    def get(self, request):
        profile = self._get_or_create_profile(request.user)
        form    = EmployerProfileForm(instance=profile)
        return render(request, self.template_name, {
            'form':         form,
            'profile':      profile,
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request):
        profile = self._get_or_create_profile(request.user)
        form    = EmployerProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company profile updated.')
            return redirect('marketplace:employer_dashboard')
        return render(request, self.template_name, {
            'form':         form,
            'profile':      profile,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — JOB CRUD
# ──────────────────────────────────────────────────────────────────────────────

class JobCreateView(EmployerRequiredMixin, View):
    """
    /jobs/post/
    """
    template_name = 'marketplace/jobs/create.html'

    def get(self, request):
        return render(request, self.template_name, {
            'form':         JobForm(),
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request):
        form = JobForm(request.POST)
        if form.is_valid():
            job          = form.save(commit=False)
            job.employer = self.employer_profile
            job.save()
            form.save_m2m()
            messages.success(request, 'Job posted successfully.')
            return redirect('marketplace:employer_dashboard')
        return render(request, self.template_name, {
            'form':         form,
            'unread_count': _unread_notification_count(request.user),
        })


class JobUpdateView(EmployerRequiredMixin, View):
    """
    /jobs/<pk>/edit/
    """
    template_name = 'marketplace/jobs/edit.html'

    def _get_job(self, pk):
        return get_object_or_404(Job, pk=pk, employer=self.employer_profile)

    def get(self, request, pk):
        job  = self._get_job(pk)
        form = JobForm(instance=job)
        return render(request, self.template_name, {
            'form':         form,
            'job':          job,
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request, pk):
        job  = self._get_job(pk)
        form = JobForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, 'Job listing updated.')
            return redirect('marketplace:employer_dashboard')
        return render(request, self.template_name, {
            'form':         form,
            'job':          job,
            'unread_count': _unread_notification_count(request.user),
        })


class JobDeleteView(EmployerRequiredMixin, View):
    """
    POST /jobs/<pk>/delete/
    """

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk, employer=self.employer_profile)
        job.delete()
        messages.success(request, 'Job listing deleted.')
        return redirect('marketplace:employer_dashboard')


class JobToggleStatusView(EmployerRequiredMixin, View):
    """
    POST /jobs/<pk>/toggle-status/  (AJAX)
    Toggles between Active ↔ Paused.
    Returns JSON: {"status": "active"|"paused"}
    """

    def post(self, request, pk):
        job = get_object_or_404(Job, pk=pk, employer=self.employer_profile)
        if job.status == Job.Status.ACTIVE:
            job.status = Job.Status.PAUSED
        elif job.status == Job.Status.PAUSED:
            job.status = Job.Status.ACTIVE
        else:
            return JsonResponse({'error': 'Cannot toggle this status.'}, status=400)
        job.save(update_fields=['status', 'updated'])
        return JsonResponse({'status': job.status})


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — JOB APPLICATIONS
# ──────────────────────────────────────────────────────────────────────────────

class JobApplicationsView(EmployerRequiredMixin, View):
    """
    /employer/jobs/<pk>/applications/
    All applications for a specific job, filterable by status.
    """
    template_name = 'marketplace/employers/applications.html'
    per_page      = 15

    def get(self, request, pk):
        job  = get_object_or_404(Job, pk=pk, employer=self.employer_profile)
        apps = (
            JobApplication.objects.filter(job=job)
            .select_related('worker__user', 'worker__trade_category')
            .prefetch_related('worker__skills')
            .order_by('-applied_at')
        )
        status_filter = request.GET.get('status')
        if status_filter:
            apps = apps.filter(status=status_filter)

        paginator = Paginator(apps, self.per_page)

        return render(request, self.template_name, {
            'job':            job,
            'applications':   paginator.get_page(request.GET.get('page')),
            'status_choices': JobApplication.Status.choices,
            'status_filter':  status_filter,
            'unread_count':   _unread_notification_count(request.user),
        })


class UpdateApplicationStatusView(EmployerRequiredMixin, View):
    """
    POST /employer/applications/<pk>/update/
    Updates the status of an application and notifies the worker.
    """

    def post(self, request, pk):
        application = get_object_or_404(
            JobApplication,
            pk=pk,
            job__employer=self.employer_profile,
        )
        new_status = request.POST.get('status')
        valid_statuses = [
            JobApplication.Status.PENDING,
            JobApplication.Status.SHORTLISTED,
            JobApplication.Status.ACCEPTED,
            JobApplication.Status.REJECTED,
        ]
        if new_status not in valid_statuses:
            messages.error(request, 'Invalid status.')
            return redirect('marketplace:job_applications', pk=application.job.pk)

        application.status       = new_status
        application.employer_note = request.POST.get('employer_note', '')
        application.save(update_fields=['status', 'employer_note', 'updated_at'])

        # Create contract if application was accepted
        if new_status == JobApplication.Status.ACCEPTED:
            Contract.objects.get_or_create(
                application=application,
                defaults={
                    'job': application.job,
                    'employer': application.job.employer,
                    'worker': application.worker,
                    'status': Contract.Status.PENDING,
                }
            )

        # Notify the worker
        status_label = dict(JobApplication.Status.choices).get(new_status, new_status)
        Notification.objects.create(
            user=application.worker.user,
            notif_type=Notification.NotifType.APPLICATION_UPDATE,
            title=f'Application update: {application.job.title}',
            body=f'Your application status is now: {status_label}.',
            data={
                'job_id':         str(application.job.pk),
                'application_id': str(application.pk),
                'new_status':     new_status,
            },
        )

        messages.success(request, f'Application status updated to {status_label}.')
        return redirect('marketplace:job_applications', pk=application.job.pk)


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — CLIP WORKER MATCHES FOR A JOB
# ──────────────────────────────────────────────────────────────────────────────

class JobMatchesView(EmployerRequiredMixin, View):
    """
    /employer/jobs/<pk>/matches/
    Shows the CLIP-recommended workers for a specific job, ordered by score.
    This is the employer's view of the AI recommendation engine.
    """
    template_name = 'marketplace/employers/matches.html'
    per_page      = 12

    def get(self, request, pk):
        job = get_object_or_404(Job, pk=pk, employer=self.employer_profile)
        matches = (
            CLIPMatch.objects.filter(job=job, score__gte=0.50)
            .select_related(
                'worker__user',
                'worker__trade_category',
            )
            .prefetch_related('worker__skills')
            .order_by('-score')
        )
        paginator = Paginator(matches, self.per_page)

        return render(request, self.template_name, {
            'job':          job,
            'matches':      paginator.get_page(request.GET.get('page')),
            'clip_ready':   job.text_embedding is not None,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  REVIEWS
# ──────────────────────────────────────────────────────────────────────────────

class SubmitReviewView(LoginRequiredMixin, View):
    """
    /reviews/submit/<pk>/   (pk = Job pk)
    Allows either party to leave a review after a job is completed/accepted.
    The correct review_type is inferred from the current user's profile type.
    """
    template_name = 'marketplace/reviews/submit.html'

    def _resolve_context(self, request, job):
        """
        Returns (review_type, reviewee) based on who is submitting the review.
        Raises Http404 if the user is not a participant in this job.
        """
        user = request.user
        # Employer reviewing the worker
        employer = _get_employer_profile_or_none(user)
        if employer and job.employer == employer:
            accepted_apps = JobApplication.objects.filter(
                job=job, status=JobApplication.Status.ACCEPTED
            ).select_related('worker__user')
            return Review.ReviewType.EMPLOYER_TO_WORKER, accepted_apps

        # Worker reviewing the employer
        worker = _get_worker_profile_or_none(user)
        if worker:
            application = JobApplication.objects.filter(
                job=job, worker=worker,
                status=JobApplication.Status.ACCEPTED,
            ).first()
            if application:
                return Review.ReviewType.WORKER_TO_EMPLOYER, [job.employer]

        raise Http404('You are not a participant in this job.')

    def get(self, request, pk):
        job            = get_object_or_404(Job, pk=pk)
        review_type, targets = self._resolve_context(request, job)
        return render(request, self.template_name, {
            'job':          job,
            'form':         ReviewForm(),
            'review_type':  review_type,
            'targets':      targets,
            'unread_count': _unread_notification_count(request.user),
        })

    def post(self, request, pk):
        job            = get_object_or_404(Job, pk=pk)
        review_type, _ = self._resolve_context(request, job)
        form           = ReviewForm(request.POST)

        if form.is_valid():
            reviewee_id = request.POST.get('reviewee_id')
            from django.contrib.auth import get_user_model
            User = get_user_model()
            reviewee = get_object_or_404(User, pk=reviewee_id)

            Review.objects.update_or_create(
                job=job,
                reviewer=request.user,
                review_type=review_type,
                defaults={
                    'reviewee': reviewee,
                    'rating':   form.cleaned_data['rating'],
                    'comment':  form.cleaned_data['comment'],
                },
            )
            # Notify reviewee
            Notification.objects.create(
                user=reviewee,
                notif_type=Notification.NotifType.NEW_REVIEW,
                title='You received a new review',
                body=f'{request.user.username} left you a {form.cleaned_data["rating"]}★ review.',
                data={'job_id': str(job.pk)},
            )
            messages.success(request, 'Review submitted. Thank you!')
            return redirect('marketplace:job_detail', pk=job.pk)

        return render(request, self.template_name, {
            'job':          job,
            'form':         form,
            'unread_count': _unread_notification_count(request.user),
        })


# ──────────────────────────────────────────────────────────────────────────────
#  NOTIFICATIONS
# ──────────────────────────────────────────────────────────────────────────────

class NotificationListView(LoginRequiredMixin, View):
    """
    /notifications/
    Lists all notifications for the current user, most recent first.
    Soft-deleted notifications are excluded from the user's view.
    """
    template_name = 'marketplace/notifications/list.html'
    per_page      = 20

    def get(self, request):
        from datetime import date, timedelta
        notifications = Notification.objects.filter(
            user=request.user,
            is_deleted=False,
        ).select_related('user').order_by('-created_at')
        paginator = Paginator(notifications, self.per_page)

        # Mark all as read when the user opens the page
        Notification.objects.filter(
            user=request.user, is_read=False, is_deleted=False
        ).update(is_read=True)

        today     = date.today()
        yesterday = today - timedelta(days=1)

        return render(request, self.template_name, {
            'notifications': paginator.get_page(request.GET.get('page')),
            'unread_count':  0,   # just marked them all read
            'today':         today,
            'yesterday':     yesterday,
        })


class MarkNotificationReadView(LoginRequiredMixin, View):
    """
    POST /notifications/<pk>/read/  (AJAX)
    Marks a single notification as read.
    Returns JSON: {"unread_count": N}
    """

    def post(self, request, pk):
        Notification.objects.filter(
            pk=pk, user=request.user
        ).update(is_read=True)
        unread = Notification.objects.filter(
            user=request.user, is_read=False, is_deleted=False
        ).count()
        return JsonResponse({'unread_count': unread})


class MarkAllNotificationsReadView(LoginRequiredMixin, View):
    """
    POST /notifications/read-all/
    Marks every notification for the current user as read.
    """

    def post(self, request):
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        messages.success(request, 'All notifications marked as read.')
        return redirect('marketplace:notifications')


class DeleteNotificationView(LoginRequiredMixin, View):
    """
    POST /notifications/<pk>/delete/
    Soft-deletes a single notification for the current user.
    The record remains in the database and is still visible in the admin.
    Returns JSON {"ok": true} for AJAX calls, or redirects for plain POST.
    """

    def post(self, request, pk):
        Notification.objects.filter(
            pk=pk, user=request.user
        ).update(is_deleted=True)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        return redirect('marketplace:notifications')


class GetCategorySkillsView(View):
    """
    GET /api/skills/?category_id=<pk>
    Returns a JSON list of skills for the given trade category.
    """
    def get(self, request):
        category_id = request.GET.get('category_id')
        if not category_id:
            return JsonResponse({'skills': []})
        
        try:
            skills = Skill.objects.filter(category_id=category_id).order_by('name')
            data = [{'id': str(skill.id), 'name': skill.name} for skill in skills]
            return JsonResponse({'skills': data})
        except ValueError:
            return JsonResponse({'skills': []}, status=400)


class GetStateLgasView(View):
    """
    GET /api/lgas/?state=<code>
    Returns a JSON list of LGAs for the given Nigerian state code.
    If no state is specified, returns all states and their LGAs.
    """
    def get(self, request):
        state_code = request.GET.get('state', '').strip().lower()
        from .locations import get_nigerian_states_lgas, get_lgas_for_state

        if not state_code:
            return JsonResponse({'states_lgas': get_nigerian_states_lgas()})

        lgas = get_lgas_for_state(state_code)
        return JsonResponse({'state': state_code, 'lgas': lgas})