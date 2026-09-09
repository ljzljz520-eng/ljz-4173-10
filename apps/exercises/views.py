"""观察表交互: HTMX 局部刷新观察面板."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.sops.models import SOPVersion

from . import services
from .models import ObservationSession, ObserverConflict, StepRecord


def _require_observer(user):
    if not user.can_observe():
        raise PermissionDenied("仅观察员或管理员可执行该操作。")


def _panel_context(session, user, error=None):
    records_by_step = {}
    for rec in session.step_records.select_related("observer"):
        records_by_step.setdefault(rec.step_code, []).append(rec)
    eff = services.effective_outcomes(session)
    rows = []
    for step in session.snapshot.get("steps", []):
        recs = records_by_step.get(step["code"], [])
        rows.append(
            {
                "step": step,
                "records": recs,
                "effective": eff.get(step["code"]),
                "recorded_by_me": any(r.observer_id == user.id for r in recs),
            }
        )
    return {
        "session": session,
        "rows": rows,
        "score": services.compute_score(session),
        "criticals": session.critical_confirmations.select_related("decided_by"),
        "conflicts": session.conflicts.select_related(
            "record_a__observer", "record_b__observer", "resolved_by"
        ),
        "can_record": user.can_observe() and session.status == ObservationSession.Status.OPEN,
        "error": error,
    }


@login_required
def session_list(request):
    qs = ObservationSession.objects.select_related("trainee", "primary_observer", "sop_version")
    if request.user.is_trainee:
        qs = qs.filter(trainee=request.user)
    return render(request, "exercises/list.html", {"sessions": qs})


@login_required
def session_create(request):
    _require_observer(request.user)
    if request.method == "POST":
        version = get_object_or_404(SOPVersion, pk=request.POST.get("sop_version"))
        session = ObservationSession.objects.create(
            trainee_id=request.POST.get("trainee"),
            primary_observer=request.user,
            sop_version=version,
            species_category=request.POST.get("species_category"),
            operation_area=request.POST.get("operation_area"),
        )
        messages.success(request, f"已创建观察会话 #{session.pk}, 流程版本已冻结为 {version.version}。")
        return redirect("exercises:detail", pk=session.pk)
    from apps.accounts.models import User

    return render(
        request,
        "exercises/create.html",
        {
            "versions": SOPVersion.objects.filter(is_current=True),
            "trainees": User.objects.filter(role=User.Role.TRAINEE),
            "species_choices": ObservationSession.Species.choices,
            "area_choices": ObservationSession.Area.choices,
        },
    )


@login_required
def session_detail(request, pk):
    session = get_object_or_404(
        ObservationSession.objects.select_related("trainee", "primary_observer", "sop_version"), pk=pk
    )
    ctx = _panel_context(session, request.user)
    ctx.update(
        {
            "clips": session.clips.exclude(status="aborted").order_by("-created_at"),
            "responses": session.responses.select_related("author"),
            "rereviews": session.rereview_requests.select_related("requested_by", "resolved_by"),
            "outcome_choices": StepRecord.Outcome.choices,
            "can_respond": request.user == session.trainee or request.user.can_observe(),
        }
    )
    return render(request, "exercises/detail.html", ctx)


@login_required
@require_POST
def record_step(request, pk):
    session = get_object_or_404(ObservationSession, pk=pk)
    try:
        _require_observer(request.user)
        services.record_step(
            session=session,
            observer=request.user,
            step_code=request.POST.get("step_code", ""),
            outcome=request.POST.get("outcome", ""),
            note=request.POST.get("note", ""),
            backfill_reason=request.POST.get("backfill_reason", ""),
        )
        error = None
    except (ValidationError, PermissionDenied) as exc:
        error = exc.message if hasattr(exc, "message") else str(exc)
    session.refresh_from_db()
    return render(request, "exercises/_observation_panel.html", _panel_context(session, request.user, error))


@login_required
@require_POST
def decide_critical(request, pk, item_code):
    session = get_object_or_404(ObservationSession, pk=pk)
    try:
        _require_observer(request.user)
        services.decide_critical(
            session=session,
            item_code=item_code,
            observer=request.user,
            confirm=request.POST.get("decision") == "confirm",
            note=request.POST.get("note", ""),
        )
        error = None
    except (ValidationError, PermissionDenied) as exc:
        error = exc.message if hasattr(exc, "message") else str(exc)
    session.refresh_from_db()
    return render(request, "exercises/_observation_panel.html", _panel_context(session, request.user, error))


@login_required
@require_POST
def resolve_conflict(request, pk, conflict_id):
    session = get_object_or_404(ObservationSession, pk=pk)
    conflict = get_object_or_404(ObserverConflict, pk=conflict_id, session=session)
    try:
        _require_observer(request.user)
        services.resolve_conflict(
            conflict=conflict,
            resolver=request.user,
            outcome=request.POST.get("outcome", ""),
            note=request.POST.get("note", ""),
        )
        error = None
    except (ValidationError, PermissionDenied) as exc:
        error = exc.message if hasattr(exc, "message") else str(exc)
    session.refresh_from_db()
    return render(request, "exercises/_observation_panel.html", _panel_context(session, request.user, error))


@login_required
@require_POST
def finalize(request, pk):
    session = get_object_or_404(ObservationSession, pk=pk)
    try:
        _require_observer(request.user)
        services.finalize(session, by=request.user)
        messages.success(request, f"会话 #{session.pk} 已定稿: {session.get_result_display()}")
    except (ValidationError, PermissionDenied) as exc:
        msg = exc.message if hasattr(exc, "message") else str(exc)
        messages.error(request, msg)
    return redirect("exercises:detail", pk=pk)
