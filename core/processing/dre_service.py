from __future__ import annotations
from typing import Dict, Tuple
from django.db.models import Sum
from df.models import BalanceteItem, GrupoGrande

def _int_mil(v) -> int:
    """Divide por 1000 e arredonda para inteiro mais próximo."""
    try:
        return int(round((float(v) if v else 0.0) / 1000.0, 0))
    except Exception:
        return 0

def gerar_dados_dre(
    fundo_id: int,
    ano: int,
) -> Tuple[Dict, int, int]:
    """
    Monta a DRE a partir do mapeamento no banco.
    Considera apenas grupinhos de tipo=4 (Resultado).
    Ignora linhas zeradas em ambos os anos.
    """

    # 1) Consulta agregada — só grupinhos tipo=4 (Resultado)
    qs = (
        BalanceteItem.objects
        .filter(fundo_id=fundo_id, ano__in=[ano, ano - 1],
                conta_corrente__grupo_pequeno__tipo=4)
        .values(
            "ano",
            "conta_corrente__grupo_pequeno_id",
            "conta_corrente__grupo_pequeno__grupao_id",
        )
        .annotate(total=Sum("saldo_final"))
    )

    # 2) Indexa os valores
    somas = {}
    for row in qs:
        gpequeno = row["conta_corrente__grupo_pequeno_id"]
        ggrande = row["conta_corrente__grupo_pequeno__grupao_id"]
        a = int(row["ano"])
        somas[(ggrande, gpequeno, a)] = float(row["total"] or 0.0) + somas.get((ggrande, gpequeno, a), 0.0)

    dict_tabela: Dict[str, Dict] = {}
    resultado_exercicio = 0
    resultado_exercicio_anterior = 0

    # 3) Itera sobre os grupões e seus grupinhos de tipo=4
    grupoes = GrupoGrande.objects.prefetch_related("grupinhos").all().order_by("nome")

    for grupao in grupoes:
        grupinhos_resultado = [g for g in grupao.grupinhos.all() if g.tipo == 4]
        if not grupinhos_resultado:
            continue

        bloco: Dict[str, Dict[str, int] | int] = {}
        soma_atual_i = 0
        soma_anterior_i = 0

        for grupinho in sorted(grupinhos_resultado, key=lambda g: g.nome):
            atual = _int_mil(somas.get((grupao.id, grupinho.id, ano), 0.0))
            anterior = _int_mil(somas.get((grupao.id, grupinho.id, ano - 1), 0.0))

            if atual == 0 and anterior == 0:
                continue  # ignora subgrupo irrelevante

            bloco[grupinho.nome] = {"ATUAL": atual, "ANTERIOR": anterior}
            soma_atual_i += atual
            soma_anterior_i += anterior

        # só adiciona se houver algo relevante
        if soma_atual_i != 0 or soma_anterior_i != 0:
            bloco["SOMA"] = soma_atual_i
            bloco["SOMA_ANTERIOR"] = soma_anterior_i
            dict_tabela[grupao.nome] = bloco

            resultado_exercicio += soma_atual_i
            resultado_exercicio_anterior += soma_anterior_i

    return dict_tabela, resultado_exercicio, resultado_exercicio_anterior
