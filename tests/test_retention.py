"""保留期限: 完成上传时按冻结版本计算保留截止; 清除命令只处理过期对象."""
import json
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.media.models import VideoClip

from .base import BaseCase, make_version


class RetentionTest(BaseCase):
    def setUp(self):
        self.version = make_version(retention_days=30)
        self.session = self.make_session(version=self.version)
        self.client.force_login(self.observer1)

    def _init_and_complete(self, filename="a.mp4"):
        with patch("apps.media.s3.get_storage") as mock_get:
            storage = MagicMock()
            storage.create_multipart.return_value = "u1"
            storage.head_object.return_value = {"ContentLength": 2048}
            mock_get.return_value = storage
            resp = self.client.post(
                reverse("media:init_upload", args=[self.session.id]), {"filename": filename}
            )
            clip_id = resp.json()["clip_id"]
            resp = self.client.post(
                reverse("media:complete_upload", args=[clip_id]),
                data=json.dumps({"parts": [{"PartNumber": 1, "ETag": '"e1"'}]}),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
        return VideoClip.objects.get(pk=clip_id)

    def test_retention_computed_from_frozen_version(self):
        clip = self._init_and_complete()
        self.assertEqual(clip.status, VideoClip.Status.COMPLETED)
        self.assertEqual(clip.size_bytes, 2048)
        expected = clip.completed_at + timedelta(days=30)
        self.assertAlmostEqual(
            clip.retention_until.timestamp(), expected.timestamp(), delta=1.0
        )

    def test_purge_only_expired(self):
        expired = self._init_and_complete("old.mp4")
        fresh = self._init_and_complete("new.mp4")
        VideoClip.objects.filter(pk=expired.pk).update(
            retention_until=timezone.now() - timedelta(days=1)
        )

        with patch("apps.media.s3.get_storage") as mock_get:
            storage = MagicMock()
            mock_get.return_value = storage
            out = StringIO()
            call_command("purge_expired_media", stdout=out)

        storage.delete_object.assert_called_once_with(expired.s3_key)
        expired.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(expired.status, VideoClip.Status.PURGED)
        self.assertEqual(expired.s3_key, "")
        self.assertEqual(fresh.status, VideoClip.Status.COMPLETED)
        self.assertNotEqual(fresh.s3_key, "")
        # 审计记录随片段保留(片段行未删除)
        self.assertTrue(VideoClip.objects.filter(pk=expired.pk).exists())
