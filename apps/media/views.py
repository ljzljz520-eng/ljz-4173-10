"""视频上传(直传 S3)与访问审计."""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.exercises.models import ObservationSession

from . import s3
from .models import VideoAccessAudit, VideoClip


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _can_upload(user, session):
    return user.can_observe() and session.status == ObservationSession.Status.OPEN


def _can_view(user, clip):
    if clip.status != VideoClip.Status.COMPLETED:
        return False
    return user.can_observe() or clip.session.trainee_id == user.id


def _audit(clip, user, action, request):
    VideoAccessAudit.objects.create(
        clip=clip,
        user=user if user.is_authenticated else None,
        action=action,
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:256],
    )


@login_required
@require_POST
def init_upload(request, session_id):
    session = get_object_or_404(ObservationSession, pk=session_id)
    if not _can_upload(request.user, session):
        return HttpResponseForbidden("仅观察员可在进行中的会话上传视频。")
    filename = request.POST.get("filename", "clip.mp4")[:200]
    content_type = request.POST.get("content_type", "video/mp4")
    key = f"sessions/{session.pk}/clips/{uuid.uuid4().hex}/{filename}"
    upload_id = s3.get_storage().create_multipart(key, content_type)
    clip = VideoClip.objects.create(
        session=session,
        step_record_id=request.POST.get("step_record_id") or None,
        s3_key=key,
        upload_id=upload_id,
        original_filename=filename,
        content_type=content_type,
        uploaded_by=request.user,
    )
    return JsonResponse({"clip_id": clip.pk, "key": key, "upload_id": upload_id})


@login_required
def presign_part(request, clip_id):
    clip = get_object_or_404(VideoClip, pk=clip_id)
    if clip.uploaded_by_id != request.user.id and not request.user.can_observe():
        return HttpResponseForbidden()
    if clip.status != VideoClip.Status.PENDING:
        return JsonResponse({"error": "上传已结束"}, status=409)
    part_number = int(request.GET.get("part_number", "1"))
    url = s3.get_storage().presign_part(clip.s3_key, clip.upload_id, part_number)
    return JsonResponse({"url": url})


@login_required
@require_POST
def complete_upload(request, clip_id):
    clip = get_object_or_404(VideoClip, pk=clip_id)
    if clip.uploaded_by_id != request.user.id and not request.user.can_observe():
        return HttpResponseForbidden()
    if clip.status != VideoClip.Status.PENDING:
        return JsonResponse({"error": "上传已结束"}, status=409)
    payload = json.loads(request.body.decode() or "{}")
    parts = payload.get("parts", [])
    storage = s3.get_storage()
    storage.complete_multipart(clip.s3_key, clip.upload_id, parts)
    head = storage.head_object(clip.s3_key)
    clip.size_bytes = head.get("ContentLength")
    clip.status = VideoClip.Status.COMPLETED
    clip.completed_at = timezone.now()
    # 保留期限来自会话冻结的流程版本, 版本更换不影响已冻结证据
    days = int(clip.session.snapshot.get("retention_days") or 0)
    clip.retention_until = clip.completed_at + timezone.timedelta(days=days)
    clip.save()
    return JsonResponse(
        {"status": "completed", "retention_until": clip.retention_until.isoformat()}
    )


@login_required
@require_POST
def abort_upload(request, clip_id):
    """上传中止: 通知 S3 中止分片上传并标记片段, 中止的片段不计入证据."""
    clip = get_object_or_404(VideoClip, pk=clip_id)
    if clip.uploaded_by_id != request.user.id and not request.user.can_observe():
        return HttpResponseForbidden()
    if clip.status == VideoClip.Status.PENDING:
        s3.get_storage().abort_multipart(clip.s3_key, clip.upload_id)
        clip.status = VideoClip.Status.ABORTED
        clip.save(update_fields=["status"])
    return JsonResponse({"status": "aborted"})


@login_required
def clip_access(request, clip_id):
    """访问授权片段: 每次访问(含拒绝)都写审计, 然后重定向到短时预签名 URL."""
    clip = get_object_or_404(VideoClip, pk=clip_id)
    action = (
        VideoAccessAudit.Action.DOWNLOAD
        if request.GET.get("download")
        else VideoAccessAudit.Action.VIEW
    )
    if not _can_view(request.user, clip):
        _audit(clip, request.user, VideoAccessAudit.Action.DENIED, request)
        return HttpResponseForbidden("无权访问该视频片段。")
    _audit(clip, request.user, action, request)
    url = s3.get_storage().presign_get(clip.s3_key, download=bool(request.GET.get("download")))
    return redirect(url)
