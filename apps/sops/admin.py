from django.contrib import admin

from .models import CriticalFailItem, SOPStep, SOPVersion


class StepInline(admin.TabularInline):
    model = SOPStep
    extra = 0


class CriticalInline(admin.TabularInline):
    model = CriticalFailItem
    extra = 0


@admin.register(SOPVersion)
class SOPVersionAdmin(admin.ModelAdmin):
    list_display = ("facility", "code", "version", "is_current", "pass_threshold", "retention_days")
    inlines = [StepInline, CriticalInline]
