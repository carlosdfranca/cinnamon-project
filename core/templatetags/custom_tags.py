from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def formata_milhar(valor):
    try:
        if valor < 0:
            return f"({abs(valor):,})".replace(".", "X").replace(",", ".").replace("X", ",")
        elif valor > 0:
            return f"{valor:,}".replace(".", "X").replace(",", ".").replace("X", ",")
        else:
            return "0"
    except:
        return "-"
    

@register.filter
def get_item(dictionary, key):
    """Permite acessar dicionários no template: {{ dict|get_item:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def percentual(atual, anterior):
    """
    Calcula variação percentual entre dois valores numéricos.
    Exemplo: 120 e 100 → 20.0
    """
    try:
        atual = float(atual or 0)
        anterior = float(anterior or 0)
        if anterior == 0:
            return "-"
        return round(((atual - anterior) / anterior) * 100, 2)
    except Exception:
        return "-"
