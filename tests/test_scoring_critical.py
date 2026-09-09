"""自动计分按冻结版本计算; 关键失败必须经观察员确认才生效."""
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.exercises import services
from apps.exercises.models import CriticalFailConfirmation, ObservationSession

from .base import BaseCase


class ScoringAndCriticalTest(BaseCase):
    def test_auto_score_uses_frozen_threshold(self):
        session = self.make_session()
        # 5 步合格(50) + 1 步部分合格(5) = 55/60 = 91.67 >= 80
        self.record_all(session, self.observer1, skip={"waste_disposal"})
        services.record_step(
            session=session, observer=self.observer1, step_code="waste_disposal", outcome="partial"
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(session.score_percent, Decimal("91.67"))
        self.assertEqual(session.result, ObservationSession.Result.PASS)

    def test_na_steps_excluded_from_denominator(self):
        session = self.make_session()
        self.record_all(session, self.observer1, skip={"waste_disposal"})
        services.record_step(
            session=session, observer=self.observer1, step_code="waste_disposal", outcome="na"
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(session.score_percent, Decimal("100.00"))

    def test_critical_fail_requires_observer_confirmation(self):
        session = self.make_session()
        # 手套污染不合格 -> 系统自动生成"待确认"关键失败, 但不直接判负
        self.record_all(session, self.observer1, skip={"glove_contamination"})
        services.record_step(
            session=session, observer=self.observer1, step_code="glove_contamination",
            outcome="fail", backfill_reason="污染事件发生时未即时记录, 术后补录",
        )
        conf = session.critical_confirmations.get(item_code="STERILE_BREACH")
        self.assertEqual(conf.state, CriticalFailConfirmation.State.PENDING)

        # 未确认前不能定稿 —— 关键失败必须人工确认
        with self.assertRaises(ValidationError):
            services.finalize(session, by=self.observer1)

        # 观察员排除 -> 按分数正常判定(50/60=83.33 通过)
        services.decide_critical(
            session=session, item_code="STERILE_BREACH", observer=self.observer1, confirm=False,
            note="回放确认未接触无菌区",
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(session.result, ObservationSession.Result.PASS)
        self.assertEqual(session.score_percent, Decimal("83.33"))

    def test_confirmed_critical_overrides_high_score(self):
        session = self.make_session()
        self.record_all(session, self.observer1, skip={"glove_contamination"})
        services.record_step(
            session=session, observer=self.observer1, step_code="glove_contamination",
            outcome="fail", backfill_reason="污染事件发生时未即时记录, 术后补录",
        )
        services.decide_critical(
            session=session, item_code="STERILE_BREACH", observer=self.observer1, confirm=True
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(session.result, ObservationSession.Result.FAIL)
