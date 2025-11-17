"""
Template tags e filtros customizados para o app cvat_sync.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Permite acessar itens de um dicionário no template usando uma variável como chave.

    Uso: {{ dict|get_item:key_variable }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def divide(value, arg):
    """
    Divide um valor por outro.

    Uso: {{ value|divide:arg }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError):
        return 0


@register.filter
def multiply(value, arg):
    """
    Multiplica um valor por outro.

    Uso: {{ value|multiply:arg }}
    """
    try:
        return float(value) * float(arg)
    except ValueError:
        return 0


@register.filter
def get_status_color(status):
    """
    Retorna a classe de cor Tailwind para um status.

    Uso: {{ task.status|get_status_color }}
    """
    colors = {
        'pendente': 'gray',
        'em_andamento': 'orange',
        'conferindo': 'cyan',
        'feito': 'green',
        'revisado': 'green',
    }
    return colors.get(status, 'gray')


@register.filter
def get_status_icon(status):
    """
    Retorna o ícone FontAwesome para um status.

    Uso: {{ task.status|get_status_icon }}
    """
    icons = {
        'pendente': 'fa-circle',
        'em_andamento': 'fa-clock',
        'conferindo': 'fa-search',
        'feito': 'fa-check-circle',
        'revisado': 'fa-check-double',
    }
    return icons.get(status, 'fa-circle')


@register.simple_tag
def get_status_choices():
    """
    Retorna as escolhas de status do modelo CVATTask.

    Uso: {% get_status_choices as status_choices %}
    """
    from cvat_sync.models import CVATTask
    return CVATTask.STATUS_CHOICES


@register.filter
def status_display_name(status_key):
    """
    Retorna o nome de exibição de um status.

    Uso: {{ 'em_andamento'|status_display_name }}
    """
    from cvat_sync.models import CVATTask
    return dict(CVATTask.STATUS_CHOICES).get(status_key, status_key)


@register.filter
def get_status_display(status_key):
    """
    Retorna o nome de exibição de um status (alias para status_display_name).

    Uso: {{ status_filter|get_status_display }}
    """
    from cvat_sync.models import CVATTask
    return dict(CVATTask.STATUS_CHOICES).get(status_key, status_key)
