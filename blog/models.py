"""
blog/models.py
==============
TradeLink NG — Blog application models.

Features:
  - Post: full SEO fields (meta_title, meta_description, og_image, canonical_url)
  - Category & Tag for taxonomy / filtering
  - TableOfContents auto-generated from headings
  - Reading time computed from body word count
  - Related posts via shared tags (M2M)
  - Author linked to AUTH_USER_MODEL
  - View counter for trending posts
  - JSON-LD structured data helpers
"""

import uuid
import math
import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


# ──────────────────────────────────────────────────────────────────────────────
#  CATEGORY
# ──────────────────────────────────────────────────────────────────────────────

class Category(models.Model):
    """Blog post category — plumbing tips, electrical guides, safety, etc."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon_class  = models.CharField(
        max_length=80, blank=True,
        help_text='FontAwesome class, e.g. fas fa-wrench',
    )
    color       = models.CharField(
        max_length=30, blank=True, default='amber',
        help_text='Accent colour name: amber | orange | emerald | sky',
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active     = models.BooleanField(default=True)
    created       = models.DateTimeField(auto_now_add=True)

    # SEO
    meta_title       = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name        = 'Category'
        verbose_name_plural = 'Categories'
        ordering            = ['display_order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:category', kwargs={'slug': self.slug})

    @property
    def seo_title(self):
        return self.meta_title or f'{self.name} — TradeLink NG Blog'

    @property
    def seo_description(self):
        return self.meta_description or self.description[:160] or (
            f'Read expert {self.name} articles and guides on the TradeLink NG blog.'
        )


# ──────────────────────────────────────────────────────────────────────────────
#  TAG
# ──────────────────────────────────────────────────────────────────────────────

class Tag(models.Model):
    """Freeform tag for blog posts — enables granular topic filtering."""
    name    = models.CharField(max_length=60, unique=True)
    slug    = models.SlugField(max_length=80, unique=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:tag', kwargs={'slug': self.slug})


# ──────────────────────────────────────────────────────────────────────────────
#  POST
# ──────────────────────────────────────────────────────────────────────────────

class Post(models.Model):
    """
    A blog article.

    SEO fields
    ----------
    meta_title       — overrides the <title> tag (max 70 chars)
    meta_description — overrides the meta description (max 160 chars)
    og_image         — Open Graph / Twitter card image
    canonical_url    — set when the post is cross-posted elsewhere
    focus_keyword    — primary keyword for on-page SEO hint
    schema_type      — JSON-LD @type (Article | HowTo | FAQPage)

    Indexing
    --------
    Published posts are automatically included in the sitemap via
    django.contrib.sitemaps (see blog/sitemaps.py).
    """

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED  = 'archived',  'Archived'

    class SchemaType(models.TextChoices):
        ARTICLE  = 'Article',  'Article'
        HOW_TO   = 'HowTo',    'HowTo'
        FAQ_PAGE = 'FAQPage',  'FAQPage'
        NEWS     = 'NewsArticle', 'NewsArticle'

    # ── Identity ────────────────────────────────────────────────────────────
    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True,
        related_name='blog_posts',
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='posts',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts')

    # ── Content ─────────────────────────────────────────────────────────────
    title    = models.CharField(max_length=200)
    slug     = models.SlugField(max_length=220, unique=True, blank=True)
    excerpt  = models.TextField(
        max_length=320, blank=True,
        help_text='Short summary shown in listing cards (max 320 chars). '
                  'Auto-generated from body if left blank.',
    )
    body     = models.TextField(help_text='HTML content. Use heading tags h2/h3 for TOC.')

    # Featured image
    featured_image     = models.ImageField(
        upload_to='blog/featured/', blank=True, null=True,
    )
    featured_image_alt = models.CharField(
        max_length=200, blank=True,
        help_text='Alt text for featured image (improves accessibility & image SEO).',
    )

    # ── SEO ─────────────────────────────────────────────────────────────────
    meta_title       = models.CharField(
        max_length=70, blank=True,
        help_text='Custom <title> tag. Leave blank to use post title. Max 70 chars.',
    )
    meta_description = models.CharField(
        max_length=160, blank=True,
        help_text='Meta description shown in SERPs. Max 160 chars.',
    )
    og_image         = models.ImageField(
        upload_to='blog/og/', blank=True, null=True,
        help_text='Open Graph / Twitter card image (1200×630 px recommended).',
    )
    canonical_url    = models.URLField(
        blank=True,
        help_text='Canonical URL if this post is syndicated from another source.',
    )
    focus_keyword    = models.CharField(
        max_length=100, blank=True,
        help_text='Primary SEO keyword for this post.',
    )
    schema_type      = models.CharField(
        max_length=20,
        choices=SchemaType.choices,
        default=SchemaType.ARTICLE,
    )
    no_index         = models.BooleanField(
        default=False,
        help_text='Add noindex meta tag (useful for draft previews).',
    )

    # ── Status & dates ──────────────────────────────────────────────────────
    status       = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created      = models.DateTimeField(auto_now_add=True)
    updated      = models.DateTimeField(auto_now=True)

    # ── Engagement ──────────────────────────────────────────────────────────
    views        = models.PositiveIntegerField(default=0, db_index=True)
    is_featured  = models.BooleanField(default=False, db_index=True)
    allow_comments = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Post'
        verbose_name_plural = 'Posts'
        ordering            = ['-published_at', '-created']
        indexes = [
            models.Index(fields=['status', 'published_at']),
            models.Index(fields=['is_featured', 'status']),
        ]

    def __str__(self):
        return self.title

    # ── URL helpers ─────────────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        # Auto-set published_at when first published
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        # Auto-generate excerpt from body if blank
        if not self.excerpt and self.body:
            clean = re.sub(r'<[^>]+>', '', self.body)
            self.excerpt = clean[:320].rsplit(' ', 1)[0] + '…'
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:post_detail', kwargs={'slug': self.slug})

    # ── Computed properties ─────────────────────────────────────────────────

    @property
    def reading_time(self):
        """Estimated reading time in minutes (200 wpm average)."""
        word_count = len(re.sub(r'<[^>]+>', '', self.body or '').split())
        return max(1, math.ceil(word_count / 200))

    @property
    def seo_title(self):
        return self.meta_title or f'{self.title} — TradeLink NG'

    @property
    def seo_description(self):
        if self.meta_description:
            return self.meta_description
        clean = re.sub(r'<[^>]+>', '', self.excerpt or self.body or '')
        return clean[:160]

    @property
    def og_image_url(self):
        """Return OG image URL, falling back to featured image."""
        if self.og_image:
            return self.og_image.url
        if self.featured_image:
            return self.featured_image.url
        return None

    @property
    def table_of_contents(self):
        """
        Parse h2 / h3 headings from body HTML and return a list of dicts:
            [{'level': 2, 'id': 'intro', 'text': 'Introduction'}, …]
        """
        pattern = re.compile(
            r'<h([23])[^>]*(?:id=["\']([^"\']*)["\'])?[^>]*>(.*?)</h[23]>',
            re.IGNORECASE | re.DOTALL,
        )
        toc = []
        for match in pattern.finditer(self.body or ''):
            level   = int(match.group(1))
            heading_id = match.group(2) or ''
            text    = re.sub(r'<[^>]+>', '', match.group(3)).strip()
            # Auto-generate id from text if not set in HTML
            if not heading_id:
                heading_id = slugify(text)
            toc.append({'level': level, 'id': heading_id, 'text': text})
        return toc

    def related_posts(self, limit=3):
        """Return posts sharing the most tags, excluding self."""
        tag_ids = self.tags.values_list('id', flat=True)
        return (
            Post.objects.filter(
                status=Post.Status.PUBLISHED,
                tags__in=tag_ids,
            )
            .exclude(pk=self.pk)
            .annotate(shared=models.Count('tags'))
            .order_by('-shared', '-published_at')
            .distinct()[:limit]
        )

    def increment_views(self):
        Post.objects.filter(pk=self.pk).update(views=models.F('views') + 1)


# ──────────────────────────────────────────────────────────────────────────────
#  COMMENT
# ──────────────────────────────────────────────────────────────────────────────

class Comment(models.Model):
    """Threaded comments on blog posts (single level of nesting)."""

    post    = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, related_name='blog_comments',
    )
    parent  = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='replies',
    )
    body    = models.TextField(max_length=2000)
    is_approved = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created']

    def __str__(self):
        return f'Comment by {self.author} on "{self.post}"'
