from django.urls import path

from . import views

app_name = "experiments"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("datasets/new/", views.dataset_create, name="dataset_create"),
    path("datasets/<int:pk>/", views.dataset_detail, name="dataset_detail"),
    path("datasets/<int:pk>/images/upload/", views.image_upload, name="image_upload"),
    path("images/<int:image_id>/pose/", views.pose_edit, name="pose_edit"),
    path("runs/new/", views.run_create, name="run_create"),
    path("runs/<int:pk>/", views.run_detail, name="run_detail"),
    path("runs/<int:pk>/start/", views.run_start, name="run_start"),
    path("api/runs/<int:pk>/artifacts/", views.run_artifacts_json, name="run_artifacts_json"),
]

