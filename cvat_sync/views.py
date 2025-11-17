from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView
from django.contrib import messages
from django.core.management import call_command
from django.db.models import Q, Sum, Count
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from .models import CVATTask, WebhookLog
import io
import sys
import json
import hmac
import hashlib
import requests


class CVATTaskListView(ListView):
    """View para listar tasks sincronizadas do CVAT com 3 modos de visualização."""
    model = CVATTask
    template_name = "cvat_sync/task_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        # Para dashboard view, não precisamos paginar
        view_mode = self.request.GET.get("view", "list")
        if view_mode == "dashboard":
            return CVATTask.objects.none()  # Dashboard não usa queryset

        queryset = CVATTask.objects.all()

        # Filtro por busca (task_name ou project_name)
        search = self.request.GET.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(task_name__icontains=search) |
                Q(project_name__icontains=search)
            )

        # Filtro por projeto
        project_filter = self.request.GET.get("project", "").strip()
        if project_filter:
            queryset = queryset.filter(project_name=project_filter)

        # Filtro por responsável
        assignee_filter = self.request.GET.get("assignee", "").strip()
        if assignee_filter:
            queryset = queryset.filter(assignee=assignee_filter)

        # Filtro por status
        status_filter = self.request.GET.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Ordenação customizada
        sort_field = self.request.GET.get("sort", "cvat_job_id")
        sort_order = self.request.GET.get("order", "desc")

        # Mapping de campos permitidos para ordenação
        sortable_fields = {
            'cvat_task_id': 'cvat_task_id',
            'cvat_job_id': 'cvat_job_id',
            'task_name': 'task_name',
            'project_name': 'project_name',
            'total_annotations': 'total_annotations',
            'last_synced_at': 'last_synced_at',
        }

        # Validar campo de ordenação
        if sort_field in sortable_fields:
            order_field = sortable_fields[sort_field]
            if sort_order == 'asc':
                queryset = queryset.order_by(order_field)
            else:
                queryset = queryset.order_by(f'-{order_field}')
        else:
            # Fallback para ordenação padrão
            queryset = queryset.order_by('-cvat_job_id')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # View mode
        view_mode = self.request.GET.get("view", "list")
        context["view_mode"] = view_mode

        # Adicionar filtros ao contexto
        context["search"] = self.request.GET.get("search", "")
        context["project_filter"] = self.request.GET.get("project", "")
        context["assignee_filter"] = self.request.GET.get("assignee", "")
        context["status_filter"] = self.request.GET.get("status", "")

        # Adicionar informações de ordenação
        context["sort_field"] = self.request.GET.get("sort", "cvat_job_id")
        context["sort_order"] = self.request.GET.get("order", "desc")

        # Listas únicas para filtros
        context["projects"] = CVATTask.objects.values_list("project_name", flat=True).distinct().order_by("project_name")
        context["assignees"] = CVATTask.objects.values_list("assignee", flat=True).distinct().order_by("assignee")
        context["status_choices"] = CVATTask.STATUS_CHOICES

        # Estatísticas gerais
        total_tasks = CVATTask.objects.count()
        tasks_em_andamento = CVATTask.objects.filter(status='em_andamento').count()
        tasks_concluidas = CVATTask.objects.filter(status__in=['feito', 'revisado']).count()
        total_annotations = CVATTask.objects.aggregate(
            total=Sum("total_annotations")
        )["total"] or 0

        context["stats"] = {
            "total_tasks": total_tasks,
            "total_annotations": total_annotations,
        }
        context["tasks_em_andamento"] = tasks_em_andamento
        context["tasks_concluidas"] = tasks_concluidas

        # Para grouped view, agrupar tasks por status
        if view_mode == "grouped":
            tasks_por_status = {}
            for status_value, status_label in CVATTask.STATUS_CHOICES:
                # Aplicar mesmos filtros
                queryset = CVATTask.objects.filter(status=status_value)

                search = self.request.GET.get("search", "").strip()
                if search:
                    queryset = queryset.filter(
                        Q(task_name__icontains=search) |
                        Q(project_name__icontains=search)
                    )

                project_filter = self.request.GET.get("project", "").strip()
                if project_filter:
                    queryset = queryset.filter(project_name=project_filter)

                assignee_filter = self.request.GET.get("assignee", "").strip()
                if assignee_filter:
                    queryset = queryset.filter(assignee=assignee_filter)

                queryset = queryset.order_by("-cvat_job_id")

                tasks_por_status[status_value] = {
                    'count': queryset.count(),
                    'tasks': list(queryset)
                }

            context["tasks_por_status"] = tasks_por_status

        return context


class CVATTaskDetailView(DetailView):
    """View para exibir detalhes de uma task do CVAT."""
    model = CVATTask
    template_name = "cvat_sync/task_detail.html"
    context_object_name = "task"


def sync_cvat_view(request):
    """View para disparar sincronização manual do CVAT."""
    if request.method == "POST":
        try:
            # Capturar output do comando
            output = io.StringIO()
            call_command("sync_cvat", stdout=output)

            # Exibir mensagem de sucesso
            messages.success(
                request,
                f"Sincronização concluída com sucesso!"
            )

        except Exception as e:
            messages.error(
                request,
                f"Erro na sincronização: {str(e)}"
            )

    return redirect("cvat_task_list")


@csrf_exempt
@require_http_methods(["POST"])
def cvat_webhook_view(request):
    """
    Endpoint para receber webhooks do CVAT.

    Valida a assinatura HMAC e processa eventos de create/update/delete.
    """
    # Criar log inicial
    webhook_log = WebhookLog(
        event_type="unknown",
        payload={},
        status="pending",
        source_ip=get_client_ip(request)
    )

    try:
        # 1. Validar Content-Type
        if request.content_type != "application/json":
            webhook_log.status = "error"
            webhook_log.error_message = f"Invalid content type: {request.content_type}"
            webhook_log.save()
            return JsonResponse(
                {"error": "Content-Type must be application/json"},
                status=400
            )

        # 2. Parse do payload
        try:
            payload = json.loads(request.body.decode('utf-8'))
            webhook_log.payload = payload
        except json.JSONDecodeError as e:
            webhook_log.status = "error"
            webhook_log.error_message = f"Invalid JSON: {str(e)}"
            webhook_log.save()
            return JsonResponse(
                {"error": "Invalid JSON payload"},
                status=400
            )

        # 3. Validar assinatura HMAC (se configurado)
        signature_header = request.headers.get("X-Signature-256", "")
        if hasattr(settings, "CVAT_WEBHOOK_SECRET") and settings.CVAT_WEBHOOK_SECRET:
            if not validate_webhook_signature(request.body, signature_header):
                webhook_log.status = "error"
                webhook_log.error_message = "Invalid HMAC signature"
                webhook_log.save()
                return JsonResponse(
                    {"error": "Invalid signature"},
                    status=403
                )

        # 4. Extrair tipo de evento
        event_type = payload.get("event", "unknown")
        webhook_log.event_type = event_type
        webhook_log.status = "processing"
        webhook_log.save()

        # 5. Processar evento
        if event_type in ["create:job", "update:job"]:
            result = process_job_event(payload, webhook_log)

            webhook_log.status = "success"
            webhook_log.processed_at = timezone.now()
            webhook_log.save()

            return JsonResponse({
                "status": "success",
                "message": f"Event {event_type} processed successfully",
                "task_id": result.get("task_id") if result else None
            }, status=200)

        elif event_type == "delete:job":
            result = process_job_delete(payload, webhook_log)

            webhook_log.status = "success"
            webhook_log.processed_at = timezone.now()
            webhook_log.save()

            return JsonResponse({
                "status": "success",
                "message": "Delete event processed successfully",
                "deleted": result.get("deleted", False)
            }, status=200)

        elif event_type in ["create:task", "update:task"]:
            result = process_task_event(payload, webhook_log)

            webhook_log.status = "success"
            webhook_log.processed_at = timezone.now()
            webhook_log.save()

            return JsonResponse({
                "status": "success",
                "message": f"Event {event_type} processed successfully",
                "task_id": result.get("task_id") if result else None
            }, status=200)

        elif event_type == "delete:task":
            result = process_task_delete(payload, webhook_log)

            webhook_log.status = "success"
            webhook_log.processed_at = timezone.now()
            webhook_log.save()

            return JsonResponse({
                "status": "success",
                "message": "Task delete event processed successfully",
                "deleted": result.get("deleted", False),
                "deleted_count": result.get("deleted_count", 0)
            }, status=200)

        else:
            webhook_log.status = "error"
            webhook_log.error_message = f"Unsupported event type: {event_type}"
            webhook_log.save()

            return JsonResponse({
                "error": f"Unsupported event type: {event_type}"
            }, status=400)

    except Exception as e:
        webhook_log.status = "error"
        webhook_log.error_message = str(e)
        webhook_log.processed_at = timezone.now()
        webhook_log.save()

        return JsonResponse({
            "error": "Internal server error",
            "message": str(e)
        }, status=500)


def validate_webhook_signature(payload_body, signature_header):
    """
    Valida a assinatura HMAC do webhook.

    Args:
        payload_body: Body da requisição em bytes
        signature_header: Header X-Signature-256 do CVAT

    Returns:
        bool: True se válido, False caso contrário
    """
    if not signature_header:
        return False

    # CVAT envia como "sha256=<hash>"
    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header.replace("sha256=", "")

    # Calcular HMAC
    secret = settings.CVAT_WEBHOOK_SECRET.encode('utf-8')
    calculated_signature = hmac.new(
        secret,
        payload_body,
        hashlib.sha256
    ).hexdigest()

    # Comparação segura contra timing attacks
    return hmac.compare_digest(calculated_signature, expected_signature)


def get_client_ip(request):
    """Obtém o IP real do cliente, considerando proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def map_cvat_state_to_status(stage, cvat_state):
    """
    Mapeia stage + state do CVAT para o status do sistema.

    Args:
        stage: Etapa do workflow (annotation, validation, acceptance)
        cvat_state: Estado do CVAT (new, in progress, completed, rejected)

    Returns:
        str: Status do sistema (pendente, em_andamento, conferindo, feito, revisado)
    """
    # Normalizar
    stage_lower = (stage or '').lower()
    state_lower = (cvat_state or '').lower()

    # Regra 1: acceptance + completed = feito
    if stage_lower == 'acceptance' and state_lower == 'completed':
        return 'feito'

    # Regra 2: qualquer stage + new = pendente
    if state_lower == 'new':
        return 'pendente'

    # Regra 3: qualquer stage + in progress = em_andamento
    if state_lower == 'in progress':
        return 'em_andamento'

    # Regra 4: completed (mas não acceptance) = conferindo
    if state_lower == 'completed':
        return 'conferindo'

    # Regra 5: rejected = pendente
    if state_lower == 'rejected':
        return 'pendente'

    # Default
    return 'pendente'


def fetch_project_name_from_cvat(project_id):
    """
    Busca o nome de um projeto no CVAT.

    Args:
        project_id: ID do projeto no CVAT

    Returns:
        str: Nome do projeto ou None se falhar
    """
    try:
        # Login
        cookies = login_to_cvat()
        if not cookies:
            return None

        # Buscar projeto
        url = f"{settings.CVAT_API_URL}/projects/{project_id}"
        response = requests.get(url, cookies=cookies, timeout=10)
        response.raise_for_status()

        project_data = response.json()
        return project_data.get('name')
    except Exception as e:
        print(f"Error fetching project {project_id}: {e}")
        return None


def process_job_event(payload, webhook_log):
    """
    Processa eventos de create/update de jobs do CVAT.

    Implementa lógica híbrida:
    - Sincroniza status do CVAT automaticamente
    - Preserva status se manual_override=True

    Args:
        payload: Dados do webhook
        webhook_log: Instância do WebhookLog

    Returns:
        dict: Resultado do processamento
    """
    try:
        # Extrair dados do job do payload
        job_data = payload.get("job", {})

        if not job_data:
            raise ValueError("Job data not found in payload")

        job_id = job_data.get("id")
        task_id = job_data.get("task_id")

        if not job_id:
            raise ValueError("Job ID not found in payload")

        # VALIDAÇÃO: Buscar informações completas da task do CVAT (OBRIGATÓRIO)
        if not task_id:
            raise ValueError(f"Task ID not found for job {job_id}")

        task_info = fetch_task_from_cvat(task_id)
        if not task_info:
            raise ValueError(f"Failed to fetch task data for task {task_id}")

        # Preparar dados - usar dados da API (não do payload)
        task_name = task_info.get('name')
        if not task_name:
            raise ValueError(f"Task name not found for task {task_id}")

        project_id = task_info.get('project_id')
        project_name = None

        # Se tem projeto, buscar o nome (OBRIGATÓRIO se project_id existir)
        if project_id:
            project_name = fetch_project_name_from_cvat(project_id)
            if not project_name:
                raise ValueError(f"Failed to fetch project name for project {project_id}")

        # Extrair assignee
        assignee = None
        if job_data.get("assignee"):
            if isinstance(job_data["assignee"], dict):
                assignee = job_data["assignee"].get("username")
            else:
                assignee = str(job_data["assignee"])

        # Gerar URL do CVAT
        cvat_url = f"https://cvat.perplan.work/tasks/{task_id}/jobs/{job_id}" if task_id and job_id else None

        # Mapear status do CVAT para status do sistema
        stage = job_data.get("stage")
        cvat_state = job_data.get("state")
        mapped_status = map_cvat_state_to_status(stage, cvat_state)

        # Verificar se task já existe
        try:
            existing_task = CVATTask.objects.get(cvat_job_id=job_id)

            # Preparar defaults para update
            defaults = {
                "cvat_task_id": task_id or 0,
                "task_name": task_name,
                "project_id": project_id,
                "project_name": project_name,
                "assignee": assignee,
                "cvat_status": job_data.get("status"),
                "stage": job_data.get("stage"),
                "cvat_state": cvat_state,
                "cvat_url": cvat_url,
                "cvat_data": payload,
                "last_synced_at": timezone.now()
            }

            # LÓGICA HÍBRIDA: Só atualizar status se não foi editado manualmente
            if not existing_task.manual_override:
                defaults["status"] = mapped_status

            # Atualizar task
            for field, value in defaults.items():
                setattr(existing_task, field, value)
            existing_task.save()

            task = existing_task
            created = False

        except CVATTask.DoesNotExist:
            # Task nova - criar com status mapeado
            task = CVATTask.objects.create(
                cvat_job_id=job_id,
                cvat_task_id=task_id or 0,
                task_name=task_name,
                project_id=project_id,
                project_name=project_name,
                assignee=assignee,
                status=mapped_status,
                cvat_status=job_data.get("status"),
                stage=job_data.get("stage"),
                cvat_state=cvat_state,
                cvat_url=cvat_url,
                cvat_data=payload,
                manual_override=False,
                last_synced_at=timezone.now()
            )
            created = True

        # Associar webhook log à task
        webhook_log.cvat_task = task
        webhook_log.save()

        return {
            "task_id": task.id,
            "created": created
        }

    except Exception as e:
        raise Exception(f"Error processing job event: {str(e)}")


def process_task_event(payload, webhook_log):
    """
    Processa eventos de create/update de tasks do CVAT.

    Args:
        payload: Dados do webhook
        webhook_log: Instância do WebhookLog

    Returns:
        dict: Resultado do processamento
    """
    try:
        # Extrair dados da task do payload
        task_data = payload.get("task", {})

        if not task_data:
            raise ValueError("Task data not found in payload")

        task_id = task_data.get("id")

        # FIX: Check for None explicitly (allow 0 as valid ID)
        if task_id is None:
            raise ValueError("Task ID not found in payload")

        # Buscar informações completas da task do CVAT
        task_info = fetch_task_from_cvat(task_id)

        if not task_info:
            # Se API falhar, usar dados do payload
            task_info = {
                'name': task_data.get('name', f'Task #{task_id}'),
                'project_id': task_data.get('project_id'),
                'assignee': task_data.get('assignee'),
                'status': task_data.get('status'),
                'state': task_data.get('state'),
            }

        # Buscar project_id e project_name (VALIDAÇÃO OBRIGATÓRIA se tiver projeto)
        project_id = task_info.get('project_id')
        project_name = None

        if project_id:
            project_name = fetch_project_name_from_cvat(project_id)
            if not project_name:
                raise ValueError(f"Failed to fetch project name for project {project_id} in task {task_id}")

        # Para tasks, buscar TODOS os jobs associados
        jobs_list = []

        # Tentar pegar jobs do payload
        jobs_from_payload = task_data.get('jobs', [])
        if isinstance(jobs_from_payload, list) and len(jobs_from_payload) > 0:
            jobs_list = jobs_from_payload
        # Se não tiver no payload, buscar da API
        elif task_info and task_info.get('jobs'):
            jobs_list = task_info.get('jobs', [])

        # Se ainda não temos jobs, ignorar silenciosamente (task pode estar sendo criada)
        if not jobs_list:
            webhook_log.status = 'success'
            webhook_log.error_message = f"Task {task_id} has no jobs yet - skipping"
            webhook_log.save()
            return {
                "task_id": None,
                "created": False,
                "message": "Task has no jobs - skipped"
            }

        # Processar APENAS o primeiro job (cada task tem 1 job principal)
        first_job = jobs_list[0]
        job_id = first_job.get('id')

        if job_id is None:
            raise ValueError(f"Job ID not found in task {task_id}")

        # Extrair assignee
        assignee = None
        if task_info.get('assignee'):
            if isinstance(task_info['assignee'], dict):
                assignee = task_info['assignee'].get('username')
            else:
                assignee = str(task_info['assignee'])

        # Gerar URL do CVAT
        cvat_url = f"https://cvat.perplan.work/tasks/{task_id}/jobs/{job_id}" if task_id and job_id else None

        # Mapear status do CVAT para status do sistema
        stage = task_info.get('stage')
        cvat_state = task_info.get('state')
        mapped_status = map_cvat_state_to_status(stage, cvat_state)

        # Verificar se task já existe
        try:
            existing_task = CVATTask.objects.get(cvat_job_id=job_id)

            # Preparar defaults para update
            defaults = {
                "cvat_task_id": task_id,
                "task_name": task_info.get('name', f'Task #{task_id}'),
                "project_id": task_info.get('project_id'),
                "project_name": project_name,
                "assignee": assignee,
                "cvat_status": task_info.get('status'),
                "stage": task_info.get('stage'),
                "cvat_state": cvat_state,
                "cvat_url": cvat_url,
                "cvat_data": payload,
                "last_synced_at": timezone.now()
            }

            # LÓGICA HÍBRIDA: Só atualizar status se não foi editado manualmente
            if not existing_task.manual_override:
                defaults["status"] = mapped_status

            # Atualizar task
            for field, value in defaults.items():
                setattr(existing_task, field, value)
            existing_task.save()

            task = existing_task
            created = False

        except CVATTask.DoesNotExist:
            # Task nova - criar com status mapeado
            task = CVATTask.objects.create(
                cvat_job_id=job_id,
                cvat_task_id=task_id,
                task_name=task_info.get('name', f'Task #{task_id}'),
                project_id=task_info.get('project_id'),
                project_name=project_name,
                assignee=assignee,
                status=mapped_status,
                cvat_status=task_info.get('status'),
                stage=task_info.get('stage'),
                cvat_state=cvat_state,
                cvat_url=cvat_url,
                cvat_data=payload,
                manual_override=False,
                last_synced_at=timezone.now()
            )
            created = True

        # Associar webhook log à task
        webhook_log.cvat_task = task
        webhook_log.save()

        return {
            "task_id": task.id,
            "created": created
        }

    except Exception as e:
        raise Exception(f"Error processing task event: {str(e)}")


def process_job_delete(payload, webhook_log):
    """
    Processa eventos de delete de jobs do CVAT.

    Args:
        payload: Dados do webhook
        webhook_log: Instância do WebhookLog

    Returns:
        dict: Resultado do processamento
    """
    try:
        # Extrair dados do job do payload
        job_data = payload.get("job", {})

        if not job_data:
            raise ValueError("Job data not found in payload")

        job_id = job_data.get("id")

        if not job_id:
            raise ValueError("Job ID not found in payload")

        # Buscar e deletar a task
        try:
            task = CVATTask.objects.get(cvat_job_id=job_id)
            webhook_log.cvat_task = task
            webhook_log.save()

            task.delete()

            return {
                "deleted": True,
                "job_id": job_id
            }

        except CVATTask.DoesNotExist:
            # Task já não existe no banco, registrar mas não é erro
            return {
                "deleted": False,
                "job_id": job_id,
                "message": "Task not found in database"
            }

    except Exception as e:
        raise Exception(f"Error processing job delete: {str(e)}")


def process_task_delete(payload, webhook_log):
    """
    Processa eventos de delete de tasks do CVAT.

    Args:
        payload: Dados do webhook
        webhook_log: Instância do WebhookLog

    Returns:
        dict: Resultado do processamento
    """
    try:
        # Extrair dados da task do payload
        task_data = payload.get("task", {})

        if not task_data:
            raise ValueError("Task data not found in payload")

        task_id = task_data.get("id")

        if not task_id:
            raise ValueError("Task ID not found in payload")

        # Buscar e deletar todas as tasks com esse cvat_task_id
        # (pode haver múltiplos jobs para a mesma task)
        deleted_count = 0
        tasks = CVATTask.objects.filter(cvat_task_id=task_id)

        for task in tasks:
            webhook_log.cvat_task = task
            webhook_log.save()
            task.delete()
            deleted_count += 1

        if deleted_count == 0:
            # Task não encontrada no banco
            return {
                "deleted": False,
                "task_id": task_id,
                "message": "Task not found in database"
            }

        return {
            "deleted": True,
            "task_id": task_id,
            "deleted_count": deleted_count
        }

    except Exception as e:
        raise Exception(f"Error processing task delete: {str(e)}")


# Cache de cookies de autenticação CVAT (para performance)
_cvat_auth_cookies = None


def fetch_task_from_cvat(task_id):
    """
    Busca informações completas de uma task do CVAT via API.

    Args:
        task_id: ID da task no CVAT

    Returns:
        dict: Informações da task ou None se falhar
    """
    global _cvat_auth_cookies

    try:
        # Se não tem cookies em cache, fazer login
        if not _cvat_auth_cookies:
            _cvat_auth_cookies = login_to_cvat()

        if not _cvat_auth_cookies:
            return None

        # Buscar task
        task_url = f"{settings.CVAT_API_URL}/tasks/{task_id}"
        response = requests.get(
            task_url,
            cookies=_cvat_auth_cookies,
            timeout=10
        )

        # Se falhou por autenticação, tentar login novamente
        if response.status_code == 401:
            _cvat_auth_cookies = login_to_cvat()
            if _cvat_auth_cookies:
                response = requests.get(
                    task_url,
                    cookies=_cvat_auth_cookies,
                    timeout=10
                )

        response.raise_for_status()
        task_data = response.json()

        # Extrair informações relevantes
        return {
            'id': task_data.get('id'),
            'name': task_data.get('name', 'Unknown'),
            'project_id': task_data.get('project_id'),
            'project': task_data.get('project'),  # Pode conter nome do projeto
            'assignee': task_data.get('assignee'),
            'status': task_data.get('status'),
            'state': task_data.get('state'),
        }

    except Exception as e:
        print(f"[ERROR] Failed to fetch task {task_id} from CVAT: {str(e)}")
        return None


def login_to_cvat():
    """
    Faz login no CVAT e retorna cookies de autenticação.

    Returns:
        dict: Cookies de sessão ou None se falhar
    """
    try:
        # Verificar se credenciais estão configuradas
        if not hasattr(settings, 'CVAT_USERNAME') or not hasattr(settings, 'CVAT_PASSWORD'):
            print("[ERROR] CVAT credentials not configured in settings.py")
            return None

        if settings.CVAT_USERNAME == "seu-usuario-aqui":
            print("[ERROR] Please configure CVAT_USERNAME and CVAT_PASSWORD in settings.py")
            return None

        # Fazer login
        login_url = f"{settings.CVAT_API_URL}/auth/login"
        response = requests.post(
            login_url,
            json={
                'username': settings.CVAT_USERNAME,
                'password': settings.CVAT_PASSWORD,
            },
            timeout=10
        )

        response.raise_for_status()
        return response.cookies.get_dict()

    except Exception as e:
        print(f"[ERROR] Failed to login to CVAT: {str(e)}")
        return None


# ============================================================================
# API ENDPOINTS PARA EDIÇÃO INLINE E DASHBOARD
# ============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def update_task_field(request):
    """
    API endpoint para atualizar um campo específico de uma task.
    Usado pela edição inline.
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        field = data.get('field')
        value = data.get('value')

        if not all([task_id, field]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        task = get_object_or_404(CVATTask, id=task_id)

        # Campos permitidos para edição
        allowed_fields = ['task_name', 'assignee', 'status', 'data_inicio', 'data_conclusao']

        if field not in allowed_fields:
            return JsonResponse({'error': f'Field {field} not allowed'}, status=400)

        # Se estiver editando status, marcar manual_override
        if field == 'status':
            if value not in dict(CVATTask.STATUS_CHOICES):
                return JsonResponse({'error': 'Invalid status value'}, status=400)
            task.manual_override = True

        # Atualizar campo
        setattr(task, field, value)
        task.save()

        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'field': field,
            'value': value
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_task_responsaveis(request):
    """
    API endpoint para atualizar os responsáveis de uma task (ManyToMany).
    """
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        user_ids = data.get('user_ids', [])

        if not task_id:
            return JsonResponse({'error': 'Missing task_id'}, status=400)

        task = get_object_or_404(CVATTask, id=task_id)

        # Atualizar responsáveis
        from django.contrib.auth.models import User
        users = User.objects.filter(id__in=user_ids)
        task.responsavel.set(users)
        task.save()

        return JsonResponse({
            'success': True,
            'task_id': task.id,
            'responsaveis': [
                {'id': u.id, 'username': u.username}
                for u in task.responsavel.all()
            ]
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
def dashboard_metrics(request):
    """
    API endpoint para retornar métricas do dashboard.
    """
    try:
        from datetime import datetime, timedelta
        from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField

        # Filtros de data
        quick_filter = request.GET.get('quick_filter', '')  # '7d', '30d', 'this_month', 'last_month'
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        # Determinar range de datas
        now = timezone.now()
        queryset = CVATTask.objects.all()

        if quick_filter == '7d':
            start = now - timedelta(days=7)
            queryset = queryset.filter(last_synced_at__gte=start)
        elif quick_filter == '30d':
            start = now - timedelta(days=30)
            queryset = queryset.filter(last_synced_at__gte=start)
        elif quick_filter == 'this_month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            queryset = queryset.filter(last_synced_at__gte=start)
        elif quick_filter == 'last_month':
            first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            first_last_month = (first_this_month - timedelta(days=1)).replace(day=1)
            queryset = queryset.filter(
                last_synced_at__gte=first_last_month,
                last_synced_at__lt=first_this_month
            )
        elif start_date and end_date:
            queryset = queryset.filter(
                last_synced_at__gte=start_date,
                last_synced_at__lte=end_date
            )

        # Métricas gerais
        total_tasks = queryset.count()
        total_concluidas = queryset.filter(status__in=['feito', 'revisado']).count()
        taxa_conclusao = (total_concluidas / total_tasks * 100) if total_tasks > 0 else 0

        # Tempo médio de conclusão (tasks com data_inicio e data_conclusao)
        tasks_with_dates = queryset.filter(
            data_inicio__isnull=False,
            data_conclusao__isnull=False
        )

        if tasks_with_dates.exists():
            tempo_medio_seconds = tasks_with_dates.aggregate(
                avg_time=Avg(
                    ExpressionWrapper(
                        F('data_conclusao') - F('data_inicio'),
                        output_field=DurationField()
                    )
                )
            )['avg_time']
            tempo_medio_dias = tempo_medio_seconds.days if tempo_medio_seconds else 0
        else:
            tempo_medio_dias = 0

        # Total de anotações
        total_anotacoes = queryset.aggregate(
            total=Sum('total_annotations')
        )['total'] or 0

        # Rankings
        # 1. Por tasks concluídas (usando assignee do CVAT)
        ranking_tasks = queryset.filter(
            status__in=['feito', 'revisado'],
            assignee__isnull=False
        ).values('assignee').annotate(
            tasks_completed=Count('id')
        ).order_by('-tasks_completed')[:10]

        # 2. Por anotações
        ranking_anotacoes = queryset.filter(
            assignee__isnull=False
        ).values('assignee').annotate(
            total_anotacoes=Sum('total_annotations')
        ).order_by('-total_anotacoes')[:10]

        # 3. Por produtividade (anotações / tasks)
        ranking_produtividade = []
        for item in ranking_anotacoes:
            username = item['assignee']
            user_tasks = queryset.filter(assignee=username)
            tasks_count = user_tasks.count()
            total_ann = item['total_anotacoes']
            produtividade = total_ann / tasks_count if tasks_count > 0 else 0

            ranking_produtividade.append({
                'username': username,
                'productivity': round(produtividade, 2),
                'tasks': tasks_count,
                'anotacoes': total_ann
            })

        ranking_produtividade = sorted(
            ranking_produtividade,
            key=lambda x: x['productivity'],
            reverse=True
        )[:10]

        return JsonResponse({
            'metrics': {
                'total_tasks': total_tasks,
                'total_concluidas': total_concluidas,
                'taxa_conclusao': round(taxa_conclusao, 1),
                'tempo_medio_dias': tempo_medio_dias,
                'total_anotacoes': total_anotacoes
            },
            'rankings': {
                'by_tasks': list(ranking_tasks),
                'by_anotacoes': list(ranking_anotacoes),
                'by_productivity': ranking_produtividade
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
