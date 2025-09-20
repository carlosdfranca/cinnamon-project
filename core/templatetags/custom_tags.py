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