from django.contrib import admin
from .models import CVATTask, WebhookLog


@admin.register(CVATTask)
class CVATTaskAdmin(admin.ModelAdmin):
    list_display = [
        "cvat_job_id",
        "task_name",
        "project_name",
        "assignee",
        "status",
        "state",
        "total_annotations",
        "last_synced_at",
    ]
    list_filter = ["status", "state", "assignee", "project_name"]
    search_fields = ["task_name", "project_name", "assignee", "cvat_job_id"]
    readonly_fields = ["created_at", "updated_at", "last_synced_at"]

    fieldsets = (
        ("Identificação CVAT", {
            "fields": ("cvat_task_id", "cvat_job_id", "cvat_url")
        }),
        ("Informações do Projeto", {
            "fields": ("project_id", "project_name", "task_name")
        }),
        ("Responsável e Status", {
            "fields": ("assignee", "status", "state")
        }),
        ("Anotações", {
            "fields": (
                "manual_annotations",
                "interpolated_annotations",
                "total_annotations"
            )
        }),
        ("Dados Técnicos", {
            "fields": ("cvat_data",),
            "classes": ("collapse",)
        }),
        ("Controle", {
            "fields": ("created_at", "updated_at", "last_synced_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "event_type",
        "status",
        "cvat_task",
        "source_ip",
        "received_at",
        "processed_at",
    ]
    list_filter = ["event_type", "status", "received_at"]
    search_fields = ["event_type", "source_ip"]
    readonly_fields = ["received_at", "processed_at"]

    fieldsets = (
        ("Evento", {
            "fields": ("event_type", "status", "source_ip")
        }),
        ("Relacionamento", {
            "fields": ("cvat_task",)
        }),
        ("Payload", {
            "fields": ("payload",),
            "classes": ("collapse",)
        }),
        ("Erro", {
            "fields": ("error_message",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("received_at", "processed_at"),
            "classes": ("collapse",)
        }),
    )
