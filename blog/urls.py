"""blog/urls.py — URL patterns for the blog app."""
from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    # Listing
    path('',  views.blog_index,   name='index'),
    path('category/<slug:slug>/', views.category_view, name='category'),
    path('tag/<slug:slug>/',   views.tag_view,     name='tag'),

    # Detail
    path('<slug:slug>/',  views.post_detail,  name='post_detail'),

    # Comments
    path('<slug:slug>/comment/', views.add_comment, name='add_comment'),
]
