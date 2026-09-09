"""观察业务规则: 计分 / 补录 / 冲突 / 关键失败确认 / 定稿."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import CriticalFailConfirmation, ObservationSession, ObserverConflict, StepRecord

OUTCOME_RATIO = {
    StepRecord.Outcome.PASS: Decimal("1.0"),
    StepRecord.Outcome.PARTIAL: Decimal("0.5"),
    StepRecord.Outcome.FAIL: Decimal("0.0"),
}


def _step_def(session, step_code):
    for step in session.snapshot.get("steps", []):
        if step["code"] == step_code:
            return step
    return None


@transaction.atomic
def record_step(*, session, observer, step_code, outcome, note="", backfill_reason=""):
    """按真实顺序追加一条步骤记录.

    - 会话必须处于进行中;
    - 同一观察员对同一步骤只能记录一次(原始记录不可改);
    - 若已有更靠后的步骤被记录, 本次属于补录, 必须填写补录原因;
    - 与其他观察员结论不一致时自动生成冲突;
    - 步骤不合格且命中版本关键失败触发项时, 自动生成"待确认"关键失败单.
    """
    if session.status != ObservationSession.Status.OPEN:
        raise ValidationError("会话已定稿, 不能继续记录。")
    step = _step_def(session, step_code)
    if step is None:
        raise ValidationError(f"未知步骤: {step_code}")
    if outcome not in StepRecord.Outcome.values:
        raise ValidationError("无效的观察结论。")
    if StepRecord.objects.filter(session=session, step_code=step_code, observer=observer).exists():
        raise ValidationError("您已记录过该步骤; 原始记录不可修改, 如有异议请由另一位观察员记录后走冲突解决。")

    locked = ObservationSession.objects.select_for_update().get(pk=session.pk)
    max_seq = locked.step_records.aggregate(m=Max("recorded_seq"))["m"] or 0
    is_backfilled = locked.step_records.filter(step_order__gt=step["order"]).exists()
    if is_backfilled and not backfill_reason.strip():
        raise ValidationError("该步骤顺序早于已记录步骤, 属于补录, 必须填写补录原因。")

    ratio = OUTCOME_RATIO.get(outcome, Decimal("0"))
    points = (Decimal(step["max_points"]) * ratio).quantize(Decimal("0.01"))
    record = StepRecord.objects.create(
        session=session,
        observer=observer,
        step_code=step["code"],
        step_name=step["name"],
        step_order=step["order"],
        max_points=step["max_points"],
        outcome=outcome,
        points_awarded=points,
        note=note,
        recorded_seq=max_seq + 1,
        is_backfilled=is_backfilled,
        backfill_reason=backfill_reason.strip(),
    )
    _flag_conflicts(session, record)
    if outcome == StepRecord.Outcome.FAIL:
        _suggest_critical_items(session, record)
    refresh_score(session)
    return record


def _flag_conflicts(session, record):
    others = session.step_records.filter(step_code=record.step_code).exclude(pk=record.pk)
    for other in others:
        if other.outcome != record.outcome:
            already_open = session.conflicts.filter(
                step_code=record.step_code, status=ObserverConflict.Status.OPEN
            ).exists()
            if not already_open:
                ObserverConflict.objects.create(
                    session=session, step_code=record.step_code, record_a=other, record_b=record
                )


def _suggest_critical_items(session, record):
    for item in session.snapshot.get("critical_items", []):
        if item.get("auto_trigger_step") == record.step_code:
            CriticalFailConfirmation.objects.get_or_create(
                session=session,
                item_code=item["code"],
                state=CriticalFailConfirmation.State.PENDING,
                defaults={
                    "item_description": item["description"],
                    "suggested_by_record": record,
                },
            )


def effective_outcomes(session):
    """每个步骤的生效结论: 已解决冲突以解决值为准, 否则以主观察员记录为准."""
    records_by_step = {}
    for rec in session.step_records.all():
        records_by_step.setdefault(rec.step_code, []).append(rec)
    resolved = {
        c.step_code: c for c in session.conflicts.filter(status=ObserverConflict.Status.RESOLVED)
    }
    result = {}
    for step in session.snapshot.get("steps", []):
        code = step["code"]
        if code in resolved:
            result[code] = resolved[code].resolved_outcome
            continue
        recs = records_by_step.get(code, [])
        if not recs:
            result[code] = None
        else:
            primary = next(
                (r for r in recs if r.observer_id == session.primary_observer_id), recs[0]
            )
            result[code] = primary.outcome
    return result


def compute_score(session):
    """按会话冻结的版本快照计分(满分制 -> 百分比)."""
    eff = effective_outcomes(session)
    earned = Decimal("0")
    available = Decimal("0")
    for step in session.snapshot.get("steps", []):
        outcome = eff.get(step["code"])
        if outcome is None or outcome == StepRecord.Outcome.NA:
            continue
        available += step["max_points"]
        earned += Decimal(step["max_points"]) * OUTCOME_RATIO.get(outcome, Decimal("0"))
    percent = (earned / available * 100).quantize(Decimal("0.01")) if available else None
    return {"earned": earned, "available": available, "percent": percent}


def refresh_score(session):
    score = compute_score(session)
    ObservationSession.objects.filter(pk=session.pk).update(score_percent=score["percent"])
    session.score_percent = score["percent"]
    return score


@transaction.atomic
def decide_critical(*, session, item_code, observer, confirm, note=""):
    """观察员确认或排除关键失败项(必须人工决定)."""
    conf = (
        session.critical_confirmations.filter(
            item_code=item_code, state=CriticalFailConfirmation.State.PENDING
        )
        .order_by("-created_at")
        .first()
    )
    if conf is None:
        raise ValidationError("没有待确认的关键失败项。")
    conf.state = (
        CriticalFailConfirmation.State.CONFIRMED
        if confirm
        else CriticalFailConfirmation.State.DISMISSED
    )
    conf.decided_by = observer
    conf.decided_at = timezone.now()
    conf.note = note
    conf.save(update_fields=["state", "decided_by", "decided_at", "note"])
    return conf


@transaction.atomic
def resolve_conflict(*, conflict, resolver, outcome, note=""):
    if conflict.status != ObserverConflict.Status.OPEN:
        raise ValidationError("该冲突已解决。")
    if outcome not in StepRecord.Outcome.values:
        raise ValidationError("无效的解决结论。")
    conflict.status = ObserverConflict.Status.RESOLVED
    conflict.resolved_by = resolver
    conflict.resolved_at = timezone.now()
    conflict.resolved_outcome = outcome
    conflict.resolution_note = note
    conflict.save()
    refresh_score(conflict.session)
    return conflict


@transaction.atomic
def finalize(session, *, by):
    """定稿: 校验完整性后按冻结版本给出最终结果.

    关键失败项必须全部经人工确认/排除; 存在确认项时无论得分均判不合格.
    """
    if session.status != ObservationSession.Status.OPEN:
        raise ValidationError("会话已定稿。")
    eff = effective_outcomes(session)
    missing = [code for code, outcome in eff.items() if outcome is None]
    if missing:
        raise ValidationError(f"以下步骤尚未记录: {', '.join(missing)}")
    if session.conflicts.filter(status=ObserverConflict.Status.OPEN).exists():
        raise ValidationError("存在未解决的观察员冲突, 不能定稿。")
    if session.critical_confirmations.filter(
        state=CriticalFailConfirmation.State.PENDING
    ).exists():
        raise ValidationError("存在待确认的关键失败项, 必须由观察员确认或排除。")

    score = compute_score(session)
    has_confirmed_critical = session.critical_confirmations.filter(
        state=CriticalFailConfirmation.State.CONFIRMED
    ).exists()
    threshold = session.snapshot.get("pass_threshold", 80)
    if has_confirmed_critical:
        result = ObservationSession.Result.FAIL
    elif score["percent"] is not None and score["percent"] >= threshold:
        result = ObservationSession.Result.PASS
    else:
        result = ObservationSession.Result.FAIL

    session.score_percent = score["percent"]
    session.result = result
    session.status = ObservationSession.Status.FINALIZED
    session.finalized_at = timezone.now()
    session.save(update_fields=["score_percent", "result", "status", "finalized_at"])
    return session
