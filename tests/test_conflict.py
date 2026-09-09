"""两位观察员冲突: 结论不一致自动生成冲突, 解决前不能定稿, 双方记录均保留."""
from django.core.exceptions import ValidationError

from apps.exercises import services
from apps.exercises.models import ObserverConflict

from .base import BaseCase


class ObserverConflictTest(BaseCase):
    def test_conflict_lifecycle(self):
        session = self.make_session()
        # 主观察员完成全部步骤
        self.record_all(session, self.observer1, outcome="pass")
        # 第二观察员对"手套污染"步骤给出不同结论
        services.record_step(
            session=session, observer=self.observer2, step_code="glove_contamination",
            outcome="fail", backfill_reason="第二观察员术后复核补录",
        )

        conflict = session.conflicts.get()
        self.assertEqual(conflict.status, ObserverConflict.Status.OPEN)
        self.assertEqual(conflict.step_code, "glove_contamination")

        # 冲突未解决 -> 不能定稿
        with self.assertRaises(ValidationError):
            services.finalize(session, by=self.observer1)

        # 裁定以"不合格"为准
        services.resolve_conflict(conflict=conflict, resolver=self.observer1, outcome="fail", note="回放视频确认污染")
        session.refresh_from_db()

        # 双方原始记录都还在
        self.assertEqual(
            session.step_records.filter(step_code="glove_contamination").count(), 2
        )
        # 生效结论采用裁定值
        self.assertEqual(services.effective_outcomes(session)["glove_contamination"], "fail")

        # 手套污染不合格触发了关键失败提示, 需先人工处理
        with self.assertRaises(ValidationError):
            services.finalize(session, by=self.observer1)
        services.decide_critical(
            session=session, item_code="STERILE_BREACH", observer=self.observer1, confirm=True
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(session.result, "fail")

    def test_same_outcome_by_two_observers_creates_no_conflict(self):
        session = self.make_session()
        services.record_step(session=session, observer=self.observer1, step_code="handwash", outcome="pass")
        services.record_step(session=session, observer=self.observer2, step_code="handwash", outcome="pass")
        self.assertEqual(session.conflicts.count(), 0)
