"""
URL configuration for technicians project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')\
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap

from django.views.generic import RedirectView

from blog.sitemaps import BlogPostSitemap, BlogCategorySitemap, BlogIndexSitemap

sitemaps = {
    'blog_posts':      BlogPostSitemap,
    'blog_categories': BlogCategorySitemap,
    'blog_index':      BlogIndexSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("", include("users.urls")),
    path("", include("jobs.urls")),
    path('marketplace/', include('marketplace.urls', namespace='mktplace')),
    path('chats/', include('chats.urls', namespace='chats')),
    path('verify/', include('verification.urls', namespace='verify')),
    path('accounts/login/', RedirectView.as_view(pattern_name='signin', query_string=True), name='account_login'),
    path('accounts/signup/', RedirectView.as_view(pattern_name='register', query_string=True), name='account_signup'),
    path('accounts/', include('allauth.urls')),
    path('', include('bot.urls')),
    path('hire/', include('hiring.urls', namespace='hiring')),
    path('contacts/', include('contacts.urls', namespace='contacts')),
    path('blog/', include('blog.urls', namespace='blog')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
