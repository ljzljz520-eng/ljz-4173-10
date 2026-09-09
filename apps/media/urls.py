from django.urls import path

from . import views

app_name = "media"

urlpatterns = [
    path("sessions/<int:session_id>/init/", views.init_upload, name="init_upload"),
    path("clips/<int:clip_id>/presign-part/", views.presign_part, name="presign_part"),
    path("clips/<int:clip_id>/complete/", views.complete_upload, name="complete_upload"),
    path("clips/<int:clip_id>/abort/", views.abort_upload, name="abort_upload"),
    path("clips/<int:clip_id>/access/", views.clip_access, name="clip_access"),
]
