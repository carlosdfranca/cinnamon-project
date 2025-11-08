from datetime import date
from decimal import Decimal
from df.models import MecItem
from django.db import models


def gerar_dados_dmpl(fundo_id: int, data_atual: date, data_anterior: date):
    """
    Gera a DMPL comparando duas datas específicas (data_anterior → data_atual).
    Corrigido para refletir movimentações apenas dentro do intervalo de período.
    """

    # --- Consulta do período atual ---
    qs_periodo = MecItem.objects.filter(
        fundo_id=fundo_id,
        data_posicao__gt=data_anterior,
        data_posicao__lte=data_atual,
    )

    # --- Consultas para posições de início/fim ---
    primeiro_atual = (
        MecItem.objects.filter(fundo_id=fundo_id, data_posicao__lte=data_anterior)
        .order_by("-data_posicao")
        .first()
    )
    ultimo_atual = (
        MecItem.objects.filter(fundo_id=fundo_id, data_posicao__lte=data_atual)
        .order_by("-data_posicao")
        .first()
    )
    primeiro_ant = (
        MecItem.objects.filter(fundo_id=fundo_id, data_posicao__lte=data_anterior)
        .order_by("data_posicao")
        .first()
    )

    # ---- Quantidade de cotas movimentadas (no período) ----
    aplicacoes_qtd = Decimal("0")
    resgates_qtd = Decimal("0")

    for item in qs_periodo:
        if item.cota and item.cota > 0:
            aplicacoes_qtd += (item.aplicacao or Decimal("0")) / item.cota
            resgates_qtd += (item.resgate or Decimal("0")) / item.cota

    # ---- Somas agregadas ----
    soma_aplic = qs_periodo.aggregate(models.Sum("aplicacao"))["aplicacao__sum"] or Decimal(0)
    soma_resg = qs_periodo.aggregate(models.Sum("resgate"))["resgate__sum"] or Decimal(0)

    def _calc_valor(qtd, cota):
        return int(round((qtd * cota) / 1000, 0)) if qtd and cota else 0

    # ---- Cálculos principais ----
    valor_ultimo = _calc_valor(float(ultimo_atual.qtd_cotas), float(ultimo_atual.cota)) if ultimo_atual else 0
    valor_primeiro = _calc_valor(float(primeiro_atual.qtd_cotas), float(primeiro_atual.cota)) if primeiro_atual else 0
    valor_primeiro_ant = _calc_valor(float(primeiro_ant.qtd_cotas), float(primeiro_ant.cota)) if primeiro_ant else 0

    aplicacoes_valor = int(float(soma_aplic) / 1000)
    resgates_valor = -int(float(soma_resg) / 1000)

    # PL antes do resultado (início + apl - resg)
    pl_antes_resultado_periodo = valor_primeiro + aplicacoes_valor + resgates_valor

    # ---- Montagem final ----
    dados = {
        # Quantidades e cotas
        "qtd_cotas_inicio": round(float(primeiro_atual.qtd_cotas), 6) if primeiro_atual else 0,
        "qtd_cotas_fim": round(float(ultimo_atual.qtd_cotas), 6) if ultimo_atual else 0,
        "qtd_cotas_inicio_ant": round(float(primeiro_ant.qtd_cotas), 6) if primeiro_ant else 0,

        "cota_inicio": round(float(primeiro_atual.cota), 6) if primeiro_atual else 0,
        "cota_fim": round(float(ultimo_atual.cota), 6) if ultimo_atual else 0,
        "cota_inicio_ant": round(float(primeiro_ant.cota), 6) if primeiro_ant else 0,

        # Movimentações no período
        "aplicacoes_qtd": round(float(aplicacoes_qtd), 6),
        "resgates_qtd": round(float(resgates_qtd), 6),

        # Valores em milhares
        "aplicacoes_valor": int(soma_aplic / Decimal(1000)),
        "resgates_valor": int(soma_resg / Decimal(1000)),

        # Valores consolidados
        "valor_ultimo": valor_ultimo,
        "valor_primeiro": valor_primeiro,
        "valor_primeiro_ant": valor_primeiro_ant,

        "pl_antes_resultado_periodo": pl_antes_resultado_periodo,
    }

    return dados
