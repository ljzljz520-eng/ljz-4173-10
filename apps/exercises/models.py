"""观察会话: 每次练习冻结 设施流程版本 / 物种类别 / 操作区域 / 关键失败项.

证据完整性原则:
- 会话创建时把 SOP 版本内容快照进 JSONField, 之后版本更换不影响历史计分;
- 步骤记录按真实记录顺序(recorded_seq)保存, 不可修改、不可删除;
- 补录(记录顺序晚于步骤顺序)必须填写原因;
- 两位观察员对同一步骤结论不一致时生成冲突, 解决前会话不能定稿;
- 关键失败项由系统自动提示, 但必须由观察员人工确认才生效.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models


class ObservationSession(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "进行中"
        FINALIZED = "finalized", "已定稿"

    class Result(models.TextChoices):
        PENDING = "pending", "待评定"
        PASS = "pass", "通过"
        FAIL = "fail", "未通过"

    class Species(models.TextChoices):
        RODENT = "rodent", "啮齿类(大/小鼠)"
        RABBIT = "rabbit", "兔"
        CANINE = "canine", "犬"
        SWINE = "swine", "猪"
        NHP = "nhp", "非人灵长类"
        OTHER = "other", "其他"

    class Area(models.TextChoices):
        BARRIER = "barrier", "屏障环境"
        SURGERY = "surgery", "手术室"
        PREP = "prep", "准备间"
        ISOLATION = "isolation", "隔离区"

    trainee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="training_sessions"
    )
    primary_observer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="observed_sessions"
    )
    sop_version = models.ForeignKey("sops.SOPVersion", on_delete=models.PROTECT, related_name="sessions")
    species_category = models.CharField("物种类别", max_length=16, choices=Species.choices)
    operation_area = models.CharField("操作区域", max_length=16, choices=Area.choices)
    snapshot = models.JSONField("冻结的流程快照", default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    result = models.CharField(max_length=16, choices=Result.choices, default=Result.PENDING)
    score_percent = models.DecimalField("得分率(%)", max_digits=5, decimal_places=2, null=True, blank=True)
    supersedes = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="superseded_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.pk and not self.snapshot:
            self.snapshot = self.sop_version.snapshot()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"会话#{self.pk} {self.trainee} @ {self.sop_version}"


class StepRecord(models.Model):
    """单条步骤观察记录. 创建后不可修改; 异议通过观察员冲突流程解决."""

    class Outcome(models.TextChoices):
        PASS = "pass", "合格"
        PARTIAL = "partial", "部分合格"
        FAIL = "fail", "不合格"
        NA = "na", "不适用"

    session = models.ForeignKey(ObservationSession, on_delete=models.CASCADE, related_name="step_records")
    observer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="step_records")
    step_code = models.CharField(max_length=32)
    step_name = models.CharField(max_length=64)
    step_order = models.PositiveSmallIntegerField()
    max_points = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    points_awarded = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    note = models.TextField("备注", blank=True)
    recorded_seq = models.PositiveIntegerField("记录顺序号")
    is_backfilled = models.BooleanField("是否补录", default=False)
    backfill_reason = models.TextField("补录原因", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("session", "step_code", "observer")
        ordering = ["recorded_seq"]

    def __str__(self):
        return f"{self.session_id}/{self.step_code}={self.outcome} by {self.observer_id}"


class CriticalFailConfirmation(models.Model):
    """关键失败项确认单. 系统只能提示(pending), 生效必须经观察员确认."""

    class State(models.TextChoices):
        PENDING = "pending", "待确认"
        CONFIRMED = "confirmed", "已确认"
        DISMISSED = "dismissed", "已排除"

    session = models.ForeignKey(
        ObservationSession, on_delete=models.CASCADE, related_name="critical_confirmations"
    )
    item_code = models.CharField(max_length=32)
    item_description = models.CharField(max_length=256)
    state = models.CharField(max_length=16, choices=State.choices, default=State.PENDING)
    suggested_by_record = models.ForeignKey(
        StepRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ObserverConflict(models.Model):
    """两位观察员对同一步骤结论不一致. 双方原始记录均保留."""

    class Status(models.TextChoices):
        OPEN = "open", "待解决"
        RESOLVED = "resolved", "已解决"

    session = models.ForeignKey(ObservationSession, on_delete=models.CASCADE, related_name="conflicts")
    step_code = models.CharField(max_length=32)
    record_a = models.ForeignKey(StepRecord, on_delete=models.CASCADE, related_name="+")
    record_b = models.ForeignKey(StepRecord, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_outcome = models.CharField(max_length=8, choices=StepRecord.Outcome.choices, blank=True)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
