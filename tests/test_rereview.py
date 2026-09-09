"""学员回应与复评: 原意见不删除; 受理复评开启沿用冻结版本的新会话."""
from django.core.exceptions import PermissionDenied, ValidationError

from apps.exercises import services as ex_services
from apps.exercises.models import ObservationSession
from apps.reviews import services
from apps.reviews.models import ReReviewRequest, TraineeResponse

from .base import BaseCase


class ReReviewTest(BaseCase):
    def _finalized_session(self):
        session = self.make_session()
        self.record_all(session, self.observer1)
        ex_services.finalize(session, by=self.observer1)
        return session

    def test_trainee_responds_and_original_kept_after_decline(self):
        session = self._finalized_session()
        r1 = services.add_response(session=session, author=self.trainee, body="当时已更换手套, 请复核。")
        req = services.request_rereview(session=session, user=self.trainee, reason="对结论有异议")
        services.resolve_rereview(request_obj=req, resolver=self.observer1, accept=False, note="证据充分")

        # 原回应与原结论都保留
        self.assertTrue(TraineeResponse.objects.filter(pk=r1.pk).exists())
        req.refresh_from_db()
        self.assertEqual(req.status, ReReviewRequest.Status.DECLINED)
        session.refresh_from_db()
        self.assertEqual(session.result, ObservationSession.Result.PASS)

    def test_accepted_rereview_opens_new_session_with_same_frozen_version(self):
        session = self._finalized_session()
        req = services.request_rereview(session=session, user=self.trainee, reason="申请复评")
        new_session = services.resolve_rereview(
            request_obj=req, resolver=self.observer2, accept=True
        )
        self.assertEqual(new_session.supersedes, session)
        self.assertEqual(new_session.snapshot, session.snapshot)
        self.assertEqual(new_session.status, ObservationSession.Status.OPEN)
        # 原会话保持定稿
        session.refresh_from_db()
        self.assertEqual(session.status, ObservationSession.Status.FINALIZED)

    def test_only_trainee_can_request_and_only_once(self):
        session = self._finalized_session()
        with self.assertRaises(PermissionDenied):
            services.request_rereview(session=session, user=self.other_trainee, reason="x")
        with self.assertRaises(ValidationError):
            services.request_rereview(session=session, user=self.trainee, reason="")
        services.request_rereview(session=session, user=self.trainee, reason="合理理由")
        with self.assertRaises(ValidationError):
            services.request_rereview(session=session, user=self.trainee, reason="重复申请")

    def test_response_requires_participation(self):
        session = self._finalized_session()
        with self.assertRaises(PermissionDenied):
            services.add_response(session=session, author=self.other_trainee, body="无关回应")
