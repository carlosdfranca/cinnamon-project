# core/processing/dre_service.py
from __future__ import annotations

from typing import Dict, List, Tuple
from django.db.models import Sum
from df.models import BalanceteItem

# ============================
# Configuração padrão (igual à sua)
# ============================
CONTAS_DRE_PADRAO: List[str] = [
    "7.1.1.10.00.001-5", "7.1.1.10.00.016-1", "8.1.5.10.00.001-4", "8.1.9.99.00.001-3",
    "7.1.4.10.10.007-1", "7.1.9.99.00.016-0", "8.1.7.81.00.001-8", "8.1.7.81.00.004-9",
    "8.1.7.54.00.003-8", "8.1.7.54.00.008-3", "8.1.7.48.00.001-3", "8.1.7.54.00.005-2",
    "8.1.7.63.00.001-2", "8.1.7.63.00.002-9", "8.1.7.99.00.001-7"
]

ESTRUTURA_DRE_PADRAO: Dict[str, List[str]] = {
    "Direitos creditórios sem aquisição substancial de riscos e benefícios": [
        "Rendimentos de  direitos creditórios",
        "(-) Provisão para perdas por redução no valor de recuperação"
    ],
    "Rendas de aplicações interfinanceiras de liquidez": [
        "Letra Financeiras do Tesouro - LFT"
    ],
    "Outras receitas operacionais": [
        "Outras receitas operacionais"
    ],
    "Demais despesas": [
        "Taxa de administração", "Taxa de gestão", "Despesas bancárias",
        "Despesas com publicações", "Taxa de fiscalização CVM",
        "Serviços de auditoria", "Serviços de consultoria", "Outras despesas"
    ]
}


# ============================
# Helpers
# ============================
def _norm(s: str) -> str:
    """
    Normaliza string para comparação resiliente:
    - trata None como vazio
    - strip
    - lower()/casefold
    - comprime espaços internos
    """
    if s is None:
        return ""
    s = " ".join(str(s).strip().split())
    return s.casefold()


def _int_mil(v) -> int:
    """
    Divide por 1000 e arredonda pro inteiro mais próximo.
    Compatível com a tua regra:
      int(round(soma / 1000, 0))
    """
    try:
        return int(round((float(v) if v else 0.0) / 1000.0, 0))
    except Exception:
        return 0


# ============================
# Serviço principal
# ============================
def gerar_dados_dre(
    fundo_id: int,
    ano: int,
    contas_dre: List[str] | None = None,
    estrutura_dre: Dict[str, List[str]] | None = None,
) -> Tuple[Dict, int, int]:
    """
    Replica a lógica do teu util, mas usando agregação no banco e normalização robusta.

    Retorna:
      dict_tabela, resultado_exercicio, resultado_exercicio_anterior

    Formato:
      dict_tabela = {
          "Grupo X": {
              "Subgrupo Y": {"ATUAL": int, "ANTERIOR": int},
              ...
              "SOMA": int,
              "SOMA_ANTERIOR": int,
          },
          ...
      }
    """
    contas = contas_dre or CONTAS_DRE_PADRAO
    estrutura = estrutura_dre or ESTRUTURA_DRE_PADRAO

    if not contas:
        # nada a fazer
        return {}, 0, 0

    # 1) Consulta única agregada (ano atual e anterior) para as contas de interesse
    qs = (
        BalanceteItem.objects
        .filter(fundo_id=fundo_id, ano__in=[ano, ano - 1], conta_corrente__conta__in=contas)
        .values("ano", "conta_corrente__grupo_df")
        .annotate(total=Sum("saldo_final"))
    )

    # 2) Indexa soma por (norm(grupo_df), ano) -> valor
    #    Ex.: somas[("outras receitas operacionais", 2024)] = 12345.67
    somas: Dict[tuple[str, int], float] = {}
    for row in qs:
        g = _norm(row["conta_corrente__grupo_df"])
        a = int(row["ano"])
        somas[(g, a)] = float(row["total"] or 0.0) + somas.get((g, a), 0.0)

    dict_tabela: Dict[str, Dict] = {}
    resultado_exercicio = 0
    resultado_exercicio_anterior = 0

    # 3) Para cada grupo e sua lista de subgrupos (labels livres), montamos o bloco
    for grupo_label, subgrupos in estrutura.items():
        bloco: Dict[str, Dict[str, int] | int] = {}
        soma_atual_i = 0
        soma_anterior_i = 0

        for sub in subgrupos:
            key_norm = _norm(sub)
            atual = _int_mil(somas.get((key_norm, ano), 0.0))
            anterior = _int_mil(somas.get((key_norm, ano - 1), 0.0))
            bloco[sub] = {"ATUAL": atual, "ANTERIOR": anterior}
            soma_atual_i += atual
            soma_anterior_i += anterior

        bloco["SOMA"] = soma_atual_i
        bloco["SOMA_ANTERIOR"] = soma_anterior_i

        resultado_exercicio += soma_atual_i
        resultado_exercicio_anterior += soma_anterior_i

        dict_tabela[grupo_label] = bloco

    return dict_tabela, resultado_exercicio, resultado_exercicio_anterior
