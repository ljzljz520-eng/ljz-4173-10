"""设施标准操作流程(SOP)版本.

版本不可变: 更换流程时新建 SOPVersion 行, 旧版本保留供历史会话引用.
每个观察会话在创建时把版本内容快照进 JSON, 之后版本行的任何变化
都不会影响已冻结的证据与计分.
"""
from django.db import models


class SOPVersion(models.Model):
    facility = models.CharField("设施", max_length=64)
    code = models.CharField("流程代码", max_length=32)
    version = models.CharField("版本号", max_length=16)
    title = models.CharField("标题", max_length=128)
    effective_from = models.DateField("生效日期")
    is_current = models.BooleanField("当前在用", default=False)
    retention_days = models.PositiveIntegerField("证据保留天数", default=1095)
    pass_threshold = models.PositiveSmallIntegerField("通过分数线(%)", default=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("facility", "code", "version")
        ordering = ["-effective_from", "-id"]

    def __str__(self):
        return f"{self.facility}/{self.code} v{self.version}"

    def snapshot(self):
        """冻结版本内容, 存入观察会话."""
        return {
            "facility": self.facility,
            "code": self.code,
            "version": self.version,
            "title": self.title,
            "pass_threshold": self.pass_threshold,
            "retention_days": self.retention_days,
            "steps": [
                {
                    "code": s.code,
                    "name": s.name,
                    "order": s.order,
                    "phase": s.phase,
                    "phase_display": s.get_phase_display(),
                    "max_points": s.max_points,
                }
                for s in self.steps.all()
            ],
            "critical_items": [
                {
                    "code": c.code,
                    "description": c.description,
                    "auto_trigger_step": c.auto_trigger_step,
                }
                for c in self.critical_items.all()
            ],
        }


class SOPStep(models.Model):
    """观察步骤. 顺序即现场真实操作顺序."""

    class Code(models.TextChoices):
        HANDWASH = "handwash", "洗手"
        DONNING = "donning", "穿戴"
        ITEM_TRANSFER = "item_transfer", "物品传递"
        GLOVE_CONTAMINATION = "glove_contamination", "手套污染"
        INSTRUMENT_LAYOUT = "instrument_layout", "器械摆放"
        WASTE_DISPOSAL = "waste_disposal", "废弃物处置"

    class Phase(models.TextChoices):
        GOWNING = "gowning", "更衣"
        INSTRUMENT_PREP = "instrument_prep", "器械准备"
        STERILE_FIELD = "sterile_field", "无菌区维护"
        CLEANUP = "cleanup", "术后清场"

    version = models.ForeignKey(SOPVersion, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField("顺序")
    code = models.CharField("步骤代码", max_length=32, choices=Code.choices)
    name = models.CharField("步骤名称", max_length=64)
    phase = models.CharField("能力域", max_length=32, choices=Phase.choices)
    max_points = models.PositiveSmallIntegerField("满分", default=10)

    class Meta:
        unique_together = (("version", "code"), ("version", "order"))
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.name}"


class CriticalFailItem(models.Model):
    """关键失败项: 一旦确认, 无论得分如何本次观察判不合格.

    auto_trigger_step 非空时, 对应步骤被判"不合格"会自动生成一条
    待确认记录, 但必须由观察员人工确认后才生效.
    """

    version = models.ForeignKey(SOPVersion, on_delete=models.CASCADE, related_name="critical_items")
    code = models.CharField("代码", max_length=32)
    description = models.CharField("描述", max_length=256)
    auto_trigger_step = models.CharField(
        "自动提示步骤", max_length=32, choices=SOPStep.Code.choices, blank=True
    )

    class Meta:
        unique_together = ("version", "code")

    def __str__(self):
        return f"{self.code}: {self.description}"
