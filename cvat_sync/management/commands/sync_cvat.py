"""
Management command para sincronizar tasks do CVAT com o banco de dados local.
"""
import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from cvat_sync.models import CVATTask


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


class Command(BaseCommand):
    help = 'Sincroniza tasks do CVAT com o banco de dados local'

    def add_arguments(self, parser):
        parser.add_argument(
            '--project-id',
            type=int,
            help='Filtrar por ID do projeto específico'
        )
        parser.add_argument(
            '--task-id',
            type=int,
            help='Filtrar por ID da task específica'
        )
        parser.add_argument(
            '--assignee',
            type=str,
            help='Filtrar por username do responsável'
        )
        parser.add_argument(
            '--status',
            type=str,
            help='Filtrar por status do job'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forçar atualização de todas as tasks (ignora detecção de duplicatas)'
        )

    def handle(self, *args, **options):
        # Configurações do CVAT
        BASE_URL = "https://cvat.perplan.work/api"
        USERNAME = "Lucas.melo"
        PASSWORD = "Perci@25"
        TIMEOUT = 60

        self.stdout.write(self.style.NOTICE("="*80))
        self.stdout.write(self.style.NOTICE("SINCRONIZAÇÃO CVAT"))
        self.stdout.write(self.style.NOTICE("="*80))

        # Login
        self.stdout.write("Fazendo login no CVAT...")
        try:
            cookies = self._login(BASE_URL, USERNAME, PASSWORD, TIMEOUT)
            self.stdout.write(self.style.SUCCESS("[OK] Login realizado com sucesso"))
        except Exception as e:
            raise CommandError(f"Erro no login: {e}")

        # Preparar filtros
        filters = {
            'project_id': options.get('project_id'),
            'task_id': options.get('task_id'),
            'assignee': options.get('assignee'),
            'status': options.get('status'),
        }

        filters_str = ", ".join(
            f"{k}={v}" for k, v in filters.items() if v is not None
        )
        if filters_str:
            self.stdout.write(f"\nFiltros aplicados: {filters_str}")

        # Buscar jobs
        self.stdout.write("\nBuscando jobs do CVAT...")
        try:
            jobs = self._get_jobs(BASE_URL, cookies, TIMEOUT, **filters)
            self.stdout.write(self.style.SUCCESS(f"[OK] Encontrados {len(jobs)} jobs"))
        except Exception as e:
            raise CommandError(f"Erro ao buscar jobs: {e}")

        if not jobs:
            self.stdout.write(self.style.WARNING("Nenhum job encontrado com os filtros especificados."))
            return

        # Processar jobs
        self.stdout.write("\nProcessando jobs...")
        self.stdout.write("-"*80)

        stats = {
            'total': len(jobs),
            'new': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

        for i, job in enumerate(jobs, 1):
            job_id = job.get("id")
            task_id = job.get("task_id")

            self.stdout.write(
                f"[{i}/{stats['total']}] Processando Job #{job_id} "
                f"(Task #{task_id})...",
                ending=""
            )

            try:
                # Verificar se já existe
                exists = CVATTask.objects.filter(cvat_job_id=job_id).exists()

                if exists and not options.get('force'):
                    self.stdout.write(self.style.WARNING(" IGNORADO (já existe)"))
                    stats['skipped'] += 1
                    continue

                # ETAPA 1: Buscar dados da task (OBRIGATÓRIO)
                task_data = self._get_task_data(BASE_URL, cookies, task_id, TIMEOUT)
                if not task_data:
                    raise ValueError(f"Falha ao buscar dados da task {task_id}")

                # ETAPA 2: Buscar nome da task (OBRIGATÓRIO)
                task_name = self._get_task_name(BASE_URL, cookies, task_id, TIMEOUT)
                if not task_name or task_name == "Unknown":
                    raise ValueError(f"Falha ao buscar nome da task {task_id}")

                # ETAPA 3: Buscar anotações (OBRIGATÓRIO)
                annotations = self._get_job_annotations(BASE_URL, cookies, job_id, TIMEOUT)
                if annotations is None:
                    raise ValueError(f"Falha ao buscar anotações do job {job_id}")

                # ETAPA 4: Preparar dados do assignee
                assignee_data = job.get("assignee") or {}
                assignee_username = assignee_data.get("username") if assignee_data else None

                # ETAPA 5: Buscar project_id e project_name (se existir)
                project_id = task_data.get("project_id")
                project_name = None
                if project_id:
                    project_name = self._get_project_name(BASE_URL, cookies, project_id, TIMEOUT)
                    if not project_name or project_name == "Unknown":
                        # Se falhar, tentar novamente uma vez
                        import time
                        time.sleep(1)
                        project_name = self._get_project_name(BASE_URL, cookies, project_id, TIMEOUT)
                        if not project_name or project_name == "Unknown":
                            raise ValueError(f"Falha ao buscar nome do projeto {project_id} para task {task_id}")

                # ETAPA 6: Gerar URL do CVAT
                cvat_url = f"https://cvat.perplan.work/tasks/{task_id}/jobs/{job_id}"

                # ETAPA 7: Mapear status baseado em stage + state
                stage_value = job.get("stage")
                state_value = job.get("state")
                mapped_status = map_cvat_state_to_status(stage_value, state_value)

                with transaction.atomic():
                    # Verificar se task existe e se tem override manual
                    try:
                        existing_task = CVATTask.objects.get(cvat_job_id=job_id)
                        # Se tem override manual, não sobrescrever status
                        if existing_task.manual_override:
                            mapped_status = existing_task.status
                    except CVATTask.DoesNotExist:
                        pass  # Task nova, usar mapped_status

                    task_obj, created = CVATTask.objects.update_or_create(
                        cvat_job_id=job_id,
                        defaults={
                            'cvat_task_id': task_id,
                            'project_id': project_id,
                            'project_name': project_name,
                            'task_name': task_name,
                            'assignee': assignee_username,
                            'status': mapped_status,
                            'cvat_status': job.get("status"),
                            'stage': stage_value,
                            'cvat_state': state_value,
                            'manual_annotations': annotations["total_manual"],
                            'interpolated_annotations': annotations["total_interpolated"],
                            'total_annotations': annotations["total"],
                            'cvat_url': cvat_url,
                            'cvat_data': job,
                        }
                    )

                if created:
                    self.stdout.write(self.style.SUCCESS(" CRIADO"))
                    stats['new'] += 1
                else:
                    self.stdout.write(self.style.SUCCESS(" ATUALIZADO"))
                    stats['updated'] += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f" ERRO: {e}"))
                stats['errors'] += 1
                continue

        # Exibir estatísticas finais
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.NOTICE("ESTATISTICAS DA SINCRONIZACAO"))
        self.stdout.write("="*80)
        self.stdout.write(f"Total de jobs processados: {stats['total']}")
        self.stdout.write(self.style.SUCCESS(f"[OK] Novos: {stats['new']}"))
        self.stdout.write(self.style.SUCCESS(f"[OK] Atualizados: {stats['updated']}"))
        self.stdout.write(self.style.WARNING(f"[SKIP] Ignorados: {stats['skipped']}"))
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f"[ERROR] Erros: {stats['errors']}"))
        self.stdout.write("="*80)

        # Exibir resumo do banco
        total_db = CVATTask.objects.count()
        self.stdout.write(f"\nTotal de tasks no banco de dados: {total_db}")
        self.stdout.write(self.style.SUCCESS("\n[OK] Sincronizacao concluida!"))

    def _login(self, base_url, username, password, timeout):
        """Realiza login no CVAT e retorna os cookies."""
        url = f"{base_url}/auth/login"
        response = requests.post(
            url,
            json={"username": username, "password": password},
            timeout=timeout
        )
        response.raise_for_status()
        return response.cookies

    def _get_jobs(self, base_url, cookies, timeout, **filters):
        """Busca todos os jobs do CVAT com paginação."""
        url = f"{base_url}/jobs"
        params = {k: v for k, v in filters.items() if v is not None}

        all_jobs = []
        page = 1

        while True:
            params["page"] = page
            response = requests.get(url, params=params, cookies=cookies, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                break

            all_jobs.extend(results)

            if not data.get("next"):
                break
            page += 1

        return all_jobs

    def _get_task_name(self, base_url, cookies, task_id, timeout):
        """Busca o nome da task."""
        url = f"{base_url}/tasks/{task_id}"
        try:
            response = requests.get(url, cookies=cookies, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("name", "Unknown")
        except Exception:
            return "Unknown"

    def _get_task_data(self, base_url, cookies, task_id, timeout):
        """Busca dados completos da task."""
        url = f"{base_url}/tasks/{task_id}"
        try:
            response = requests.get(url, cookies=cookies, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except Exception:
            return {}

    def _get_project_name(self, base_url, cookies, project_id, timeout):
        """Busca o nome do projeto."""
        url = f"{base_url}/projects/{project_id}"
        try:
            response = requests.get(url, cookies=cookies, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("name", "Unknown")
        except Exception:
            return "Unknown"

    def _get_job_annotations(self, base_url, cookies, job_id, timeout):
        """Busca as anotações de um job."""
        url = f"{base_url}/jobs/{job_id}/annotations"
        response = requests.get(url, cookies=cookies, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        shapes = data.get("shapes", [])
        tracks = data.get("tracks", [])

        direct_shapes = len(shapes)
        manually_in_tracks = 0
        interpolated_in_tracks = 0

        for track in tracks:
            for shape in track.get("shapes", []):
                if shape.get("outside", False):
                    continue

                if shape.get("keyframe", False):
                    manually_in_tracks += 1
                else:
                    interpolated_in_tracks += 1

        total_manual = direct_shapes + manually_in_tracks
        total_interpolated = interpolated_in_tracks
        total_annotations = total_manual + total_interpolated

        return {
            "direct_shapes": direct_shapes,
            "manually_in_tracks": manually_in_tracks,
            "interpolated_in_tracks": interpolated_in_tracks,
            "total_manual": total_manual,
            "total_interpolated": total_interpolated,
            "total": total_annotations
        }
