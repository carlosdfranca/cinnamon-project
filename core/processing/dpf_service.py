from __future__ import annotations
from typing import Dict, Tuple
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
    ano: int,
    dividir_por_mil: bool = DIVIDIR_POR_MIL_PADRAO,
) -> Tuple[Dict, Dict[str, int]]:
    """
    Gera a DPF (Demonstração da Posição Financeira) a partir do mapeamento no banco.
    Considera apenas grupinhos com tipo 1=Ativo, 2=Passivo, 3=PL.
    Ignora linhas zeradas em ambos os anos.
    """

    # 1) Consulta agregada só dos tipos 1,2,3
    qs = (
        BalanceteItem.objects
        .filter(fundo_id=fundo_id, ano__in=[ano, ano - 1],
                conta_corrente__grupo_pequeno__tipo__in=[1,2,3])
        .values(
            "ano",
            "conta_corrente__grupo_pequeno_id",
            "conta_corrente__grupo_pequeno__grupao_id",
            "conta_corrente__grupo_pequeno__tipo",
        )
        .annotate(total=Sum("saldo_final"))
    )

    # 2) Indexa: somas[(tipo, grupao_id, grupinho_id, ano)] = valor
    somas = {}
    for row in qs:
        tipo = int(row["conta_corrente__grupo_pequeno__tipo"])
        ggrande = row["conta_corrente__grupo_pequeno__grupao_id"]
        gpequeno = row["conta_corrente__grupo_pequeno_id"]
        a = int(row["ano"])
        key = (tipo, ggrande, gpequeno, a)
        somas[key] = float(row["total"] or 0.0) + somas.get(key, 0.0)

    # 3) Função para montar cada seção (ATIVO, PASSIVO, PL)
    def _montar_secao(tipo: int, label_total: str) -> Tuple[Dict[str, Dict], int, int]:
        secao: Dict[str, Dict] = {}
        total_atual = 0
        total_ant = 0

        grupoes = GrupoGrande.objects.prefetch_related("grupinhos").all().order_by("nome")
        for grupao in grupoes:
            grupinhos_tipo = [g for g in grupao.grupinhos.all() if g.tipo == tipo]
            if not grupinhos_tipo:
                continue

            bloco: Dict[str, Dict[str, int] | int] = {}
            soma_atual_i = 0
            soma_ant_i = 0

            for grupinho in sorted(grupinhos_tipo, key=lambda g: g.nome):
                atual = _int_mil(somas.get((tipo, grupao.id, grupinho.id, ano), 0.0), dividir_por_mil)
                anterior = _int_mil(somas.get((tipo, grupao.id, grupinho.id, ano - 1), 0.0), dividir_por_mil)

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

        secao[label_total] = {"ATUAL": total_atual, "ANTERIOR": total_ant}
        return secao, total_atual, total_ant

    # 4) Monta cada lado na ordem desejada
    ativo_bloco, ativo_atual, ativo_ant = _montar_secao(1, "TOTAL_ATIVO")
    passivo_bloco, passivo_atual, passivo_ant = _montar_secao(2, "TOTAL_PASSIVO")
    pl_bloco, pl_atual, pl_ant = _montar_secao(3, "TOTAL_PL")

    dpf = {
        "ATIVO": ativo_bloco,
        "PASSIVO": passivo_bloco,
        "PL": pl_bloco,
    }

    metricas = {
        "ANO_ATUAL": ano,
        "ANO_ANTERIOR": ano - 1,
        "FECHAMENTO_ATUAL": ativo_atual - (passivo_atual + pl_atual),
        "FECHAMENTO_ANTERIOR": ativo_ant - (passivo_ant + pl_ant),
        "DIVIDIR_POR_MIL": dividir_por_mil,
    }

    return dpf, metricas
