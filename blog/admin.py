"""blog/admin.py — Jazzmin-friendly admin for the blog."""
from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Comment, Post, Tag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'display_order', 'is_active', 'post_count')
    list_editable = ('display_order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'icon_class', 'color', 'display_order', 'is_active')}),
        ('SEO', {'fields': ('meta_title', 'meta_description'), 'classes': ('collapse',)}),
    )

    def post_count(self, obj):
        return obj.posts.filter(status=Post.Status.PUBLISHED).count()
    post_count.short_description = 'Published Posts'


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display        = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields       = ('name',)


class CommentInline(admin.TabularInline):
    model  = Comment
    extra  = 0
    fields = ('author', 'body', 'is_approved', 'created')
    readonly_fields = ('created',)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display   = ('title', 'author', 'category', 'status', 'is_featured', 'views', 'published_at')
    list_filter    = ('status', 'is_featured', 'category')
    list_editable  = ('status', 'is_featured')
    search_fields  = ('title', 'body', 'focus_keyword')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('tags',)
    date_hierarchy = 'published_at'
    inlines        = [CommentInline]
    readonly_fields = ('created', 'updated', 'views', 'reading_time_display')

    fieldsets = (
        ('Content', {
            'fields': (
                'title', 'slug', 'author', 'category', 'tags',
                'excerpt', 'body',
                'featured_image', 'featured_image_alt',
            ),
        }),
        ('Publishing', {
            'fields': ('status', 'published_at', 'is_featured', 'allow_comments'),
        }),
        ('SEO', {
            'fields': (
                'meta_title', 'meta_description',
                'og_image', 'canonical_url',
                'focus_keyword', 'schema_type', 'no_index',
            ),
            'classes': ('collapse',),
        }),
        ('Stats', {
            'fields': ('views', 'reading_time_display', 'created', 'updated'),
            'classes': ('collapse',),
        }),
    )

    def reading_time_display(self, obj):
        return f'{obj.reading_time} min read'
    reading_time_display.short_description = 'Reading Time'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display  = ('post', 'author', 'is_approved', 'created')
    list_filter   = ('is_approved',)
    list_editable = ('is_approved',)
    search_fields = ('body', 'author__username', 'post__title')
    actions       = ['approve_comments', 'unapprove_comments']

    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = 'Approve selected comments'

    def unapprove_comments(self, request, queryset):
        queryset.update(is_approved=False)
    unapprove_comments.short_description = 'Unapprove selected comments'
