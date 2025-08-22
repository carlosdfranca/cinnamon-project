# core/processing/dpf_service.py
from __future__ import annotations

from typing import Dict, List, Tuple
from django.db.models import Sum
from df.models import BalanceteItem, MapeamentoContas

# ============================
# Configurações padrão
# ============================
CONTAS_DPF_PADRAO: List[str] = [
    "1.1.2.80.00.002-2",
    "1.2.1.10.99.000-1",
    "1.6.1.30.00.001-2",
    "1.6.1.30.00.002-9",
    "1.6.9.97.00.001-1",
    "1.9.9.10.00.001-9",
    "1.8.4.30.00.001-9",
    "4.9.9.92.00.001-4",
    "4.9.9.83.00.001-6",
    "4.9.9.83.00.004-7",
    "6.1.1.70.30.001-9",
    "6.1.1.80.00.001-7",
    "6.1.8.10.00.001-9",
    "6.1.8.10.00.003-3",
]

# Estrutura-padrão do DPF por TIPO (1=Ativo; 2=Passivo; 3=Patrimônio Líquido)
# Use rótulos que você quer ver na tabela. As strings devem combinar com MapeamentoContas.grupo_df (normalizado).
# Se algum grupo não existir no mapa/importação, ele aparece com zero.
ESTRUTURA_DPF_PADRAO: Dict[int, Dict[str, List[str]]] = {
    1: {  # ATIVO
        "Disponibilidades": [
            "Banco conta movimento",
        ],
        "Aplicações interfinanceiras de liquidez": [
            "Notas do tesouro nacional - NTN",
            "Letra Financeiras do Tesouro - LFT",
        ],
        "Cotas de fundos de investimentos": [
            "Santander FIC FI Select RF Referenciado DI",
        ],
        "Cotas de fundo de investimento": [
            "Petra Liquidez Fundo de Investimento Referenciado DI LP",
        ],
        "Direitos creditórios sem aquisição substancial de riscos e benefícios": [
            "Direitos creditórios a vencer",
            "Direitos creditório a vencidos",
            "(-) Provisão para perdas por redução no valor de recuperação",
        ],
        "Outros valores a receber": [
            "Outros valores a receber",
            "Recebiveis a liquidar",
        ],
    },
    2: {  # PASSIVO
        "Valores a pagar": [
            "Créditos a identificar",
            "Despesa de taxa de administração",
            "Despesa de taxa de gestão",
        ],
    },
    3: { # PATRIMONIO LÍQUIDO
        "Patrimônio Líquido": [
            "Patrimônio líquido",
        ],
    }
}

# Controle de escala (igual à DRE)
DIVIDIR_POR_MIL_PADRAO = True


# ============================
# Helpers compartilhados
# ============================
def _norm(s: str) -> str:
    if s is None:
        return ""
    s = " ".join(str(s).strip().split())
    return s.casefold()

def _int_mil(v, dividir_por_mil: bool) -> int:
    try:
        f = float(v) if v is not None else 0.0
        if dividir_por_mil:
            f = f / 1000.0
        return int(round(f, 0))
    except Exception:
        return 0


# ============================
# Serviço principal (DPF)
# ============================
def gerar_dados_dpf(
    fundo_id: int,
    ano: int,
    contas_dpf: List[str] | None = CONTAS_DPF_PADRAO,
    estrutura_por_tipo: Dict[int, Dict[str, List[str]]] | None = None,
    dividir_por_mil: bool = DIVIDIR_POR_MIL_PADRAO,
) -> Tuple[Dict, Dict[str, int]]:
    """
    Gera a DPF (Demonstração da Posição Financeira) para 'ano' e 'ano-1'.

    Retorna:
      dpf_tabela, metricas
    Onde:
      dpf_tabela = {
        "ATIVO": {
            "Ativo Circulante": { "SOMA": int, "SOMA_ANTERIOR": int, "<subgrupo>": {"ATUAL": int, "ANTERIOR": int}, ... },
            "Ativo Não Circulante": {...},
            "TOTAL_ATIVO": { "ATUAL": int, "ANTERIOR": int }
        },
        "PASSIVO": {
            ...
            "TOTAL_PASSIVO": { "ATUAL": int, "ANTERIOR": int }
        },
        "PL": {
            ...
            "TOTAL_PL": { "ATUAL": int, "ANTERIOR": int }
        }
      }

      metricas = {
        "ANO_ATUAL": ano,
        "ANO_ANTERIOR": ano-1,
        "FECHAMENTO_ATUAL": total_ativo_atual - (total_passivo_atual + total_pl_atual),
        "FECHAMENTO_ANTERIOR": total_ativo_ant - (total_passivo_ant + total_pl_ant),
      }
    """
    estrutura = estrutura_por_tipo or ESTRUTURA_DPF_PADRAO

    filtros_base = {
        "fundo_id": fundo_id,
        "ano__in": [ano, ano - 1],
    }
    if contas_dpf:
        filtros_base["conta_corrente__conta__in"] = contas_dpf

    # Consulta única: somar por (ano, tipo, grupo_df)
    qs = (
        BalanceteItem.objects
        .filter(**filtros_base)
        .values("ano", "conta_corrente__tipo", "conta_corrente__grupo_df")
        .annotate(total=Sum("saldo_final"))
    )

    # Índices para acesso rápido
    # somas[(tipo, norm(grupo_df), ano)] = float
    somas: Dict[tuple[int, str, int], float] = {}
    for row in qs:
        a = int(row["ano"])
        tipo = int(row["conta_corrente__tipo"] or 0)
        gnorm = _norm(row["conta_corrente__grupo_df"])
        somas[(tipo, gnorm, a)] = float(row["total"] or 0.0) + somas.get((tipo, gnorm, a), 0.0)

    def _montar_bloco(tipo: int, estrutura_tipo: Dict[str, List[str]]):
        """
        Monta o dicionário de um dos lados (ex.: ATIVO) com subtotais.
        """
        bloco: Dict[str, Dict] = {}
        total_atual = 0
        total_ant = 0

        for grupo_label, subgrupos in estrutura_tipo.items():
            soma_atual_i = 0
            soma_ant_i = 0
            det: Dict[str, Dict[str, int]] = {}

            for sub in subgrupos:
                k = _norm(sub)
                atual = _int_mil(somas.get((tipo, k, ano), 0.0), dividir_por_mil)
                anterior = _int_mil(somas.get((tipo, k, ano - 1), 0.0), dividir_por_mil)
                det[sub] = {"ATUAL": atual, "ANTERIOR": anterior}
                soma_atual_i += atual
                soma_ant_i += anterior

            det["SOMA"] = soma_atual_i
            det["SOMA_ANTERIOR"] = soma_ant_i
            bloco[grupo_label] = det

            total_atual += soma_atual_i
            total_ant += soma_ant_i

        return bloco, total_atual, total_ant

    # Monta ATIVO, PASSIVO, PL (por tipo)
    dpf: Dict[str, Dict] = {}

    ativo_struct = estrutura.get(1, {})
    passivo_struct = estrutura.get(2, {})
    pl_struct = estrutura.get(3, {})

    ativo_bloco, ativo_atual, ativo_ant = _montar_bloco(1, ativo_struct)
    passivo_bloco, passivo_atual, passivo_ant = _montar_bloco(2, passivo_struct)
    pl_bloco, pl_atual, pl_ant = _montar_bloco(3, pl_struct)

    # Totais por seção
    ativo_bloco["TOTAL_ATIVO"] = {"ATUAL": ativo_atual, "ANTERIOR": ativo_ant}
    passivo_bloco["TOTAL_PASSIVO"] = {"ATUAL": passivo_atual, "ANTERIOR": passivo_ant}
    pl_bloco["TOTAL_PL"] = {"ATUAL": pl_atual, "ANTERIOR": pl_ant}

    dpf["ATIVO"] = ativo_bloco
    dpf["PASSIVO"] = passivo_bloco
    dpf["PL"] = pl_bloco

    metricas = {
        "ANO_ATUAL": int(ano),
        "ANO_ANTERIOR": int(ano - 1),
        "FECHAMENTO_ATUAL": ativo_atual - (passivo_atual + pl_atual),
        "FECHAMENTO_ANTERIOR": ativo_ant - (passivo_ant + pl_ant),
        "DIVIDIR_POR_MIL": dividir_por_mil,
    }

    return dpf, metricas
