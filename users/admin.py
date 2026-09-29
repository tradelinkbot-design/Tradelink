from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["id","username", "first_name", "last_name", "email", "phone_number", "created", "updated"]
    list_filter = ["id","username", "first_name", "last_name", "email", "phone_number", "created", "updated"]
    search_fields = ['username', 'email', 'first_name', 'last_name']