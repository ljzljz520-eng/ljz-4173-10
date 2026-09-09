"""端到端冒烟: 经 HTMX 端点完成 建会话 -> 记录 -> 定稿 -> 学员回应."""
from django.urls import reverse

from apps.exercises.models import ObservationSession

from .base import BaseCase, make_version


class ViewSmokeTest(BaseCase):
    def setUp(self):
        self.version = make_version()
        self.client.force_login(self.observer1)

    def test_full_flow_via_views(self):
        resp = self.client.post(
            reverse("exercises:create"),
            {
                "trainee": self.trainee.id,
                "sop_version": self.version.id,
                "species_category": "rodent",
                "operation_area": "barrier",
            },
        )
        session = ObservationSession.objects.get()
        self.assertRedirects(resp, reverse("exercises:detail", args=[session.id]))

        resp = self.client.get(reverse("exercises:detail", args=[session.id]))
        self.assertContains(resp, "观察表")
        self.assertContains(resp, "v1.0")

        for code in ["handwash", "donning", "item_transfer",
                     "glove_contamination", "instrument_layout", "waste_disposal"]:
            resp = self.client.post(
                reverse("exercises:record_step", args=[session.id]),
                {"step_code": code, "outcome": "pass"},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(resp.status_code, 200, code)
        self.assertContains(resp, "100.00")

        resp = self.client.post(reverse("exercises:finalize", args=[session.id]))
        self.assertRedirects(resp, reverse("exercises:detail", args=[session.id]))
        session.refresh_from_db()
        self.assertEqual(session.status, "finalized")
        self.assertEqual(session.result, "pass")

        # 学员回应(HTMX 局部刷新)
        self.client.force_login(self.trainee)
        resp = self.client.post(
            reverse("reviews:add_response", args=[session.id]), {"body": "收到, 谢谢指导"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "收到, 谢谢指导")

        # 定稿后观察员不能再记录
        self.client.force_login(self.observer1)
        resp = self.client.post(
            reverse("exercises:record_step", args=[session.id]),
            {"step_code": "handwash", "outcome": "fail"},
        )
        self.assertContains(resp, "已定稿")

    def test_trainee_cannot_record_steps(self):
        session = self.make_session(version=self.version)
        self.client.force_login(self.trainee)
        resp = self.client.post(
            reverse("exercises:record_step", args=[session.id]),
            {"step_code": "handwash", "outcome": "pass"},
        )
        self.assertContains(resp, "仅观察员")
        self.assertEqual(session.step_records.count(), 0)
