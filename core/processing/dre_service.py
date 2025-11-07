from __future__ import annotations
from typing import Dict, Tuple
from datetime import date
from django.db.models import Sum
from df.models import BalanceteItem, GrupoGrande


def _int_mil(v) -> int:
    """Divide por 1000 e arredonda para inteiro mais próximo."""
    try:
        return int(round((float(v) if v else 0.0) / 1000.0, 0))
    except Exception:
        return 0


def gerar_dados_dre(fundo_id: int, data_atual: date, data_anterior: date) -> Tuple[Dict, int, int]:
    """
    Monta a DRE comparando duas datas específicas de balancete (saldo final).
    Considera apenas grupões de tipo=4 (Resultado).
    """

    qs = (
        BalanceteItem.objects
        .filter(
            fundo_id=fundo_id,
            data_referencia__in=[data_atual, data_anterior],
            conta_corrente__grupo_pequeno__grupao__tipo=4,
        )
        .values(
            "data_referencia",
            "conta_corrente__grupo_pequeno_id",
            "conta_corrente__grupo_pequeno__grupao_id",
        )
        .annotate(total=Sum("saldo_final"))
    )

    somas = {}
    for row in qs:
        gpequeno = row["conta_corrente__grupo_pequeno_id"]
        ggrande = row["conta_corrente__grupo_pequeno__grupao_id"]
        data_ref = row["data_referencia"]
        somas[(ggrande, gpequeno, data_ref)] = float(row["total"] or 0.0) + somas.get((ggrande, gpequeno, data_ref), 0.0)

    dict_tabela: Dict[str, Dict] = {}
    resultado_exercicio = resultado_exercicio_anterior = 0

    grupoes = GrupoGrande.objects.filter(tipo=4).prefetch_related("grupinhos").order_by("ordem", "nome")

    for grupao in grupoes:
        bloco: Dict[str, Dict[str, int]] = {}
        soma_atual_i = soma_anterior_i = 0

        for grupinho in sorted(grupao.grupinhos.all(), key=lambda g: g.nome):
            atual = _int_mil(somas.get((grupao.id, grupinho.id, data_atual), 0.0))
            anterior = _int_mil(somas.get((grupao.id, grupinho.id, data_anterior), 0.0))

            if atual == 0 and anterior == 0:
                continue

            bloco[grupinho.nome] = {"ATUAL": atual, "ANTERIOR": anterior}
            soma_atual_i += atual
            soma_anterior_i += anterior

        if soma_atual_i != 0 or soma_anterior_i != 0:
            bloco["SOMA"] = soma_atual_i
            bloco["SOMA_ANTERIOR"] = soma_anterior_i
            dict_tabela[grupao.nome] = bloco
            resultado_exercicio += soma_atual_i
            resultado_exercicio_anterior += soma_anterior_i

    return dict_tabela, resultado_exercicio, resultado_exercicio_anterior
