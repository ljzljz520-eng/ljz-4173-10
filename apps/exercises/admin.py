from django.contrib import admin

from .models import CriticalFailConfirmation, ObservationSession, ObserverConflict, StepRecord


class StepRecordInline(admin.TabularInline):
    model = StepRecord
    extra = 0
    readonly_fields = ("recorded_seq", "is_backfilled", "created_at")


@admin.register(ObservationSession)
class ObservationSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "trainee", "primary_observer", "sop_version", "species_category", "operation_area", "status", "result", "score_percent")
    list_filter = ("status", "result", "species_category", "operation_area")
    readonly_fields = ("snapshot", "created_at", "finalized_at")
    inlines = [StepRecordInline]


@admin.register(StepRecord)
class StepRecordAdmin(admin.ModelAdmin):
    list_display = ("session", "step_code", "observer", "outcome", "recorded_seq", "is_backfilled")
    list_filter = ("outcome", "is_backfilled")


@admin.register(CriticalFailConfirmation)
class CriticalFailConfirmationAdmin(admin.ModelAdmin):
    list_display = ("session", "item_code", "state", "decided_by", "decided_at")


@admin.register(ObserverConflict)
class ObserverConflictAdmin(admin.ModelAdmin):
    list_display = ("session", "step_code", "status", "resolved_outcome", "resolved_by")
