from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("sessions/<int:session_id>/respond/", views.add_response, name="add_response"),
    path("sessions/<int:session_id>/rereview/", views.request_rereview, name="request_rereview"),
    path("rereview/<int:request_id>/resolve/", views.resolve_rereview, name="resolve_rereview"),
]
