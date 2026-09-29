from django.shortcuts import render
from django.db.models import Count, Q


def homepage(request):
    """
    Homepage view — passes all real data from the database so the template
    has zero hardcoded content.

    Context keys:
      categories      — active TradeCategory objects, annotated with
                        job_count and worker_count, limited to 8 for the grid
      all_categories  — all active categories (for autocomplete JS array)
      featured_jobs   — 5 most recent ACTIVE jobs
      total_workers   — count of all WorkerProfile rows
      total_jobs      — count of all ACTIVE Job rows
      total_employers — count of all EmployerProfile rows
      nigerian_states — NIGERIAN_STATES choices list (for state dropdown)
    """
    from jobs.models import (
        TradeCategory,
        Job,
        WorkerProfile,
        EmployerProfile,
        NIGERIAN_STATES,
    )

    # ── Trade categories (grid + autocomplete) ───────────────────────────────
    all_categories = (
        TradeCategory.objects.filter(is_active=True)
        .annotate(
            job_count=Count(
                'jobs',
                filter=Q(jobs__status=Job.Status.ACTIVE),
                distinct=True,
            ),
            worker_count=Count('workers', distinct=True),
        )
        .order_by('display_order', 'name')
    )

    # First 8 for the homepage grid, all for the autocomplete JS
    categories = all_categories[:8]

    # ── Featured jobs — latest 5 active ─────────────────────────────────────
    featured_jobs = (
        Job.objects.filter(status=Job.Status.ACTIVE)
        .select_related('employer', 'trade_category')
        .prefetch_related('required_skills')
        .order_by('-created')[:5]
    )

    # ── Trust bar stats ──────────────────────────────────────────────────────
    total_workers   = WorkerProfile.objects.count()
    total_jobs      = Job.objects.filter(status=Job.Status.ACTIVE).count()
    total_employers = EmployerProfile.objects.count()

    return render(request, 'jobs/index.html', {
        'categories':      categories,
        'all_categories':  all_categories,
        'featured_jobs':   featured_jobs,
        'total_workers':   total_workers,
        'total_jobs':      total_jobs,
        'total_employers': total_employers,
        'nigerian_states': NIGERIAN_STATES,
    })


def login_user(request):
    return render(request, 'jobs/login.html')


def about_us(request):
    """
    Comprehensive About Us view detailing TradeLink NG's mission, ecosystem,
    trust & verification system, and milestones for artisans and employers across Nigeria.
    """
    from jobs.models import (
        TradeCategory,
        WorkerProfile,
        Job,
        EmployerProfile,
        NIGERIAN_STATES,
    )

    total_workers   = WorkerProfile.objects.count()
    total_jobs      = Job.objects.filter(status=Job.Status.ACTIVE).count()
    total_employers = EmployerProfile.objects.count()
    categories      = TradeCategory.objects.filter(is_active=True).order_by('display_order', 'name')
    total_trades    = categories.count()

    return render(request, 'about.html', {
        'total_workers':         total_workers,
        'total_jobs':            total_jobs,
        'total_employers':       total_employers,
        'categories':            categories,
        'total_trades':          total_trades or 36,
        'nigerian_states_count': len(NIGERIAN_STATES) if NIGERIAN_STATES else 37,
    })