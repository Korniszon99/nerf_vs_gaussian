from django.urls import path

from . import views

app_name = "experiments"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("datasets/setup-guide/", views.DatasetSetupGuideView.as_view(), name="dataset_setup_guide"),
    path("datasets/new/", views.dataset_create, name="dataset_create"),
    path("datasets/<int:pk>/", views.dataset_detail, name="dataset_detail"),
    path("datasets/<int:pk>/images/upload/", views.image_upload, name="image_upload"),
    path("datasets/<int:pk>/images/reimport/", views.dataset_reimport_images, name="dataset_reimport_images"),
    path("images/<int:image_id>/pose/", views.pose_edit, name="pose_edit"),
    path("runs/new/", views.run_create, name="run_create"),
    path("runs/<int:pk>/", views.run_detail, name="run_detail"),
    path("runs/<int:pk>/start/", views.run_start, name="run_start"),
    path("api/runs/<int:pk>/logs/", views.run_logs_json, name="run_logs_json"),
    path("api/runs/<int:pk>/artifacts/", views.run_artifacts_json, name="run_artifacts_json"),
]
