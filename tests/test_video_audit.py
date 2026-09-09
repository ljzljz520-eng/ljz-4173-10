"""视频访问审计: 授权访问与越权访问均留痕."""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from apps.media.models import VideoAccessAudit, VideoClip

from .base import BaseCase


class VideoAuditTest(BaseCase):
    def setUp(self):
        self.session = self.make_session()
        self.clip = VideoClip.objects.create(
            session=self.session,
            s3_key="sessions/1/clips/x/a.mp4",
            upload_id="u",
            status=VideoClip.Status.COMPLETED,
            uploaded_by=self.observer1,
        )

    @patch("apps.media.s3.get_storage")
    def test_authorized_access_is_audited_and_redirects(self, mock_get_storage):
        storage = MagicMock()
        storage.presign_get.return_value = "https://s3.example/presigned"
        mock_get_storage.return_value = storage

        self.client.force_login(self.trainee)
        resp = self.client.get(
            reverse("media:clip_access", args=[self.clip.id]),
            HTTP_USER_AGENT="TestAgent/1.0",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "https://s3.example/presigned")

        audit = VideoAccessAudit.objects.get()
        self.assertEqual(audit.clip, self.clip)
        self.assertEqual(audit.user, self.trainee)
        self.assertEqual(audit.action, VideoAccessAudit.Action.VIEW)
        self.assertEqual(audit.ip, "127.0.0.1")
        self.assertEqual(audit.user_agent, "TestAgent/1.0")

    @patch("apps.media.s3.get_storage")
    def test_denied_access_is_audited_without_url(self, mock_get_storage):
        storage = MagicMock()
        mock_get_storage.return_value = storage

        self.client.force_login(self.other_trainee)
        resp = self.client.get(reverse("media:clip_access", args=[self.clip.id]))
        self.assertEqual(resp.status_code, 403)

        audit = VideoAccessAudit.objects.get()
        self.assertEqual(audit.action, VideoAccessAudit.Action.DENIED)
        self.assertEqual(audit.user, self.other_trainee)
        storage.presign_get.assert_not_called()

    @patch("apps.media.s3.get_storage")
    def test_download_action_recorded(self, mock_get_storage):
        storage = MagicMock()
        storage.presign_get.return_value = "https://s3.example/dl"
        mock_get_storage.return_value = storage
        self.client.force_login(self.observer1)
        resp = self.client.get(reverse("media:clip_access", args=[self.clip.id]) + "?download=1")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(VideoAccessAudit.objects.get().action, VideoAccessAudit.Action.DOWNLOAD)
