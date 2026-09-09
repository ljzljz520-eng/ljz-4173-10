from django.contrib import admin

from .models import ReReviewRequest, TraineeResponse


@admin.register(TraineeResponse)
class TraineeResponseAdmin(admin.ModelAdmin):
    list_display = ("session", "author", "created_at")
    readonly_fields = ("session", "author", "body", "created_at")

    def has_delete_permission(self, request, obj=None):
        return False  # 原意见不删除


@admin.register(ReReviewRequest)
class ReReviewRequestAdmin(admin.ModelAdmin):
    list_display = ("session", "requested_by", "status", "resolved_by", "created_at")
