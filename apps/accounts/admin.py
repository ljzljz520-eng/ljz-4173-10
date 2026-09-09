from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("平台角色", {"fields": ("role",)}),)
    list_display = ("username", "role", "is_staff")
