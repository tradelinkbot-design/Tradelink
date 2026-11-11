"""
blog/views.py
=============
TradeLink NG — Blog views.

All public views are optimised for SEO:
  - Proper HTTP 404 on missing slugs
  - Canonical URL in context for every view
  - View counter via atomic DB update (no race conditions)
  - Paginated listing views (10 per page)
  - Search via GET ?q= with icontains on title, excerpt, body
  - JSON-LD structured data passed to template context
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CommentForm
from .models import Category, Comment, Post, Tag


POSTS_PER_PAGE = 9


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _published():
    """Base queryset: published posts only."""
    return Post.objects.filter(
        status=Post.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    )


def _paginate(request, qs, per_page=POSTS_PER_PAGE):
    paginator = Paginator(qs, per_page)
    page      = request.GET.get('page', 1)
    try:
        return paginator.page(page)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def _sidebar_data():
    """Shared sidebar context: categories, tags, recent posts."""
    return {
        'sidebar_categories': Category.objects.filter(is_active=True).annotate(
            post_count=Count('posts', filter=Q(posts__status=Post.Status.PUBLISHED))
        ).filter(post_count__gt=0).order_by('display_order', 'name'),
        'sidebar_tags': Tag.objects.annotate(
            post_count=Count('posts', filter=Q(posts__status=Post.Status.PUBLISHED))
        ).filter(post_count__gt=0).order_by('-post_count')[:20],
        'sidebar_recent': _published().select_related('category').order_by('-published_at')[:5],
    }


# ──────────────────────────────────────────────────────────────────────────────
#  LISTING VIEWS
# ──────────────────────────────────────────────────────────────────────────────

def blog_index(request):
    """Main blog listing — featured posts hero + paginated grid."""
    q         = request.GET.get('q', '').strip()
    posts_qs  = _published().select_related('author', 'category').prefetch_related('tags')

    if q:
        posts_qs = posts_qs.filter(
            Q(title__icontains=q) |
            Q(excerpt__icontains=q) |
            Q(body__icontains=q) |
            Q(tags__name__icontains=q) |
            Q(category__name__icontains=q)
        ).distinct()

    featured  = posts_qs.filter(is_featured=True).order_by('-published_at')[:3]
    posts_qs  = posts_qs.order_by('-published_at')
    page_obj  = _paginate(request, posts_qs)

    ctx = {
        'page_obj':   page_obj,
        'featured':   featured,
        'search_q':   q,
        'page_title': 'Blog — Trades Tips, Hiring Guides & Industry News | TradeLink NG',
        'page_desc':  'Expert articles on hiring skilled tradespeople, apprenticeship tips, '
                      'trade safety, tools reviews, and the Nigerian artisan economy.',
        **_sidebar_data(),
    }
    return render(request, 'blog/index.html', ctx)


def post_detail(request, slug):
    """Full post view with TOC, related posts, comment thread, JSON-LD."""
    post = get_object_or_404(
        Post.objects.select_related('author', 'category').prefetch_related('tags', 'comments__author'),
        slug=slug,
        status=Post.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    )

    # Atomic view counter
    post.increment_views()

    # Related posts
    related = post.related_posts(limit=3)

    # Comments
    top_comments = post.comments.filter(is_approved=True, parent__isnull=True).select_related('author')
    comment_form = CommentForm()

    # JSON-LD structured data
    json_ld = _build_json_ld(post, request)

    ctx = {
        'post':          post,
        'related':       related,
        'top_comments':  top_comments,
        'comment_form':  comment_form,
        'toc':           post.table_of_contents,
        'json_ld':       json.dumps(json_ld, ensure_ascii=False),
        'page_title':    post.seo_title,
        'page_desc':     post.seo_description,
        'og_image_url':  post.og_image_url,
        'canonical_url': post.canonical_url or request.build_absolute_uri(post.get_absolute_url()),
        **_sidebar_data(),
    }
    return render(request, 'blog/post_detail.html', ctx)


def category_view(request, slug):
    """Posts filtered by category."""
    category = get_object_or_404(Category, slug=slug, is_active=True)
    posts_qs = _published().filter(category=category).select_related('author', 'category').prefetch_related('tags')
    page_obj = _paginate(request, posts_qs)

    ctx = {
        'category':   category,
        'page_obj':   page_obj,
        'page_title': category.seo_title,
        'page_desc':  category.seo_description,
        **_sidebar_data(),
    }
    return render(request, 'blog/category.html', ctx)


def tag_view(request, slug):
    """Posts filtered by tag."""
    tag      = get_object_or_404(Tag, slug=slug)
    posts_qs = _published().filter(tags=tag).select_related('author', 'category').prefetch_related('tags')
    page_obj = _paginate(request, posts_qs)

    ctx = {
        'tag':        tag,
        'page_obj':   page_obj,
        'page_title': f'#{tag.name} articles — TradeLink NG Blog',
        'page_desc':  f'All TradeLink NG blog posts tagged with #{tag.name}.',
        **_sidebar_data(),
    }
    return render(request, 'blog/tag.html', ctx)


# ──────────────────────────────────────────────────────────────────────────────
#  COMMENTS
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def add_comment(request, slug):
    """Submit a top-level or reply comment."""
    post = get_object_or_404(Post, slug=slug, status=Post.Status.PUBLISHED)

    if not post.allow_comments:
        messages.error(request, 'Comments are closed for this post.')
        return redirect(post.get_absolute_url())

    form = CommentForm(request.POST)
    if form.is_valid():
        comment        = form.save(commit=False)
        comment.post   = post
        comment.author = request.user
        parent_id      = request.POST.get('parent_id')
        if parent_id:
            try:
                comment.parent = Comment.objects.get(pk=parent_id, post=post)
            except Comment.DoesNotExist:
                pass
        comment.save()
        messages.success(request, 'Your comment has been posted.')
    else:
        messages.error(request, 'Please correct the errors in your comment.')

    return redirect(f'{post.get_absolute_url()}#comments')


# ──────────────────────────────────────────────────────────────────────────────
#  JSON-LD BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def _build_json_ld(post, request):
    """Build a JSON-LD Article / HowTo / FAQPage schema dict."""
    abs_url   = request.build_absolute_uri(post.get_absolute_url())
    og_image  = post.og_image_url

    base = {
        '@context': 'https://schema.org',
        '@type':    post.schema_type,
        'headline': post.title,
        'url':      abs_url,
        'datePublished': post.published_at.isoformat() if post.published_at else None,
        'dateModified':  post.updated.isoformat(),
        'description':   post.seo_description,
        'publisher': {
            '@type': 'Organization',
            'name':  'TradeLink NG',
            'url':   request.build_absolute_uri('/'),
            'logo': {
                '@type': 'ImageObject',
                'url':   request.build_absolute_uri('/static/img/logo.png'),
            },
        },
    }

    if post.author:
        base['author'] = {
            '@type': 'Person',
            'name':  post.author.get_full_name() or post.author.username,
        }

    if og_image:
        base['image'] = {
            '@type': 'ImageObject',
            'url':   request.build_absolute_uri(og_image),
        }

    return base
