from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class CVATTask(models.Model):
    """
    Modelo para armazenar tasks/jobs sincronizadas do CVAT.
    """

    # Identificadores únicos do CVAT
    cvat_task_id = models.IntegerField(
        verbose_name="CVAT Task ID",
        help_text="ID da task no CVAT"
    )
    cvat_job_id = models.IntegerField(
        verbose_name="CVAT Job ID",
        help_text="ID do job no CVAT",
        unique=True
    )

    # Informações do projeto
    project_id = models.IntegerField(
        verbose_name="Project ID",
        null=True,
        blank=True,
        help_text="ID do projeto no CVAT"
    )
    project_name = models.CharField(
        max_length=255,
        verbose_name="Nome do Projeto",
        null=True,
        blank=True
    )

    # Informações da task
    task_name = models.CharField(
        max_length=255,
        verbose_name="Nome da Task"
    )

    # Informações do responsável
    assignee = models.CharField(
        max_length=100,
        verbose_name="Responsável",
        null=True,
        blank=True,
        help_text="Username do responsável no CVAT"
    )

    # Responsáveis do sistema (múltiplos usuários)
    responsavel = models.ManyToManyField(
        User,
        related_name='assigned_tasks',
        blank=True,
        verbose_name="Responsáveis",
        help_text="Usuários responsáveis por esta task"
    )

    # Status, Stage e Estado do CVAT (mantidos para referência)
    cvat_status = models.CharField(
        max_length=50,
        verbose_name="Status CVAT",
        null=True,
        blank=True,
        help_text="Status original do job no CVAT (new, validation, completed, etc.)"
    )
    stage = models.CharField(
        max_length=50,
        verbose_name="Etapa",
        null=True,
        blank=True,
        help_text="Etapa do workflow (annotation, validation, acceptance)"
    )
    cvat_state = models.CharField(
        max_length=50,
        verbose_name="Estado CVAT",
        null=True,
        blank=True,
        help_text="Estado original de progresso do job no CVAT (in progress, completed, etc.)"
    )

    # Status do Sistema (novo - 5 opções em português)
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('em_andamento', 'Em Andamento'),
        ('conferindo', 'Conferindo'),
        ('feito', 'Feito'),
        ('revisado', 'Revisado'),
    ]

    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='pendente',
        verbose_name="Status",
        help_text="Status atual da task no sistema"
    )

    # Flag para controlar se status foi editado manualmente
    manual_override = models.BooleanField(
        default=False,
        verbose_name="Override Manual",
        help_text="Se True, status não será sobrescrito pelo webhook do CVAT"
    )

    # Datas adicionais
    data_inicio = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de Início",
        help_text="Data de início da task"
    )
    data_conclusao = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Data de Conclusão",
        help_text="Data e hora de conclusão da task"
    )

    # Contadores de anotações
    manual_annotations = models.IntegerField(
        default=0,
        verbose_name="Anotações Manuais",
        help_text="Total de anotações feitas manualmente"
    )
    interpolated_annotations = models.IntegerField(
        default=0,
        verbose_name="Anotações Interpoladas",
        help_text="Total de anotações interpoladas automaticamente"
    )
    total_annotations = models.IntegerField(
        default=0,
        verbose_name="Total de Anotações",
        help_text="Total de anotações (manuais + interpoladas)"
    )

    # URL direta para CVAT
    cvat_url = models.URLField(
        max_length=500,
        verbose_name="URL do CVAT",
        null=True,
        blank=True,
        help_text="Link direto para a task no CVAT"
    )

    # Dados completos do CVAT (para referência)
    cvat_data = models.JSONField(
        verbose_name="Dados do CVAT",
        null=True,
        blank=True,
        help_text="Payload completo do CVAT para referência"
    )

    # Controle de sincronização
    last_synced_at = models.DateTimeField(
        verbose_name="Última Sincronização",
        auto_now=False,  # FIX: Manual update only (not on every save)
        default=timezone.now,  # Default on creation
        help_text="Data e hora da última sincronização"
    )
    created_at = models.DateTimeField(
        verbose_name="Data de Criação",
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="Data de Atualização",
        auto_now=True
    )

    class Meta:
        verbose_name = "CVAT Task"
        verbose_name_plural = "CVAT Tasks"
        ordering = ["-cvat_job_id"]  # Jobs mais recentes primeiro (IDs maiores = mais novos)
        indexes = [
            models.Index(fields=["cvat_task_id", "cvat_job_id"]),
            models.Index(fields=["project_id"]),
            models.Index(fields=["assignee"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.task_name} (Job #{self.cvat_job_id})"

    @property
    def completion_percentage(self):
        """Calcula a porcentagem de conclusão baseada no status."""
        status_map = {
            "revisado": 100,
            "feito": 100,
            "conferindo": 80,
            "em_andamento": 50,
            "pendente": 0,
        }
        return status_map.get(self.status, 0)

    def get_status_badge_class(self):
        """Retorna a classe CSS para o badge do status."""
        status_classes = {
            'pendente': 'badge-pendente',
            'em_andamento': 'badge-em_andamento',
            'conferindo': 'badge-conferindo',
            'feito': 'badge-feito',
            'revisado': 'badge-revisado',
        }
        return status_classes.get(self.status, 'badge-secondary')

    def get_status_icon(self):
        """Retorna o ícone FontAwesome para o status."""
        status_icons = {
            'pendente': 'fa-circle',
            'em_andamento': 'fa-clock',
            'conferindo': 'fa-search',
            'feito': 'fa-check-circle',
            'revisado': 'fa-check-double',
        }
        return status_icons.get(self.status, 'fa-circle')

    def get_status_color(self):
        """Retorna a cor Tailwind para o status."""
        status_colors = {
            'pendente': 'gray',
            'em_andamento': 'orange',
            'conferindo': 'cyan',
            'feito': 'green',
            'revisado': 'green',
        }
        return status_colors.get(self.status, 'gray')

    @classmethod
    def get_status_display_name(cls, status_key):
        """Retorna o nome de exibição do status."""
        return dict(cls.STATUS_CHOICES).get(status_key, status_key)


class WebhookLog(models.Model):
    """
    Modelo para registrar webhooks recebidos do CVAT.
    """

    # Evento
    event_type = models.CharField(
        max_length=100,
        verbose_name="Tipo de Evento",
        help_text="Tipo de evento recebido (create, update, delete)"
    )

    # Payload recebido
    payload = models.JSONField(
        verbose_name="Payload",
        help_text="Dados completos recebidos do webhook"
    )

    # Task relacionada (pode ser null se a task não existir)
    cvat_task = models.ForeignKey(
        CVATTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_logs",
        verbose_name="Task CVAT"
    )

    # Status do processamento
    STATUS_CHOICES = [
        ('pending', 'Pendente'),
        ('processing', 'Processando'),
        ('success', 'Sucesso'),
        ('error', 'Erro'),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Status"
    )

    # Mensagem de erro (se houver)
    error_message = models.TextField(
        null=True,
        blank=True,
        verbose_name="Mensagem de Erro"
    )

    # IP de origem
    source_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP de Origem"
    )

    # Timestamps
    received_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Recebido em"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Processado em"
    )

    class Meta:
        verbose_name = "Webhook Log"
        verbose_name_plural = "Webhook Logs"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["-received_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.status} ({self.received_at})"
