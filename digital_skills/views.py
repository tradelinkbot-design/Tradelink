"""
digital_skills/views.py
=======================
Views for the Digital Skills section of TradeLink NG.

URL namespace: 'digital'

View map
────────
  Public
    DigitalWorkerDirectoryView    GET  /digital/
    DigitalPublicProfileView      GET  /digital/profile/<username>/
    DigitalGigListView            GET  /digital/gigs/
    DigitalGigDetailView          GET  /digital/gigs/<uuid:pk>/

  Auth — digital_worker only
    DigitalProfileSetupView      GET/POST /digital/profile/setup/
    DigitalProfileEditView       GET/POST /digital/profile/edit/
    DigitalPortfolioView         GET/POST /digital/portfolio/
    DigitalPortfolioDeleteView   POST     /digital/portfolio/<uuid:pk>/delete/
    DigitalWorkerDashboardView   GET      /digital/dashboard/
    DigitalApplyView             POST     /digital/gigs/<uuid:pk>/apply/
    DigitalMyApplicationsView    GET      /digital/my-applications/
    DigitalToggleSaveGigView     POST     /digital/gigs/<uuid:pk>/save/

  Auth — employer only
    DigitalGigCreateView         GET/POST /digital/gigs/create/
    DigitalGigEditView           GET/POST /digital/gigs/<uuid:pk>/edit/
    DigitalGigDeleteView         POST     /digital/gigs/<uuid:pk>/delete/
    DigitalGigApplicantsView     GET      /digital/gigs/<uuid:pk>/applicants/
    DigitalApplicationActionView POST     /digital/applications/<uuid:pk>/action/
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q, F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from .models import (
    DigitalSkillCategory,
    DigitalSubSkill,
    DigitalWorkerProfile,
    DigitalPortfolioItem,
    DigitalGig,
    DigitalApplication,
    SavedDigitalGig,
    DigitalWorkerReview,
)
from .forms import (
    DigitalWorkerProfileForm,
    DigitalPortfolioItemForm,
    DigitalGigForm,
    DigitalApplicationForm,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  MIXINS
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerRequiredMixin(LoginRequiredMixin):
    """Only users with account_type == 'digital_worker' may access this view."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.account_type != 'digital_worker':
            messages.warning(
                request,
                'This section is only available to Digital Skilled Worker accounts.',
            )
            return redirect('jobs:home')
        return super().dispatch(request, *args, **kwargs)

    @property
    def digital_profile(self) -> DigitalWorkerProfile:
        profile, _ = DigitalWorkerProfile.objects.get_or_create(
            user=self.request.user
        )
        return profile


class EmployerRequiredMixin(LoginRequiredMixin):
    """Only users with account_type == 'employer' may post/manage gigs."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.account_type != 'employer':
            messages.warning(request, 'Only employer accounts can post gigs.')
            return redirect('digital:gig_list')
        if not hasattr(request.user, 'employer_profile'):
            messages.warning(request, 'Please complete your employer profile first.')
            return redirect('jobs:employer_profile_edit')
        return super().dispatch(request, *args, **kwargs)

    @property
    def employer_profile(self):
        return self.request.user.employer_profile


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC VIEWS
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerDirectoryView(View):
    """
    Public directory of digital workers.
    Searchable by category, sub-skill, location, and free text.
    """
    template_name = 'digital_skills/directory.html'

    def get(self, request):
        qs = DigitalWorkerProfile.objects.select_related(
            'user', 'primary_category'
        ).prefetch_related('sub_skills').filter(
            profile_completion__gte=30,
        ).order_by('-is_featured', '-profile_completion', '-created')

        # ── Filters ──────────────────────────────────────────────────────
        category_slug = request.GET.get('category', '').strip()
        sub_skill_slug = request.GET.get('sub_skill', '').strip()
        state          = request.GET.get('state', '').strip()
        q              = request.GET.get('q', '').strip()
        availability   = request.GET.get('availability', '').strip()
        experience     = request.GET.get('experience', '').strip()

        if category_slug:
            qs = qs.filter(primary_category__slug=category_slug)
        if sub_skill_slug:
            qs = qs.filter(sub_skills__slug=sub_skill_slug)
        if state:
            qs = qs.filter(state=state)
        if availability:
            qs = qs.filter(availability=availability)
        if experience:
            qs = qs.filter(experience_level=experience)
        if q:
            qs = qs.filter(
                Q(headline__icontains=q) |
                Q(bio__icontains=q) |
                Q(user__username__icontains=q) |
                Q(primary_category__name__icontains=q) |
                Q(sub_skills__name__icontains=q)
            ).distinct()

        paginator = Paginator(qs, 20)
        page      = paginator.get_page(request.GET.get('page', 1))

        return render(request, self.template_name, {
            'page_obj':   page,
            'categories': DigitalSkillCategory.objects.filter(is_active=True).order_by('display_order'),
            'q':           q,
            'filters': {
                'category_slug': category_slug,
                'sub_skill_slug': sub_skill_slug,
                'state':         state,
                'availability':  availability,
                'experience':    experience,
            },
        })


class DigitalPublicProfileView(View):
    """Public profile page for a digital worker."""
    template_name = 'digital_skills/public_profile.html'

    def get(self, request, username):
        profile = get_object_or_404(
            DigitalWorkerProfile.objects.select_related(
                'user', 'primary_category'
            ).prefetch_related('sub_skills', 'portfolio_items'),
            user__username=username,
        )
        reviews = DigitalWorkerReview.objects.filter(
            worker=profile, is_public=True
        ).select_related('reviewer').order_by('-created')[:10]

        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg']

        return render(request, self.template_name, {
            'profile':    profile,
            'reviews':    reviews,
            'avg_rating': avg_rating,
            'can_contact': request.user.is_authenticated,
        })


class DigitalGigListView(View):
    """Public gig board — all active digital gigs."""
    template_name = 'digital_skills/gigs/gig_list.html'

    def get(self, request):
        qs = DigitalGig.objects.filter(status=DigitalGig.Status.ACTIVE).select_related(
            'employer', 'category'
        ).prefetch_related('required_sub_skills').order_by('-created')

        category_slug = request.GET.get('category', '').strip()
        work_type     = request.GET.get('work_type', '').strip()
        state         = request.GET.get('state', '').strip()
        q             = request.GET.get('q', '').strip()

        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        if work_type:
            qs = qs.filter(work_type=work_type)
        if state:
            qs = qs.filter(state=state)
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(category__name__icontains=q) |
                Q(required_sub_skills__name__icontains=q)
            ).distinct()

        paginator = Paginator(qs, 15)
        page      = paginator.get_page(request.GET.get('page', 1))

        # Saved gig PKs for authenticated users
        saved_pks = set()
        if request.user.is_authenticated:
            saved_pks = set(
                SavedDigitalGig.objects.filter(user=request.user)
                .values_list('gig_id', flat=True)
            )

        return render(request, self.template_name, {
            'page_obj':   page,
            'categories': DigitalSkillCategory.objects.filter(is_active=True),
            'saved_pks':  saved_pks,
            'q':           q,
            'filters': {
                'category_slug': category_slug,
                'work_type':     work_type,
                'state':         state,
            },
        })


class DigitalGigDetailView(View):
    """Detail page for a single digital gig."""
    template_name = 'digital_skills/gigs/gig_detail.html'

    def get(self, request, pk):
        gig = get_object_or_404(
            DigitalGig.objects.select_related('employer', 'category')
                              .prefetch_related('required_sub_skills'),
            pk=pk,
        )
        # Increment views
        DigitalGig.objects.filter(pk=pk).update(views_count=F('views_count') + 1)

        has_applied = False
        is_saved    = False
        if request.user.is_authenticated:
            if request.user.account_type == 'digital_worker':
                try:
                    dwp = request.user.digital_worker_profile
                    has_applied = DigitalApplication.objects.filter(
                        gig=gig, worker=dwp
                    ).exists()
                except DigitalWorkerProfile.DoesNotExist:
                    pass
            is_saved = SavedDigitalGig.objects.filter(user=request.user, gig=gig).exists()

        return render(request, self.template_name, {
            'gig':         gig,
            'has_applied': has_applied,
            'is_saved':    is_saved,
            'apply_form':  DigitalApplicationForm() if not has_applied else None,
        })


# ──────────────────────────────────────────────────────────────────────────────
#  DIGITAL WORKER VIEWS
# ──────────────────────────────────────────────────────────────────────────────

class DigitalWorkerDashboardView(DigitalWorkerRequiredMixin, View):
    """Dashboard for a logged-in digital worker."""
    template_name = 'digital_skills/dashboard.html'

    def get(self, request):
        profile = self.digital_profile
        recent_apps = DigitalApplication.objects.filter(
            worker=profile
        ).select_related('gig', 'gig__category').order_by('-created')[:10]
        recent_gigs = DigitalGig.objects.filter(
            status=DigitalGig.Status.ACTIVE
        ).order_by('-created')[:6]

        return render(request, self.template_name, {
            'profile':     profile,
            'recent_apps': recent_apps,
            'recent_gigs': recent_gigs,
        })


class DigitalProfileSetupView(DigitalWorkerRequiredMixin, View):
    """Initial profile setup wizard for a new digital worker."""
    template_name = 'digital_skills/profile_setup.html'

    def get(self, request):
        profile = self.digital_profile
        form    = DigitalWorkerProfileForm(instance=profile)
        return render(request, self.template_name, {
            'form':       form,
            'profile':    profile,
            'categories': DigitalSkillCategory.objects.filter(is_active=True).prefetch_related('sub_skills'),
        })

    def post(self, request):
        profile = self.digital_profile
        form    = DigitalWorkerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Your profile has been saved!')
            return redirect('digital:dashboard')
        return render(request, self.template_name, {
            'form':       form,
            'profile':    profile,
            'categories': DigitalSkillCategory.objects.filter(is_active=True).prefetch_related('sub_skills'),
        })


class DigitalProfileEditView(DigitalWorkerRequiredMixin, View):
    """Edit an existing digital worker profile."""
    template_name = 'digital_skills/profile_edit.html'

    def get(self, request):
        form = DigitalWorkerProfileForm(instance=self.digital_profile)
        return render(request, self.template_name, {
            'form':    form,
            'profile': self.digital_profile,
            'categories': DigitalSkillCategory.objects.filter(is_active=True).prefetch_related('sub_skills'),
        })

    def post(self, request):
        profile = self.digital_profile
        form    = DigitalWorkerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Profile updated successfully.')
            return redirect('digital:public_profile', username=request.user.username)
        return render(request, self.template_name, {
            'form':    form,
            'profile': profile,
            'categories': DigitalSkillCategory.objects.filter(is_active=True).prefetch_related('sub_skills'),
        })


class DigitalSubSkillsAjaxView(View):
    """Returns sub-skills for a given category as JSON (for dynamic form dropdowns)."""

    def get(self, request):
        cat_slug = request.GET.get('category', '')
        sub_skills = DigitalSubSkill.objects.filter(
            category__slug=cat_slug, is_active=True
        ).values('id', 'name', 'slug')
        return JsonResponse({'sub_skills': list(sub_skills)})


class DigitalPortfolioView(DigitalWorkerRequiredMixin, View):
    """List and add portfolio items."""
    template_name = 'digital_skills/portfolio.html'

    def get(self, request):
        items = DigitalPortfolioItem.objects.filter(worker=self.digital_profile).order_by('display_order')
        form  = DigitalPortfolioItemForm()
        return render(request, self.template_name, {
            'items':   items,
            'form':    form,
            'profile': self.digital_profile,
        })

    def post(self, request):
        profile = self.digital_profile
        form    = DigitalPortfolioItemForm(request.POST, request.FILES)
        if form.is_valid():
            item        = form.save(commit=False)
            item.worker = profile
            item.save()
            messages.success(request, '✅ Portfolio item added.')
            return redirect('digital:portfolio')
        items = DigitalPortfolioItem.objects.filter(worker=profile).order_by('display_order')
        return render(request, self.template_name, {
            'items':   items,
            'form':    form,
            'profile': profile,
        })


class DigitalPortfolioDeleteView(DigitalWorkerRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(DigitalPortfolioItem, pk=pk, worker=self.digital_profile)
        item.delete()
        messages.success(request, 'Portfolio item removed.')
        return redirect('digital:portfolio')


class DigitalApplyView(DigitalWorkerRequiredMixin, View):
    """Submit an application to a digital gig."""

    def post(self, request, pk):
        gig = get_object_or_404(DigitalGig, pk=pk, status=DigitalGig.Status.ACTIVE)
        profile = self.digital_profile

        if DigitalApplication.objects.filter(gig=gig, worker=profile).exists():
            messages.warning(request, 'You have already applied to this gig.')
            return redirect('digital:gig_detail', pk=pk)

        form = DigitalApplicationForm(request.POST)
        if form.is_valid():
            app        = form.save(commit=False)
            app.gig    = gig
            app.worker = profile
            app.save()
            # Bump applications count
            DigitalGig.objects.filter(pk=pk).update(applications_count=F('applications_count') + 1)
            messages.success(request, '✅ Application submitted! The employer will be in touch.')
            return redirect('digital:gig_detail', pk=pk)

        messages.error(request, 'Please fix the errors below.')
        return redirect('digital:gig_detail', pk=pk)


class DigitalMyApplicationsView(DigitalWorkerRequiredMixin, View):
    """List all applications submitted by this digital worker, with status filter + pagination."""
    template_name = 'digital_skills/my_applications.html'
    PAGE_SIZE = 10

    def get(self, request):
        status_filter = request.GET.get('status', '').strip()
        qs = DigitalApplication.objects.filter(
            worker=self.digital_profile
        ).select_related('gig', 'gig__category', 'gig__employer', 'gig__employer__user')

        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.order_by('-created')
        paginator   = Paginator(qs, self.PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj    = paginator.get_page(page_number)

        return render(request, self.template_name, {
            'page_obj':       page_obj,
            'profile':        self.digital_profile,
            'current_status': status_filter,
        })


class DigitalWithdrawApplicationView(DigitalWorkerRequiredMixin, View):
    """Digital worker withdraws a pending application."""

    def post(self, request, pk):
        app = get_object_or_404(
            DigitalApplication,
            pk=pk,
            worker=self.digital_profile,
            status=DigitalApplication.Status.PENDING,
        )
        app.status = DigitalApplication.Status.WITHDRAWN
        app.save(update_fields=['status', 'updated'])
        messages.success(request, 'Application withdrawn successfully.')
        return redirect('digital:my_applications')


class DigitalToggleSaveGigView(LoginRequiredMixin, View):
    """AJAX: save / unsave a digital gig."""

    def post(self, request, pk):
        gig  = get_object_or_404(DigitalGig, pk=pk)
        obj, created = SavedDigitalGig.objects.get_or_create(user=request.user, gig=gig)
        if not created:
            obj.delete()
            return JsonResponse({'saved': False})
        return JsonResponse({'saved': True})


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER VIEWS
# ──────────────────────────────────────────────────────────────────────────────

class DigitalGigCreateView(EmployerRequiredMixin, View):
    """Employer posts a new digital gig."""
    template_name = 'digital_skills/gigs/gig_form.html'

    def get(self, request):
        form = DigitalGigForm()
        return render(request, self.template_name, {
            'form':   form,
            'action': 'Create',
        })

    def post(self, request):
        form = DigitalGigForm(request.POST)
        if form.is_valid():
            gig          = form.save(commit=False)
            gig.employer = self.employer_profile
            gig.save()
            form.save_m2m()
            messages.success(request, '✅ Gig posted! Digital workers can now discover and apply.')
            return redirect('digital:gig_detail', pk=gig.pk)
        return render(request, self.template_name, {'form': form, 'action': 'Create'})


class DigitalGigEditView(EmployerRequiredMixin, View):
    """Employer edits their gig."""
    template_name = 'digital_skills/gigs/gig_form.html'

    def get_gig(self, pk):
        return get_object_or_404(DigitalGig, pk=pk, employer=self.employer_profile)

    def get(self, request, pk):
        gig  = self.get_gig(pk)
        form = DigitalGigForm(instance=gig)
        return render(request, self.template_name, {'form': form, 'gig': gig, 'action': 'Edit'})

    def post(self, request, pk):
        gig  = self.get_gig(pk)
        form = DigitalGigForm(request.POST, instance=gig)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Gig updated.')
            return redirect('digital:gig_detail', pk=pk)
        return render(request, self.template_name, {'form': form, 'gig': gig, 'action': 'Edit'})


class DigitalGigDeleteView(EmployerRequiredMixin, View):
    def post(self, request, pk):
        gig = get_object_or_404(DigitalGig, pk=pk, employer=self.employer_profile)
        gig.delete()
        messages.success(request, 'Gig deleted.')
        return redirect('digital:gig_list')


class DigitalGigApplicantsView(EmployerRequiredMixin, View):
    """Employer reviews applications for their gig."""
    template_name = 'digital_skills/gigs/gig_applicants.html'

    def get(self, request, pk):
        gig  = get_object_or_404(DigitalGig, pk=pk, employer=self.employer_profile)
        apps = DigitalApplication.objects.filter(gig=gig).select_related(
            'worker', 'worker__user', 'worker__primary_category'
        ).order_by('-created')
        return render(request, self.template_name, {
            'gig':          gig,
            'applications': apps,
        })


class DigitalApplicationActionView(EmployerRequiredMixin, View):
    """Employer shortlists / rejects / hires an applicant."""

    def post(self, request, pk):
        app    = get_object_or_404(DigitalApplication, pk=pk,
                                    gig__employer=self.employer_profile)
        action = request.POST.get('action', '').strip()
        note   = request.POST.get('employer_note', '').strip()

        status_map = {
            'shortlist': DigitalApplication.Status.SHORTLISTED,
            'reject':    DigitalApplication.Status.REJECTED,
            'hire':      DigitalApplication.Status.HIRED,
        }

        if action not in status_map:
            messages.error(request, 'Invalid action.')
            return redirect('digital:gig_applicants', pk=app.gig.pk)

        app.status        = status_map[action]
        app.employer_note = note
        app.save(update_fields=['status', 'employer_note', 'updated'])
        messages.success(request, f'Application marked as {app.get_status_display()}.')
        return redirect('digital:gig_applicants', pk=app.gig.pk)
