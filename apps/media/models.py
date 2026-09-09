"""视频片段: 仅存 S3 指针与元数据, 对象本体在 S3.

- 上传三段式: init(创建分片上传) -> 浏览器直传分片 -> complete/abort;
- 完成时按会话冻结版本的保留期限计算 retention_until;
- 每次访问(查看/下载/拒绝)都写入 VideoAccessAudit;
- 过期后由 purge_expired_media 删除 S3 对象, 元数据与审计保留备查.
"""
from django.conf import settings
from django.db import models

from apps.exercises.models import ObservationSession, StepRecord


class VideoClip(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "上传中"
        COMPLETED = "completed", "已完成"
        ABORTED = "aborted", "已中止"
        PURGED = "purged", "已清除(过期)"

    session = models.ForeignKey(ObservationSession, on_delete=models.CASCADE, related_name="clips")
    step_record = models.ForeignKey(
        StepRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="clips"
    )
    s3_key = models.CharField(max_length=512)
    upload_id = models.CharField(max_length=128, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=64, default="video/mp4")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateTimeField("保留截止", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"clip#{self.pk} session={self.session_id} {self.status}"


class VideoAccessAudit(models.Model):
    class Action(models.TextChoices):
        VIEW = "view", "在线查看"
        DOWNLOAD = "download", "下载"
        DENIED = "denied", "拒绝访问"

    clip = models.ForeignKey(VideoClip, on_delete=models.CASCADE, related_name="access_audits")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accessed_at"]
