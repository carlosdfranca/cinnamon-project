from datetime import date
from decimal import Decimal
from df.models import MecItem
from django.db import models


def gerar_dados_dmpl(fundo_id: int, data_atual: date, data_anterior: date):
    """
    Gera os dados da DMPL (Demonstração das Mutações do Patrimônio Líquido)
    comparando duas datas específicas (data_atual e data_anterior).

    A lógica é a mesma do modelo original, mas agora usamos datas exatas
    em vez de anos fechados.
    """

    # --- Filtragem dinâmica ---
    qs_atual = MecItem.objects.filter(fundo_id=fundo_id, data_posicao__lte=data_atual)
    qs_ant = MecItem.objects.filter(fundo_id=fundo_id, data_posicao__lte=data_anterior)

    # Posição mais recente até cada data
    primeiro_atual = qs_atual.order_by("data_posicao").first()
    ultimo_atual = qs_atual.order_by("-data_posicao").first()
    ultimo_ant = qs_ant.order_by("-data_posicao").first()

    # ---- Quantidade de cotas movimentadas ----
    aplicacoes_qtd = Decimal("0")
    resgates_qtd = Decimal("0")
    aplicacoes_qtd_ant = Decimal("0")
    resgates_qtd_ant = Decimal("0")

    for item in qs_atual:
        if item.cota and item.cota > 0:
            aplicacoes_qtd += (item.aplicacao or Decimal("0")) / item.cota
            resgates_qtd += (item.resgate or Decimal("0")) / item.cota

    for item in qs_ant:
        if item.cota and item.cota > 0:
            aplicacoes_qtd_ant += (item.aplicacao or Decimal("0")) / item.cota
            resgates_qtd_ant += (item.resgate or Decimal("0")) / item.cota

    # ---- Somas agregadas ----
    soma_aplic = qs_atual.aggregate(models.Sum("aplicacao"))["aplicacao__sum"] or Decimal(0)
    soma_resg = qs_atual.aggregate(models.Sum("resgate"))["resgate__sum"] or Decimal(0)
    soma_aplic_ant = qs_ant.aggregate(models.Sum("aplicacao"))["aplicacao__sum"] or Decimal(0)
    soma_resg_ant = qs_ant.aggregate(models.Sum("resgate"))["resgate__sum"] or Decimal(0)

    # ---- Função auxiliar ----
    def _calc_valor(qtd, cota):
        return int(round((qtd * cota) / 1000, 0)) if qtd and cota else 0

    # ---- Cálculos principais ----
    valor_ultimo = _calc_valor(float(ultimo_atual.qtd_cotas), float(ultimo_atual.cota)) if ultimo_atual else 0
    valor_primeiro = _calc_valor(float(primeiro_atual.qtd_cotas), float(primeiro_atual.cota)) if primeiro_atual else 0
    valor_ultimo_ant = _calc_valor(float(ultimo_ant.qtd_cotas), float(ultimo_ant.cota)) if ultimo_ant else 0

    aplicacoes_valor = int(float(soma_aplic) / 1000)
    resgates_valor = -int(float(soma_resg) / 1000)

    # PL antes do resultado (saldo do início + apl - resg)
    pl_antes_resultado_periodo = valor_primeiro + aplicacoes_valor + resgates_valor

    # ---- Montagem do dicionário final ----
    dados = {
        # Quantidades e cotas
        "qtd_cotas_inicio": round(float(primeiro_atual.qtd_cotas), 6) if primeiro_atual else 0,
        "qtd_cotas_fim": round(float(ultimo_atual.qtd_cotas), 6) if ultimo_atual else 0,
        "qtd_cotas_inicio_ant": round(float(ultimo_ant.qtd_cotas), 6) if ultimo_ant else 0,

        "cota_inicio": round(float(primeiro_atual.cota), 6) if primeiro_atual else 0,
        "cota_fim": round(float(ultimo_atual.cota), 6) if ultimo_atual else 0,
        "cota_inicio_ant": round(float(ultimo_ant.cota), 6) if ultimo_ant else 0,

        # Movimentações em quantidade
        "aplicacoes_qtd": round(float(aplicacoes_qtd), 6),
        "resgates_qtd": round(float(resgates_qtd), 6),
        "aplicacoes_qtd_ant": round(float(aplicacoes_qtd_ant), 6),
        "resgates_qtd_ant": round(float(resgates_qtd_ant), 6),

        # Movimentações em valor (milhares)
        "aplicacoes_valor": int(soma_aplic / Decimal(1000)),
        "resgates_valor": int(soma_resg / Decimal(1000)),
        "aplicacoes_valor_ant": int(soma_aplic_ant / Decimal(1000)),
        "resgates_valor_ant": int(soma_resg_ant / Decimal(1000)),

        # Valores consolidados
        "valor_ultimo": valor_ultimo,
        "valor_primeiro": valor_primeiro,
        "valor_ultimo_ant": valor_ultimo_ant,

        # PL ajustado
        "pl_antes_resultado_periodo": pl_antes_resultado_periodo,
    }

    return dados
