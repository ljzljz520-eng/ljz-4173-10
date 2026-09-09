"""测试公共构造: 用户 / 流程版本 / 会话."""
from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.exercises.models import ObservationSession
from apps.sops.models import CriticalFailItem, SOPStep, SOPVersion

STEP_DEFS = [
    (1, "handwash", "洗手", "gowning", 10),
    (2, "donning", "穿戴", "gowning", 10),
    (3, "item_transfer", "物品传递", "instrument_prep", 10),
    (4, "glove_contamination", "手套污染", "sterile_field", 10),
    (5, "instrument_layout", "器械摆放", "instrument_prep", 10),
    (6, "waste_disposal", "废弃物处置", "cleanup", 10),
]


def make_version(*, version="1.0", current=True, threshold=80, retention_days=365):
    v = SOPVersion.objects.create(
        facility="实验动物中心",
        code="GLP-OBS",
        version=version,
        title="更衣与无菌操作观察流程",
        effective_from=date(2026, 1, 1),
        is_current=current,
        retention_days=retention_days,
        pass_threshold=threshold,
    )
    for order, code, name, phase, points in STEP_DEFS:
        SOPStep.objects.create(
            version=v, order=order, code=code, name=name, phase=phase, max_points=points
        )
    CriticalFailItem.objects.create(
        version=v,
        code="STERILE_BREACH",
        description="无菌区被破坏且未按规程处理",
        auto_trigger_step="glove_contamination",
    )
    CriticalFailItem.objects.create(
        version=v,
        code="WASTE_MIX",
        description="感染性废弃物混放",
        auto_trigger_step="waste_disposal",
    )
    return v


class BaseCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.observer1 = User.objects.create_user("observer1", password="pw", role=User.Role.OBSERVER)
        cls.observer2 = User.objects.create_user("observer2", password="pw", role=User.Role.OBSERVER)
        cls.trainee = User.objects.create_user("trainee1", password="pw", role=User.Role.TRAINEE)
        cls.other_trainee = User.objects.create_user("trainee2", password="pw", role=User.Role.TRAINEE)

    def make_session(self, version=None, **kwargs):
        version = version or make_version()
        defaults = dict(
            trainee=self.trainee,
            primary_observer=self.observer1,
            sop_version=version,
            species_category=ObservationSession.Species.RODENT,
            operation_area=ObservationSession.Area.BARRIER,
        )
        defaults.update(kwargs)
        return ObservationSession.objects.create(**defaults)

    def record_all(self, session, observer, outcome="pass", skip=()):
        from apps.exercises import services

        for step in session.snapshot["steps"]:
            if step["code"] in skip:
                continue
            services.record_step(
                session=session, observer=observer, step_code=step["code"], outcome=outcome
            )
