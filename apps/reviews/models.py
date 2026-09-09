"""学员回应与复评申请. 回应只增不改不删, 保留完整意见链."""
from django.conf import settings
from django.db import models

from apps.exercises.models import ObservationSession


class TraineeResponse(models.Model):
    session = models.ForeignKey(
        ObservationSession, on_delete=models.CASCADE, related_name="responses"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField("回应内容")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ReReviewRequest(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        ACCEPTED = "accepted", "已受理(开启新会话)"
        DECLINED = "declined", "已驳回"

    session = models.ForeignKey(
        ObservationSession, on_delete=models.CASCADE, related_name="rereview_requests"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.TextField("申请理由")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
