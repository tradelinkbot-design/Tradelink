"""blog/sitemaps.py — Sitemap classes for the blog."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from .models import Category, Post


class BlogPostSitemap(Sitemap):
    changefreq = 'weekly'
    priority   = 0.8
    protocol   = 'https'

    def items(self):
        return Post.objects.filter(
            status=Post.Status.PUBLISHED,
            published_at__lte=timezone.now(),
            no_index=False,
        ).order_by('-published_at')

    def lastmod(self, obj):
        return obj.updated

    def location(self, obj):
        return obj.get_absolute_url()


class BlogCategorySitemap(Sitemap):
    changefreq = 'weekly'
    priority   = 0.6
    protocol   = 'https'

    def items(self):
        return Category.objects.filter(is_active=True)

    def location(self, obj):
        return obj.get_absolute_url()


class BlogIndexSitemap(Sitemap):
    changefreq = 'daily'
    priority   = 0.9
    protocol   = 'https'

    def items(self):
        return ['blog:index']

    def location(self, item):
        return reverse(item)
