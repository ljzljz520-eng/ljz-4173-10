"""流程版本更换: 会话冻结创建时的版本, 之后换版/改版不影响历史计分."""
from apps.exercises import services
from apps.sops.models import SOPVersion

from .base import BaseCase, make_version


class VersionChangeTest(BaseCase):
    def test_session_keeps_frozen_version_after_facility_upgrades(self):
        v1 = make_version(version="1.0", current=True, threshold=80, retention_days=365)
        session = self.make_session(version=v1)
        self.assertEqual(session.snapshot["version"], "1.0")
        self.assertEqual(session.snapshot["pass_threshold"], 80)
        self.assertEqual(session.snapshot["retention_days"], 365)

        # 设施切换到新版本 2.0 (分数线更严, 保留期更短)
        v1.is_current = False
        v1.save()
        make_version(version="2.0", current=True, threshold=95, retention_days=30)

        # 旧版本行甚至被直接改严, 也不应影响已冻结会话
        SOPVersion.objects.filter(pk=v1.pk).update(pass_threshold=99, retention_days=7)
        session.refresh_from_db()

        # 5 步合格 + 1 步部分合格 = 55/60 = 91.67%:
        # 按冻结的 80 分线通过; 若错误地用了改后的 99 分线则会判负
        self.record_all(session, self.observer1, skip={"instrument_layout"})
        services.record_step(
            session=session, observer=self.observer1, step_code="instrument_layout",
            outcome="partial", backfill_reason="漏记, 当场补录",
        )
        services.finalize(session, by=self.observer1)
        self.assertEqual(str(session.score_percent), "91.67")
        self.assertEqual(session.result, "pass")

        # 新会话使用新版本的冻结快照
        new_session = self.make_session(version=SOPVersion.objects.get(version="2.0"))
        self.assertEqual(new_session.snapshot["version"], "2.0")
        self.assertEqual(new_session.snapshot["pass_threshold"], 95)
        self.assertEqual(new_session.snapshot["retention_days"], 30)

    def test_snapshot_contains_steps_and_critical_items(self):
        version = make_version()
        session = self.make_session(version=version)
        codes = [s["code"] for s in session.snapshot["steps"]]
        self.assertEqual(
            codes,
            ["handwash", "donning", "item_transfer", "glove_contamination",
             "instrument_layout", "waste_disposal"],
        )
        item_codes = [i["code"] for i in session.snapshot["critical_items"]]
        self.assertIn("STERILE_BREACH", item_codes)
