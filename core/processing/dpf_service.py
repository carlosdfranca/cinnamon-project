from __future__ import annotations
from typing import Dict, Tuple
from datetime import date
from django.db.models import Sum
from df.models import BalanceteItem, GrupoGrande

DIVIDIR_POR_MIL_PADRAO = True


def _int_mil(v, dividir_por_mil: bool) -> int:
    try:
        f = float(v) if v is not None else 0.0
        if dividir_por_mil:
            f = f / 1000.0
        return int(round(f, 0))
    except Exception:
        return 0


def gerar_dados_dpf(
    fundo_id: int,
    data_atual: date,
    data_anterior: date | None,
    dividir_por_mil: bool = DIVIDIR_POR_MIL_PADRAO,
    zerar_anterior: bool = False,
) -> Tuple[Dict, Dict[str, int]]:
    """
    Gera a DPF (Demonstração da Posição Financeira) a partir do mapeamento no banco.
    Compara duas datas específicas de balancete (data_atual e data_anterior).
    Se zerar_anterior=True, ignora completamente a data_anterior e retorna todos
    os valores 'ANTERIOR' como 0.
    """

    # 1) Consulta agregada — só tipos 1,2,3 (Ativo, Passivo, PL)
    qs = (
        BalanceteItem.objects
        .filter(
            fundo_id=fundo_id,
            data_referencia__in=[data_atual] if zerar_anterior else [data_atual, data_anterior],
            conta_corrente__grupo_pequeno__grupao__tipo__in=[1, 2, 3],
        )
        .values(
            "data_referencia",
            "conta_corrente__grupo_pequeno_id",
            "conta_corrente__grupo_pequeno__grupao_id",
            "conta_corrente__grupo_pequeno__grupao__tipo",
        )
        .annotate(total=Sum("saldo_final"))
    )

    # 2) Indexar: somas[(tipo, grupao_id, grupinho_id, data)] = valor
    somas = {}
    for row in qs:
        tipo = int(row["conta_corrente__grupo_pequeno__grupao__tipo"])
        ggrande = row["conta_corrente__grupo_pequeno__grupao_id"]
        gpequeno = row["conta_corrente__grupo_pequeno_id"]
        data_ref = row["data_referencia"]
        key = (tipo, ggrande, gpequeno, data_ref)
        somas[key] = float(row["total"] or 0.0) + somas.get(key, 0.0)

    # 3) Função para montar cada seção (ATIVO, PASSIVO, PL)
    def _montar_secao(tipo: int, label_total: str) -> Tuple[Dict[str, Dict], int, int]:
        secao: Dict[str, Dict] = {}
        total_atual = 0
        total_ant = 0

        grupoes = (
            GrupoGrande.objects
            .filter(tipo=tipo)
            .prefetch_related("grupinhos")
            .order_by("ordem", "nome")
        )

        for grupao in grupoes:
            bloco: Dict[str, Dict[str, int] | int] = {}
            soma_atual_i = 0
            soma_ant_i = 0

            for grupinho in sorted(grupao.grupinhos.all(), key=lambda g: g.nome):
                atual = _int_mil(
                    somas.get((tipo, grupao.id, grupinho.id, data_atual), 0.0),
                    dividir_por_mil,
                )
                anterior = 0 if zerar_anterior else _int_mil(
                    somas.get((tipo, grupao.id, grupinho.id, data_anterior), 0.0),
                    dividir_por_mil,
                )

                if atual == 0 and anterior == 0:
                    continue  # ignora subgrupo irrelevante

                bloco[grupinho.nome] = {"ATUAL": atual, "ANTERIOR": anterior}
                soma_atual_i += atual
                soma_ant_i += anterior

            if soma_atual_i != 0 or soma_ant_i != 0:
                bloco["SOMA"] = soma_atual_i
                bloco["SOMA_ANTERIOR"] = soma_ant_i
                secao[grupao.nome] = bloco

                total_atual += soma_atual_i
                total_ant += soma_ant_i

        # Linha total da seção
        secao[label_total] = {"ATUAL": total_atual, "ANTERIOR": 0 if zerar_anterior else total_ant}
        return secao, total_atual, 0 if zerar_anterior else total_ant

    # 4) Monta cada lado (Ativo, Passivo, PL)
    ativo_bloco, ativo_atual, ativo_ant = _montar_secao(1, "TOTAL_ATIVO")
    passivo_bloco, passivo_atual, passivo_ant = _montar_secao(2, "TOTAL_PASSIVO")
    pl_bloco, pl_atual, pl_ant = _montar_secao(3, "TOTAL_PL")

    dpf = {
        "ATIVO": ativo_bloco,
        "PASSIVO": passivo_bloco,
        "PL": pl_bloco,
    }

    # 5) Métricas de fechamento (sem %)
    metricas = {
        "DATA_ATUAL": str(data_atual),
        "DATA_ANTERIOR": "ZERADO" if zerar_anterior else str(data_anterior),
        "FECHAMENTO_ATUAL": ativo_atual - (passivo_atual + pl_atual),
        "FECHAMENTO_ANTERIOR": 0 if zerar_anterior else ativo_ant - (passivo_ant + pl_ant),
        "DIVIDIR_POR_MIL": dividir_por_mil,
    }

    return dpf, metricas
