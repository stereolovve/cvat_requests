"""
URLs do app cvat_sync.
"""
from django.urls import path
from .views import CVATTaskListView, CVATTaskDetailView, sync_cvat_view, cvat_webhook_view


urlpatterns = [
    path("", CVATTaskListView.as_view(), name="cvat_task_list"),
    path("<int:pk>/", CVATTaskDetailView.as_view(), name="cvat_task_detail"),
    path("sync/", sync_cvat_view, name="cvat_sync"),
    path("webhook/", cvat_webhook_view, name="cvat_webhook"),
]
