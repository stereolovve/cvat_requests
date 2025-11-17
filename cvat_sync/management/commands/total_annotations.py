"""
Django management command para consultar total de anotações
Uso: python manage.py total_annotations [--detailed]
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, Avg
from cvat_sync.models import CVATTask


class Command(BaseCommand):
    help = 'Exibe o total de anotacoes do CVAT'

    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Exibir estatisticas detalhadas',
        )
        parser.add_argument(
            '--by-status',
            action='store_true',
            help='Agrupar por status',
        )
        parser.add_argument(
            '--by-project',
            action='store_true',
            help='Agrupar por projeto',
        )
        parser.add_argument(
            '--by-assignee',
            action='store_true',
            help='Agrupar por responsavel',
        )

    def handle(self, *args, **options):
        # Total simples
        total = CVATTask.objects.aggregate(
            total=Sum('total_annotations')
        )['total'] or 0

        self.stdout.write(self.style.SUCCESS(f'\nTOTAL DE ANOTACOES: {total:,}'))

        # Estatísticas detalhadas
        if options['detailed']:
            stats = CVATTask.objects.aggregate(
                total_tasks=Count('id'),
                total_anotacoes=Sum('total_annotations'),
                media=Avg('total_annotations'),
            )

            self.stdout.write('\n' + '=' * 50)
            self.stdout.write('ESTATISTICAS DETALHADAS')
            self.stdout.write('=' * 50)
            self.stdout.write(f"Total de Tasks: {stats['total_tasks']}")
            self.stdout.write(f"Total de Anotacoes: {stats['total_anotacoes']:,}")
            self.stdout.write(f"Media por Task: {stats['media']:.2f}")

        # Agrupar por status
        if options['by_status']:
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write('ANOTACOES POR STATUS')
            self.stdout.write('=' * 50)

            por_status = CVATTask.objects.values('status').annotate(
                total=Sum('total_annotations'),
                tasks=Count('id')
            ).order_by('-total')

            for item in por_status:
                status_display = dict(CVATTask.STATUS_CHOICES).get(
                    item['status'], item['status']
                )
                self.stdout.write(
                    f"{status_display}: {item['total']:,} "
                    f"({item['tasks']} tasks)"
                )

        # Agrupar por projeto
        if options['by_project']:
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write('TOP 10 PROJETOS')
            self.stdout.write('=' * 50)

            por_projeto = CVATTask.objects.values('project_name').annotate(
                total=Sum('total_annotations'),
                tasks=Count('id')
            ).order_by('-total')[:10]

            for idx, item in enumerate(por_projeto, 1):
                projeto = item['project_name'] or '(Sem projeto)'
                self.stdout.write(
                    f"{idx:2d}. {projeto[:40]}: {item['total']:,} "
                    f"({item['tasks']} tasks)"
                )

        # Agrupar por responsável
        if options['by_assignee']:
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write('ANOTACOES POR RESPONSAVEL')
            self.stdout.write('=' * 50)

            por_assignee = CVATTask.objects.values('assignee').annotate(
                total=Sum('total_annotations'),
                tasks=Count('id')
            ).order_by('-total')

            for item in por_assignee:
                assignee = item['assignee'] or '(Nao atribuido)'
                self.stdout.write(
                    f"{assignee}: {item['total']:,} "
                    f"({item['tasks']} tasks)"
                )

        self.stdout.write('')  # Linha em branco no final
