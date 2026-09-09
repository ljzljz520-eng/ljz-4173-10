from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.exercises.models import ObservationSession

from . import services
from .models import ReReviewRequest


@login_required
@require_POST
def add_response(request, session_id):
    session = get_object_or_404(ObservationSession, pk=session_id)
    error = None
    try:
        services.add_response(session=session, author=request.user, body=request.POST.get("body", ""))
    except (ValidationError, PermissionDenied) as exc:
        error = exc.message if hasattr(exc, "message") else str(exc)
    return render(
        request,
        "reviews/_responses_panel.html",
        {
            "session": session,
            "responses": session.responses.select_related("author"),
            "error": error,
            "can_respond": request.user == session.trainee or request.user.can_observe(),
        },
    )


@login_required
@require_POST
def request_rereview(request, session_id):
    session = get_object_or_404(ObservationSession, pk=session_id)
    try:
        services.request_rereview(session=session, user=request.user, reason=request.POST.get("reason", ""))
        messages.success(request, "复评申请已提交。")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else str(exc))
    return redirect("exercises:detail", pk=session.pk)


@login_required
@require_POST
def resolve_rereview(request, request_id):
    req = get_object_or_404(ReReviewRequest, pk=request_id)
    try:
        new_session = services.resolve_rereview(
            request_obj=req,
            resolver=request.user,
            accept=request.POST.get("decision") == "accept",
            note=request.POST.get("note", ""),
        )
        if new_session:
            messages.success(request, f"已受理, 新会话 #{new_session.pk} 已开启(沿用冻结版本)。")
            return redirect("exercises:detail", pk=new_session.pk)
        messages.info(request, "复评申请已驳回, 原结论与意见保留。")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, exc.message if hasattr(exc, "message") else str(exc))
    return redirect("exercises:detail", pk=req.session_id)
