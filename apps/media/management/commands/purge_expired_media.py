"""清除超过保留期限的视频: 删除 S3 对象, 元数据与访问审计保留备查."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.media import s3
from apps.media.models import VideoClip


class Command(BaseCommand):
    help = "删除 retention_until 已过的 S3 视频对象(支持 --dry-run)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="只统计不删除")

    def handle(self, *args, dry_run=False, **options):
        expired = VideoClip.objects.filter(
            status=VideoClip.Status.COMPLETED,
            retention_until__isnull=False,
            retention_until__lt=timezone.now(),
        )
        count = expired.count()
        if dry_run:
            self.stdout.write(f"[dry-run] {count} 个片段已过期")
            return
        storage = s3.get_storage()
        for clip in expired.iterator():
            storage.delete_object(clip.s3_key)
            clip.status = VideoClip.Status.PURGED
            clip.s3_key = ""
            clip.upload_id = ""
            clip.save(update_fields=["status", "s3_key", "upload_id"])
            self.stdout.write(f"已清除 clip#{clip.pk}")
        self.stdout.write(self.style.SUCCESS(f"共清除 {count} 个过期片段"))
