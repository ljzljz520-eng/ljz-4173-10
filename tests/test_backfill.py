"""步骤补录: 乱序补记较早步骤必须说明原因, 且保留真实记录顺序."""
from django.core.exceptions import ValidationError

from apps.exercises import services

from .base import BaseCase


class BackfillTest(BaseCase):
    def test_out_of_order_recording_requires_reason_and_marks_backfill(self):
        session = self.make_session()
        services.record_step(session=session, observer=self.observer1, step_code="handwash", outcome="pass")
        services.record_step(session=session, observer=self.observer1, step_code="item_transfer", outcome="pass")

        # 直接补记顺序更早的"穿戴"而不填原因 -> 拒绝
        with self.assertRaises(ValidationError):
            services.record_step(session=session, observer=self.observer1, step_code="donning", outcome="pass")

        rec = services.record_step(
            session=session,
            observer=self.observer1,
            step_code="donning",
            outcome="pass",
            backfill_reason="术中忙于无菌区维护, 术后立即补记",
        )
        self.assertTrue(rec.is_backfilled)
        self.assertEqual(rec.recorded_seq, 3)

        # 真实记录顺序保持 洗手 -> 物品传递 -> 穿戴(补录)
        seq = [r.step_code for r in session.step_records.all()]
        self.assertEqual(seq, ["handwash", "item_transfer", "donning"])

    def test_in_order_recording_is_not_backfill(self):
        session = self.make_session()
        r1 = services.record_step(session=session, observer=self.observer1, step_code="handwash", outcome="pass")
        r2 = services.record_step(session=session, observer=self.observer1, step_code="donning", outcome="pass")
        self.assertFalse(r1.is_backfilled)
        self.assertFalse(r2.is_backfilled)
