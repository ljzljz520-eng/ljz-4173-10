from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.exercises.models import ObservationSession

from .models import ReReviewRequest, TraineeResponse


@transaction.atomic
def add_response(*, session, author, body):
    """学员/观察员追加回应. 只新增, 不提供修改与删除入口."""
    if not body.strip():
        raise ValidationError("回应内容不能为空。")
    allowed = (
        session.trainee_id == author.id
        or author.can_observe()
    )
    if not allowed:
        raise PermissionDenied("无权在该会话下回应。")
    return TraineeResponse.objects.create(session=session, author=author, body=body.strip())


@transaction.atomic
def request_rereview(*, session, user, reason):
    if session.trainee_id != user.id:
        raise PermissionDenied("仅学员本人可申请复评。")
    if session.status != ObservationSession.Status.FINALIZED:
        raise ValidationError("会话定稿后才能申请复评。")
    if session.rereview_requests.filter(status=ReReviewRequest.Status.OPEN).exists():
        raise ValidationError("已有待处理的复评申请。")
    if not reason.strip():
        raise ValidationError("请填写申请理由。")
    return ReReviewRequest.objects.create(session=session, requested_by=user, reason=reason.strip())


@transaction.atomic
def resolve_rereview(*, request_obj, resolver, accept, note=""):
    """受理复评: 以相同冻结版本/物种/区域开启新会话, 原会话与原意见全部保留."""
    if not resolver.can_observe():
        raise PermissionDenied("仅观察员可处理复评申请。")
    if request_obj.status != ReReviewRequest.Status.OPEN:
        raise ValidationError("该申请已处理。")
    request_obj.status = (
        ReReviewRequest.Status.ACCEPTED if accept else ReReviewRequest.Status.DECLINED
    )
    request_obj.resolved_by = resolver
    request_obj.resolved_at = timezone.now()
    request_obj.resolution_note = note
    request_obj.save()
    new_session = None
    if accept:
        old = request_obj.session
        new_session = ObservationSession.objects.create(
            trainee=old.trainee,
            primary_observer=resolver,
            sop_version=old.sop_version,
            species_category=old.species_category,
            operation_area=old.operation_area,
            supersedes=old,
        )
    return new_session
