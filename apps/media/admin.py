from django.contrib import admin

from .models import VideoAccessAudit, VideoClip


@admin.register(VideoClip)
class VideoClipAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "status", "size_bytes", "retention_until", "uploaded_by")
    list_filter = ("status",)


@admin.register(VideoAccessAudit)
class VideoAccessAuditAdmin(admin.ModelAdmin):
    list_display = ("clip", "user", "action", "ip", "accessed_at")
    readonly_fields = ("clip", "user", "action", "ip", "user_agent", "accessed_at")
