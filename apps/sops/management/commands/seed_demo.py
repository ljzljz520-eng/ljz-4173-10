"""演示数据: 用户 + 两个流程版本(用于版本更换演示)."""
from datetime import date

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.sops.models import CriticalFailItem, SOPStep, SOPVersion

STEPS = [
    (1, "handwash", "洗手", "gowning"),
    (2, "donning", "穿戴", "gowning"),
    (3, "item_transfer", "物品传递", "instrument_prep"),
    (4, "glove_contamination", "手套污染", "sterile_field"),
    (5, "instrument_layout", "器械摆放", "instrument_prep"),
    (6, "waste_disposal", "废弃物处置", "cleanup"),
]

CRITICALS = [
    ("STERILE_BREACH", "无菌区被破坏且未按规程处理", "glove_contamination"),
    ("PPE_SKIP", "未按规定穿戴即进入操作区", "donning"),
    ("WASTE_MIX", "感染性废弃物混放", "waste_disposal"),
]


def make_version(version, current, threshold, retention):
    v, _ = SOPVersion.objects.get_or_create(
        facility="实验动物中心",
        code="GLP-GOWN-001",
        version=version,
        defaults={
            "title": "屏障设施更衣与无菌操作观察流程",
            "effective_from": date(2026, 1, 1),
            "is_current": current,
            "pass_threshold": threshold,
            "retention_days": retention,
        },
    )
    if not v.steps.exists():
        for order, code, name, phase in STEPS:
            SOPStep.objects.create(version=v, order=order, code=code, name=name, phase=phase, max_points=10)
        for code, desc, trigger in CRITICALS:
            CriticalFailItem.objects.create(version=v, code=code, description=desc, auto_trigger_step=trigger)
    return v


class Command(BaseCommand):
    help = "创建演示用户与 SOP 版本"

    def handle(self, *args, **options):
        users = [
            ("admin", User.Role.ADMIN, True),
            ("observer1", User.Role.OBSERVER, False),
            ("observer2", User.Role.OBSERVER, False),
            ("trainee1", User.Role.TRAINEE, False),
        ]
        for username, role, is_super in users:
            user, created = User.objects.get_or_create(username=username, defaults={"role": role})
            if created:
                user.set_password("demo12345")
                user.is_superuser = is_super
                user.is_staff = is_super
                user.save()
        make_version("0.9", current=False, threshold=75, retention=1095)
        make_version("1.0", current=True, threshold=80, retention=1095)
        self.stdout.write(self.style.SUCCESS("演示数据就绪: admin/observer1/observer2/trainee1, 密码 demo12345"))
