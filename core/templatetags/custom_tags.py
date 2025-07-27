from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def formata_milhar(valor):
    try:
        valor = round(valor / 1000)
        if valor < 0:
            return f"({abs(valor):,})".replace(",", ".")
        return f"{valor:,}".replace(",", ".")
    except:
        return "0"