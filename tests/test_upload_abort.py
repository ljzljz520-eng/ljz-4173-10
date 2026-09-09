"""上传中止: 中止分片上传 -> S3 abort 被调用, 片段标记中止且不计入证据."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.media.models import VideoClip
from apps.media.s3 import S3VideoStorage

from .base import BaseCase


class UploadAbortTest(BaseCase):
    def setUp(self):
        self.session = self.make_session()
        self.client.force_login(self.observer1)

    @patch("apps.media.s3.get_storage")
    def test_abort_marks_clip_and_notifies_s3(self, mock_get_storage):
        storage = MagicMock()
        storage.create_multipart.return_value = "upload-abc"
        mock_get_storage.return_value = storage

        resp = self.client.post(
            reverse("media:init_upload", args=[self.session.id]),
            {"filename": "glove.mp4", "content_type": "video/mp4"},
        )
        self.assertEqual(resp.status_code, 200)
        clip_id = resp.json()["clip_id"]
        key = resp.json()["key"]

        resp = self.client.post(reverse("media:abort_upload", args=[clip_id]))
        self.assertEqual(resp.status_code, 200)

        storage.abort_multipart.assert_called_once_with(key, "upload-abc")
        clip = VideoClip.objects.get(pk=clip_id)
        self.assertEqual(clip.status, VideoClip.Status.ABORTED)
        # 中止的片段不算证据
        self.assertEqual(
            self.session.clips.filter(status=VideoClip.Status.COMPLETED).count(), 0
        )
        # 中止后不能补交完成
        resp = self.client.post(
            reverse("media:complete_upload", args=[clip_id]),
            data=json.dumps({"parts": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 409)

    def test_storage_abort_calls_boto_client(self):
        client = MagicMock()
        storage = S3VideoStorage(client=client, bucket="bucket-x")
        storage.abort_multipart("k/1", "u-9")
        client.abort_multipart_upload.assert_called_once_with(
            Bucket="bucket-x", Key="k/1", UploadId="u-9"
        )

    @patch("apps.media.s3.get_storage")
    def test_trainee_cannot_init_upload(self, mock_get_storage):
        self.client.force_login(self.trainee)
        resp = self.client.post(
            reverse("media:init_upload", args=[self.session.id]),
            {"filename": "x.mp4"},
        )
        self.assertEqual(resp.status_code, 403)
        mock_get_storage.return_value.create_multipart.assert_not_called()
