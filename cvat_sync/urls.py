"""
URLs do app cvat_sync.
"""
from django.urls import path
from .views import (
    CVATTaskListView,
    CVATTaskDetailView,
    sync_cvat_view,
    cvat_webhook_view,
    update_task_field,
    update_task_responsaveis,
    dashboard_metrics
)


urlpatterns = [
    path("", CVATTaskListView.as_view(), name="cvat_task_list"),
    path("<int:pk>/", CVATTaskDetailView.as_view(), name="cvat_task_detail"),
    path("sync/", sync_cvat_view, name="cvat_sync"),
    path("webhook/", cvat_webhook_view, name="cvat_webhook"),

    # API endpoints
    path("api/update-field/", update_task_field, name="update_task_field"),
    path("api/update-responsaveis/", update_task_responsaveis, name="update_task_responsaveis"),
    path("api/dashboard-metrics/", dashboard_metrics, name="dashboard_metrics"),
]
