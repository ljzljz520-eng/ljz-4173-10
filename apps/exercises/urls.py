from django.urls import path

from . import views

app_name = "exercises"

urlpatterns = [
    path("", views.session_list, name="list"),
    path("sessions/new/", views.session_create, name="create"),
    path("sessions/<int:pk>/", views.session_detail, name="detail"),
    path("sessions/<int:pk>/record-step/", views.record_step, name="record_step"),
    path("sessions/<int:pk>/critical/<str:item_code>/", views.decide_critical, name="decide_critical"),
    path("sessions/<int:pk>/conflicts/<int:conflict_id>/resolve/", views.resolve_conflict, name="resolve_conflict"),
    path("sessions/<int:pk>/finalize/", views.finalize, name="finalize"),
]
