from decimal import Decimal
from df.models import MecItem
from django.db import models

def gerar_dados_dmpl(fundo_id: int, ano: int):
    qs_atual = MecItem.objects.filter(fundo_id=fundo_id, data_posicao__year=ano)
    qs_ant = MecItem.objects.filter(fundo_id=fundo_id, data_posicao__year=ano-1)

    # Primeira e última posição do ano atual
    primeiro = qs_atual.order_by("data_posicao").first()
    ultimo = qs_atual.order_by("data_posicao").last()

    # Primeira posição do ano anterior
    primeiro_ant = qs_ant.order_by("data_posicao").first()

    # ---- Quantidade de cotas movimentadas ----
    aplicacoes_qtd = Decimal("0")
    resgates_qtd = Decimal("0")

    for item in qs_atual:
        if item.cota and item.cota > 0:
            aplicacoes_qtd += (item.aplicacao or Decimal("0")) / item.cota
            resgates_qtd += (item.resgate or Decimal("0")) / item.cota
    
    soma_aplic = qs_atual.aggregate(models.Sum("aplicacao"))["aplicacao__sum"] or Decimal(0)
    soma_resg = qs_atual.aggregate(models.Sum("resgate"))["resgate__sum"] or Decimal(0)

    def _calc_valor(qtd, cota):
        return int(round((qtd * cota) / 1000, 0)) if qtd and cota else 0
    
    valor_ultimo = _calc_valor(float(ultimo.qtd_cotas), float(ultimo.cota)) if ultimo else 0
    valor_primeiro = _calc_valor(float(primeiro.qtd_cotas), float(primeiro.cota)) if primeiro else 0
    valor_primeiro_ant = _calc_valor(float(primeiro_ant.qtd_cotas), float(primeiro_ant.cota)) if primeiro_ant else 0

    aplicacoes_valor = int(float(soma_aplic) / 1000)
    resgates_valor = -int(float(soma_resg) / 1000)

    pl_antes_resultado_periodo = valor_primeiro + aplicacoes_valor + resgates_valor


    dados = {
        "qtd_cotas_inicio": round(float(primeiro.qtd_cotas), 6) if primeiro else 0,
        "qtd_cotas_fim": round(float(ultimo.qtd_cotas), 6) if ultimo else 0,
        "qtd_cotas_inicio_ant": round(float(primeiro_ant.qtd_cotas), 6) if primeiro_ant else 0,

        "cota_inicio": round(float(primeiro.cota), 6) if primeiro else 0,
        "cota_fim": round(float(ultimo.cota), 6) if ultimo else 0,
        "cota_inicio_ant": round(float(primeiro_ant.cota), 6) if primeiro_ant else 0,

        "aplicacoes_qtd": round(float(aplicacoes_qtd), 6),
        "resgates_qtd": round(float(resgates_qtd), 6),

        "aplicacoes_valor": int(soma_aplic / Decimal(1000)),
        "resgates_valor": int(soma_resg / Decimal(1000)),

        "valor_ultimo": valor_ultimo,
        "valor_primeiro": valor_primeiro,
        "valor_primeiro_ant": valor_primeiro_ant,

        "pl_antes_resultado_periodo": pl_antes_resultado_periodo      
    }

    return dados
