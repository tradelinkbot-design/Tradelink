"""
hiring/views.py
===============
All views for the TradeLink NG hiring / LinkedIn-mode app.

URL namespace: 'hiring'

View map
────────
Worker-side
  WorkHistoryCreateView       GET/POST /hire/profile/history/add/
  WorkHistoryUpdateView       GET/POST /hire/profile/history/<pk>/edit/
  WorkHistoryDeleteView       POST     /hire/profile/history/<pk>/delete/
  CertificationCreateView     GET/POST /hire/profile/certifications/add/
  CertificationDeleteView     POST     /hire/profile/certifications/<pk>/delete/
  WorkerEmploymentPrefView    GET/POST /hire/profile/employment-prefs/
  WorkerHiringInboxView       GET      /hire/inbox/
  HiringInterestReplyView     POST     /hire/inbox/<pk>/reply/
  CVDownloadView              GET      /hire/profile/cv/
  EndorseSkillView            POST     /hire/workers/<pk>/endorse/<skill_pk>/  (AJAX)

Employer-side
  TalentSearchView            GET      /hire/talent/
  WorkerDetailEnhancedView    GET      /hire/workers/<pk>/
  SaveWorkerToggleView        POST     /hire/workers/<pk>/save/   (AJAX)
  SavedWorkersView            GET      /hire/saved/
  SendHiringInterestView      GET/POST /hire/workers/<pk>/contact/
  HiringOutboxView            GET      /hire/outreach/
  UpdateHiringStatusView      POST     /hire/outreach/<pk>/stage/ (AJAX)
  HiringPipelineView          GET      /hire/pipeline/
"""

import json
import logging
import numpy as np

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Avg, Q
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView, UpdateView, DeleteView, ListView, DetailView, TemplateView,
)

from jobs.models import (
    WorkerProfile, EmployerProfile, Skill, Notification,
)
from .models import (
    WorkHistory, Certification, SkillEndorsement,
    SavedWorker, HiringInterest,
)
from .forms import (
    WorkHistoryForm, CertificationForm, WorkerEmploymentPrefForm,
    TalentSearchForm, HiringInterestForm, HiringInterestReplyForm,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  MIXINS
# ──────────────────────────────────────────────────────────────────────────────

class WorkerRequiredMixin(LoginRequiredMixin):
    """Ensures the logged-in user has a WorkerProfile."""

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
    """Ensures the logged-in user has an EmployerProfile."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not hasattr(request.user, 'employer_profile'):
            messages.info(request, 'Please complete your employer profile first.')
            return redirect('marketplace:employer_profile_edit')
        return super().dispatch(request, *args, **kwargs)

    @property
    def employer_profile(self):
        return self.request.user.employer_profile


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _cosine_similarity(vec_a, vec_b):
    """Compute cosine similarity between two numpy arrays."""
    if vec_a is None or vec_b is None:
        return 0.0
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — WORK HISTORY CRUD
# ──────────────────────────────────────────────────────────────────────────────

class WorkHistoryCreateView(WorkerRequiredMixin, View):
    template_name = 'hiring/work_history_form.html'

    def get(self, request):
        form = WorkHistoryForm()
        return render(request, self.template_name, {
            'form': form, 'action': 'Add', 'page_title': 'Add Work Experience',
        })

    def post(self, request):
        form = WorkHistoryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.worker = self.worker_profile
            entry.save()
            messages.success(request, 'Work experience added successfully.')
            return redirect('hiring:worker_profile_enhanced')
        return render(request, self.template_name, {
            'form': form, 'action': 'Add', 'page_title': 'Add Work Experience',
        })


class WorkHistoryUpdateView(WorkerRequiredMixin, View):
    template_name = 'hiring/work_history_form.html'

    def _get_entry(self, pk):
        return get_object_or_404(WorkHistory, pk=pk, worker=self.worker_profile)

    def get(self, request, pk):
        entry = self._get_entry(pk)
        form = WorkHistoryForm(instance=entry)
        return render(request, self.template_name, {
            'form': form, 'action': 'Edit', 'page_title': 'Edit Work Experience',
        })

    def post(self, request, pk):
        entry = self._get_entry(pk)
        form = WorkHistoryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, 'Work experience updated.')
            return redirect('hiring:worker_profile_enhanced')
        return render(request, self.template_name, {
            'form': form, 'action': 'Edit', 'page_title': 'Edit Work Experience',
        })


class WorkHistoryDeleteView(WorkerRequiredMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(WorkHistory, pk=pk, worker=self.worker_profile)
        entry.delete()
        messages.success(request, 'Work experience removed.')
        return redirect('hiring:worker_profile_enhanced')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — CERTIFICATION CRUD
# ──────────────────────────────────────────────────────────────────────────────

class CertificationCreateView(WorkerRequiredMixin, View):
    template_name = 'hiring/certification_form.html'

    def get(self, request):
        form = CertificationForm()
        return render(request, self.template_name, {
            'form': form, 'page_title': 'Add Certification',
        })

    def post(self, request):
        form = CertificationForm(request.POST, request.FILES)
        if form.is_valid():
            cert = form.save(commit=False)
            cert.worker = self.worker_profile
            cert.save()
            messages.success(request, 'Certification added. It will be reviewed and verified by our team.')
            return redirect('hiring:worker_profile_enhanced')
        return render(request, self.template_name, {
            'form': form, 'page_title': 'Add Certification',
        })


class CertificationDeleteView(WorkerRequiredMixin, View):
    def post(self, request, pk):
        cert = get_object_or_404(Certification, pk=pk, worker=self.worker_profile)
        cert.delete()
        messages.success(request, 'Certification removed.')
        return redirect('hiring:worker_profile_enhanced')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — EMPLOYMENT PREFERENCES
# ──────────────────────────────────────────────────────────────────────────────

class WorkerEmploymentPrefView(WorkerRequiredMixin, View):
    template_name = 'hiring/employment_prefs.html'

    def get(self, request):
        form = WorkerEmploymentPrefForm(instance=self.worker_profile)
        return render(request, self.template_name, {
            'form': form, 'page_title': 'Open to Work Settings',
        })

    def post(self, request):
        form = WorkerEmploymentPrefForm(request.POST, instance=self.worker_profile)
        if form.is_valid():
            form.save()
            status = 'on' if self.worker_profile.open_to_employment else 'off'
            messages.success(request, f'Open to Work is now {status}. Your profile has been updated.')
            return redirect('hiring:worker_profile_enhanced')
        return render(request, self.template_name, {
            'form': form, 'page_title': 'Open to Work Settings',
        })


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — ENHANCED PROFILE VIEW (own profile editing hub)
# ──────────────────────────────────────────────────────────────────────────────

class WorkerProfileEnhancedView(WorkerRequiredMixin, View):
    """
    Worker's own professional profile management page —
    shows all hiring-mode sections in one place.
    """
    template_name = 'hiring/worker_profile_enhanced.html'

    def get(self, request):
        worker = self.worker_profile
        context = {
            'worker':          worker,
            'work_history':    worker.work_history.select_related('trade_category').all(),
            'certifications':  worker.certifications.all(),
            'endorsements':    (
                SkillEndorsement.objects
                .filter(worker=worker)
                .values('skill__name', 'skill__id')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'inbox_count':     HiringInterest.objects.filter(
                worker=worker,
                status=HiringInterest.Status.SENT,
            ).count(),
            'page_title': 'My Professional Profile',
        }
        return render(request, self.template_name, context)


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — HIRING INBOX
# ──────────────────────────────────────────────────────────────────────────────

class WorkerHiringInboxView(WorkerRequiredMixin, View):
    template_name = 'hiring/worker_inbox.html'

    def get(self, request):
        worker = self.worker_profile
        interests = (
            HiringInterest.objects
            .filter(worker=worker)
            .select_related('employer__user', 'job')
            .order_by('-sent_at')
        )
        # Mark all SENT as VIEWED upon inbox open
        unviewed = interests.filter(status=HiringInterest.Status.SENT)
        unviewed.update(status=HiringInterest.Status.VIEWED, viewed_at=timezone.now())

        return render(request, self.template_name, {
            'interests': interests,
            'page_title': 'Hiring Inbox',
        })


class HiringInterestReplyView(WorkerRequiredMixin, View):
    def post(self, request, pk):
        interest = get_object_or_404(
            HiringInterest, pk=pk, worker=self.worker_profile,
        )
        # Only allow reply if not already resolved
        if interest.status in (HiringInterest.Status.HIRED, HiringInterest.Status.DECLINED):
            messages.warning(request, 'This conversation is already closed.')
            return redirect('hiring:worker_inbox')

        form = HiringInterestReplyForm(request.POST)
        if form.is_valid():
            response   = form.cleaned_data['response']
            msg        = form.cleaned_data.get('message', '')
            interest.status       = response
            interest.worker_reply = msg
            interest.responded_at = timezone.now()
            interest.save()

            # Notify employer
            Notification.objects.create(
                user       = interest.employer.user,
                notif_type = 'hiring_interest_replied',
                title      = f'{request.user.get_full_name() or request.user.username} replied to your outreach',
                body       = (
                    f'They are {"interested" if response == "interested" else "not interested"} '
                    f'in the role{" for " + interest.job.title if interest.job else ""}.'
                ),
                data       = {'interest_id': str(interest.pk)},
            )
            messages.success(request, 'Your reply has been sent to the employer.')
        return redirect('hiring:worker_inbox')


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — CV DOWNLOAD
# ──────────────────────────────────────────────────────────────────────────────

class CVDownloadView(WorkerRequiredMixin, View):
    def get(self, request):
        from .cv_generator import generate_cv_pdf
        worker = self.worker_profile

        # Build absolute URL to the worker's public profile for the QR code.
        # Falls back gracefully if the worker has no pk yet (shouldn't happen).
        try:
            profile_path = reverse('hiring:worker_detail', kwargs={'pk': worker.pk})
            profile_url  = request.build_absolute_uri(profile_path)
        except Exception:
            profile_url = ''

        try:
            pdf_bytes = generate_cv_pdf(worker, profile_url=profile_url)
        except Exception as e:
            logger = logging.getLogger('technicians')
            logger.error("CV generation failed for worker %s: %s", worker.pk, e, exc_info=True)
            messages.error(request, 'Unable to generate CV at this time. Please try again later.')
            return redirect('hiring:worker_profile_enhanced')

        name = (
            worker.user.get_full_name().replace(' ', '_')
            or worker.user.username
        )
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{name}_TradeLink_CV.pdf"'
        return response


# ──────────────────────────────────────────────────────────────────────────────
#  WORKER — SKILL ENDORSEMENT (AJAX)
# ──────────────────────────────────────────────────────────────────────────────

class EndorseSkillView(LoginRequiredMixin, View):
    """
    POST /hire/workers/<pk>/endorse/<skill_pk>/
    Toggles a skill endorsement. Returns JSON for AJAX calls.
    """

    def post(self, request, pk, skill_pk):
        worker = get_object_or_404(WorkerProfile, pk=pk)
        skill  = get_object_or_404(Skill, pk=skill_pk, workers=worker)

        # Self-endorsement guard
        if hasattr(request.user, 'worker_profile') and request.user.worker_profile == worker:
            if _is_ajax(request):
                return JsonResponse({'error': 'You cannot endorse your own skills.'}, status=400)
            messages.error(request, 'You cannot endorse your own skills.')
            return redirect('hiring:worker_detail', pk=pk)

        obj, created = SkillEndorsement.objects.get_or_create(
            worker=worker, skill=skill, endorsed_by=request.user,
        )
        if not created:
            obj.delete()
            action = 'removed'
        else:
            action = 'added'
            # Notify the worker
            Notification.objects.create(
                user       = worker.user,
                notif_type = 'skill_endorsed',
                title      = f'{request.user.get_full_name() or request.user.username} endorsed your {skill.name} skill',
                body       = '',
                data       = {'worker_id': str(pk)},
            )

        count = SkillEndorsement.objects.filter(worker=worker, skill=skill).count()
        if _is_ajax(request):
            return JsonResponse({'action': action, 'count': count})
        return redirect('hiring:worker_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — TALENT SEARCH
# ──────────────────────────────────────────────────────────────────────────────

class TalentSearchView(EmployerRequiredMixin, View):
    """
    Core LinkedIn-mode view.  Employers search and filter the worker pool.
    With a keyword the AI sentence-transformer re-ranks results by similarity.
    """
    template_name = 'hiring/talent_search.html'
    paginate_by   = 20

    def get(self, request):
        form    = TalentSearchForm(request.GET or None)
        workers = WorkerProfile.objects.select_related(
            'user', 'trade_category',
        ).prefetch_related('skills').order_by(
            '-is_featured', '-profile_completion',
        )

        keyword          = ''
        ai_ranked        = False

        if form.is_valid():
            data = form.cleaned_data

            keyword = data.get('keyword', '').strip()

            if data.get('trade'):
                workers = workers.filter(trade_category=data['trade'])
            if data.get('state'):
                workers = workers.filter(state=data['state'])
            if data.get('experience_level'):
                workers = workers.filter(experience_level=data['experience_level'])
            if data.get('open_to_work_only'):
                workers = workers.filter(open_to_employment=True)
            if data.get('verified_only'):
                workers = workers.filter(is_verified=True)
            if data.get('employment_preference'):
                pref = data['employment_preference']
                workers = workers.filter(
                    Q(employment_preference=pref) | Q(employment_preference='either')
                )

            # ── AI / semantic keyword ranking ─────────────────────────────
            if keyword:
                from hiring.service.search_service import (
                    semantic_worker_search,
                    reorder_workers_by_scores,
                )
                from django.db.models import Case, When, FloatField, Value

                # Collect the PKs of workers that passed the hard filters
                filtered_pks = list(workers.values_list('pk', flat=True))

                ranked = semantic_worker_search(
                    query=keyword,
                    worker_pks=filtered_pks,
                )

                if ranked:
                    # Semantic search succeeded ─────────────────────────────
                    ai_ranked  = True
                    ranked_pks = {pk for pk, _ in ranked}

                    # Workers WITH embeddings, ordered by semantic score
                    semantic_qs = reorder_workers_by_scores(workers, ranked)

                    # Workers WITHOUT embeddings yet (newly updated) — append
                    # at the end if they match the keyword textually
                    no_embed_qs = (
                        workers
                        .filter(pk__in=filtered_pks)
                        .exclude(pk__in=ranked_pks)
                        .filter(text_embedding__isnull=True)
                        .filter(
                            Q(user__first_name__icontains=keyword) |
                            Q(user__last_name__icontains=keyword) |
                            Q(user__username__icontains=keyword) |
                            Q(trade_category__name__icontains=keyword) |
                            Q(bio__icontains=keyword) |
                            Q(skills__name__icontains=keyword)
                        )
                        .order_by('-profile_completion', '-is_featured')
                    )

                    # Build a single ordered queryset via CASE WHEN
                    ordered_pks = (
                        list(semantic_qs.values_list('pk', flat=True)) +
                        list(no_embed_qs.values_list('pk', flat=True))
                    )

                    if ordered_pks:
                        ordering = Case(
                            *[
                                When(pk=pk, then=Value(float(pos)))
                                for pos, pk in enumerate(ordered_pks)
                            ],
                            default=Value(float(len(ordered_pks))),
                            output_field=FloatField(),
                        )
                        workers = (
                            WorkerProfile.objects
                            .select_related('user', 'trade_category')
                            .prefetch_related('skills')
                            .filter(pk__in=ordered_pks)
                            .annotate(final_rank=ordering)
                            .order_by('final_rank')
                        )
                    else:
                        workers = workers.none()

                else:
                    # Celery unavailable / query too short → icontains fallback
                    workers = workers.filter(
                        Q(user__first_name__icontains=keyword) |
                        Q(user__last_name__icontains=keyword) |
                        Q(user__username__icontains=keyword) |
                        Q(trade_category__name__icontains=keyword) |
                        Q(bio__icontains=keyword) |
                        Q(skills__name__icontains=keyword)
                    ).distinct().order_by('-profile_completion', '-is_featured')

        # ── Pagination ────────────────────────────────────────────────────────
        from django.core.paginator import Paginator
        paginator = Paginator(workers, self.paginate_by)
        page_obj  = paginator.get_page(request.GET.get('page'))

        # ── Saved worker IDs for the current employer (to pre-tick hearts) ──
        saved_ids = set(
            SavedWorker.objects.filter(employer=self.employer_profile)
            .values_list('worker_id', flat=True)
        )

        # Force-evaluate the page queryset NOW (in this thread/connection)
        # before the template renderer touches it. Under ASGI, lazy queryset
        # evaluation during template rendering can cross thread boundaries and
        # invalidate the PostgreSQL server-side cursor, causing:
        #   OperationalError: cursor "..." does not exist
        _ = list(page_obj.object_list)

        return render(request, self.template_name, {
            'form':       form,
            'page_obj':   page_obj,
            'saved_ids':  saved_ids,
            'ai_ranked':  ai_ranked,
            'keyword':    keyword,
            'page_title': 'Talent Search',
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — ENHANCED WORKER DETAIL (LinkedIn-style public profile)
# ──────────────────────────────────────────────────────────────────────────────

class WorkerDetailEnhancedView(LoginRequiredMixin, View):
    """
    Full LinkedIn-style profile for a worker.
    Visible to any logged-in user; employers see extra actions (Save / Contact).
    """
    template_name = 'hiring/worker_detail.html'

    def get(self, request, pk):
        worker = get_object_or_404(
            WorkerProfile.objects.select_related('user', 'trade_category'),
            pk=pk,
        )

        # All endorsement counts keyed by skill id
        endorsement_counts = {
            row['skill__id']: row['count']
            for row in (
                SkillEndorsement.objects
                .filter(worker=worker)
                .values('skill__id')
                .annotate(count=Count('id'))
            )
        }

        # All skills the worker has listed, merged with their endorsement counts.
        # This ensures endorsement buttons appear even on skills with 0 endorsements.
        all_skills = worker.skills.all()
        skills_with_counts = [
            {
                'skill': skill,
                'count': endorsement_counts.get(skill.pk, 0),
            }
            for skill in all_skills
        ]

        # Did this user already endorse any skill?
        my_endorsed_skill_ids = set(
            SkillEndorsement.objects
            .filter(worker=worker, endorsed_by=request.user)
            .values_list('skill_id', flat=True)
        ) if request.user.is_authenticated else set()

        is_saved = False
        existing_interest = None
        if hasattr(request.user, 'employer_profile'):
            is_saved = SavedWorker.objects.filter(
                employer=request.user.employer_profile,
                worker=worker,
            ).exists()
            existing_interest = HiringInterest.objects.filter(
                employer=request.user.employer_profile,
                worker=worker,
            ).first()

        avg_rating = worker.user.reviews_received.filter(
            is_visible=True,
        ).aggregate(avg=Avg('rating'))['avg']

        context = {
            'worker':                worker,
            'skills_with_counts':    skills_with_counts,
            'work_history':          worker.work_history.select_related('trade_category').all(),
            'certifications':        worker.certifications.all(),
            'portfolio':             worker.portfolio.all(),
            'reviews':               worker.user.reviews_received.filter(is_visible=True).order_by('-created_at')[:5],
            'my_endorsed_skill_ids': my_endorsed_skill_ids,
            'is_saved':              is_saved,
            'existing_interest':     existing_interest,
            'avg_rating':            round(avg_rating, 1) if avg_rating else None,
            'page_title':            f'{worker.user.get_full_name() or worker.user.username} — Profile',
        }
        return render(request, self.template_name, context)


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — SAVE WORKER TOGGLE (AJAX)
# ──────────────────────────────────────────────────────────────────────────────

class SaveWorkerToggleView(EmployerRequiredMixin, View):
    def post(self, request, pk):
        worker = get_object_or_404(WorkerProfile, pk=pk)
        obj, created = SavedWorker.objects.get_or_create(
            employer=self.employer_profile,
            worker=worker,
        )
        if not created:
            obj.delete()
            saved = False
        else:
            saved = True
            Notification.objects.create(
                user       = worker.user,
                notif_type = 'profile_saved',
                title      = 'An employer saved your profile',
                body       = 'Your profile caught an employer\'s attention. Keep it updated!',
                data       = {'worker_id': str(pk)},
            )

        if _is_ajax(request):
            return JsonResponse({'saved': saved})
        return redirect('hiring:worker_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — SAVED WORKERS SHORTLIST
# ──────────────────────────────────────────────────────────────────────────────

class SavedWorkersView(EmployerRequiredMixin, View):
    template_name = 'hiring/saved_workers.html'

    def get(self, request):
        saved = (
            SavedWorker.objects
            .filter(employer=self.employer_profile)
            .select_related('worker__user', 'worker__trade_category')
            .order_by('-saved_at')
        )
        return render(request, self.template_name, {
            'saved_list': saved,
            'page_title': 'Saved Workers',
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — SEND HIRING INTEREST (direct outreach)
# ──────────────────────────────────────────────────────────────────────────────

class SendHiringInterestView(EmployerRequiredMixin, View):
    template_name = 'hiring/send_interest.html'

    def _get_worker(self, pk):
        return get_object_or_404(
            WorkerProfile.objects.select_related('user'),
            pk=pk,
        )

    def get(self, request, pk):
        worker = self._get_worker(pk)
        # Check for duplicate (same employer + worker + no job)
        existing = HiringInterest.objects.filter(
            employer=self.employer_profile,
            worker=worker,
            job=None,
        ).first()
        if existing:
            messages.info(request, 'You have already sent an outreach to this worker.')
            return redirect('hiring:outreach_list')

        form = HiringInterestForm(employer=self.employer_profile)
        return render(request, self.template_name, {
            'form':   form,
            'worker': worker,
            'page_title': f'Contact {worker.user.get_full_name() or worker.user.username}',
        })

    def post(self, request, pk):
        worker = self._get_worker(pk)
        form   = HiringInterestForm(request.POST, employer=self.employer_profile)
        if form.is_valid():
            interest          = form.save(commit=False)
            interest.employer = self.employer_profile
            interest.worker   = worker
            interest.save()

            # Notify the worker
            Notification.objects.create(
                user       = worker.user,
                notif_type = 'hiring_interest_received',
                title      = f'{self.employer_profile.company_name or request.user.username} wants to hire you',
                body       = interest.message[:200],
                data       = {'interest_id': str(interest.pk)},
            )
            messages.success(
                request,
                f'Your outreach has been sent to '
                f'{worker.user.get_full_name() or worker.user.username}. '
                f'You\'ll be notified when they respond.'
            )
            return redirect('hiring:outreach_list')

        return render(request, self.template_name, {
            'form':   form,
            'worker': worker,
            'page_title': f'Contact {worker.user.get_full_name() or worker.user.username}',
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — OUTREACH LIST (sent messages)
# ──────────────────────────────────────────────────────────────────────────────

class HiringOutboxView(EmployerRequiredMixin, View):
    template_name = 'hiring/outreach_list.html'

    def get(self, request):
        outreach = (
            HiringInterest.objects
            .filter(employer=self.employer_profile)
            .select_related('worker__user', 'worker__trade_category', 'job')
            .order_by('-sent_at')
        )
        return render(request, self.template_name, {
            'outreach':   outreach,
            'statuses':   HiringInterest.Status,
            'page_title': 'Hiring Outreach',
        })


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — UPDATE HIRING STATUS (AJAX — move candidate through pipeline)
# ──────────────────────────────────────────────────────────────────────────────

class UpdateHiringStatusView(EmployerRequiredMixin, View):
    """
    POST /hire/outreach/<pk>/stage/
    Body: {"status": "hired"} or {"status": "declined"}
    """

    ALLOWED_TRANSITIONS = {
        HiringInterest.Status.INTERESTED: [HiringInterest.Status.HIRED],
        HiringInterest.Status.VIEWED:     [HiringInterest.Status.DECLINED],
        HiringInterest.Status.SENT:       [HiringInterest.Status.DECLINED],
    }

    def post(self, request, pk):
        interest = get_object_or_404(
            HiringInterest, pk=pk, employer=self.employer_profile,
        )
        try:
            body       = json.loads(request.body)
            new_status = body.get('status')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        allowed = self.ALLOWED_TRANSITIONS.get(interest.status, [])
        if new_status not in [s.value for s in allowed]:
            return JsonResponse(
                {'error': f'Cannot transition from {interest.status} to {new_status}.'},
                status=400,
            )

        interest.status = new_status
        interest.save(update_fields=['status'])
        return JsonResponse({'status': new_status})


# ──────────────────────────────────────────────────────────────────────────────
#  EMPLOYER — HIRING PIPELINE (kanban overview)
# ──────────────────────────────────────────────────────────────────────────────

class HiringPipelineView(EmployerRequiredMixin, View):
    """
    Kanban-style view grouping all outreach by status.
    """
    template_name = 'hiring/hiring_pipeline.html'

    def get(self, request):
        base_qs = (
            HiringInterest.objects
            .filter(employer=self.employer_profile)
            .select_related('worker__user', 'worker__trade_category', 'job')
        )

        pipeline = {
            'sent':       base_qs.filter(status=HiringInterest.Status.SENT),
            'viewed':     base_qs.filter(status=HiringInterest.Status.VIEWED),
            'interested': base_qs.filter(status=HiringInterest.Status.INTERESTED),
            'hired':      base_qs.filter(status=HiringInterest.Status.HIRED),
            'declined':   base_qs.filter(status=HiringInterest.Status.DECLINED),
        }

        return render(request, self.template_name, {
            'pipeline':   pipeline,
            'page_title': 'Hiring Pipeline',
        })
