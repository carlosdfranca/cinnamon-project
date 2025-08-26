# core/upload/balancete_parser.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
import pandas as pd
import io
import unicodedata

REQUIRED_CANONICAL_COLS = ("CONTA", "SALDOATUAL", "SALDOANTERIOR")


@dataclass(frozen=True)
class BalanceteRowDTO:
    conta: str
    saldo_atual: Optional[float]
    saldo_anterior: Optional[float]
    raw: Dict  # linha original (debug/erros)


# =========================
# Erros de esquema
# =========================
class BalanceteSchemaError(Exception):
    def __init__(self, missing_columns: List[str], *, debug_info: Optional[str] = None):
        self.missing_columns = missing_columns
        self.debug_info = debug_info
        msg = f"Colunas ausentes: {', '.join(missing_columns)}"
        if debug_info:
            msg += f" | Debug: {debug_info}"
        super().__init__(msg)


# =========================
# DTO de saída do parser
# =========================
@dataclass
class BalanceteRowDTO:
    conta: str
    saldo_atual: Optional[float]
    saldo_anterior: Optional[float]
    raw: Dict


# =========================
# Colunas canônicas exigidas
# =========================
# Mantemos as labels canônicas ESTÁVEIS e sem acento/espacos extra.
CONTA = "CONTA"
SALDO_ATUAL = "SALDOATUAL"
SALDO_ANTERIOR = "SALDOANTERIOR"

REQUIRED_CANONICAL_COLS = (CONTA, SALDO_ATUAL, SALDO_ANTERIOR)


# =========================
# Normalização
# =========================
def _normalize(s: str) -> str:
    """
    Normaliza para comparação de nomes de coluna:
    - remove acentos
    - upper
    - troca separadores por espaço
    - comprime múltiplos espaços
    """
    s = str(s or "").strip()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = s.replace("_", " ").replace("-", " ").replace("/", " ")
    s = " ".join(s.split()).upper()
    return s


# =========================
# Aliases/renomeações
# =========================
def _build_renames(columns: List[str]) -> Dict[str, str]:
    """
    Constrói um mapeamento de colunas encontradas -> nomes canônicos.
    Opera sempre em cima de versões normalizadas para robustez.
    """
    # Dicionário de opções por canônico:
    aliases: Dict[str, List[str]] = {
        CONTA: [
            "CONTA", "COD CONTA", "CODIGO", "COD", "CODIGO CONTA", "C CONTA", "ID CONTA", "CODIGO DA CONTA",
        ],
        SALDO_ATUAL: [
            "SALDOATUAL", "SALDO ATUAL", "ATUAL", "VALOR ATUAL", "SALDO", "SALDO FINAL", "SALDO DEBITO CREDITO",
        ],
        SALDO_ANTERIOR: [
            # certo
            "SALDOANTERIOR", "SALDO ANTERIOR", "VALOR ANTERIOR",
            # variações comuns
            "ANTERIOR", "SALDO PREVIO", "SALDO PREV",
            # ERRO DE DIGITAÇÃO COMUM (sem R)
            "SALDOANTEIOR",
        ],
    }

    # Índice: normalizado da coluna original -> nome original
    norm_to_original: Dict[str, str] = {_normalize(c): c for c in columns}

    renames: Dict[str, str] = {}

    # Para cada canônico, tente encontrar alguma das variantes nas colunas originais
    for canonical, options in aliases.items():
        found_original = None

        # 1) se a canônica literal (normalizada) já existir como coluna
        if _normalize(canonical) in norm_to_original:
            found_original = norm_to_original[_normalize(canonical)]
        else:
            # 2) procurar por qualquer alias
            for opt in options:
                key = _normalize(opt)
                if key in norm_to_original:
                    found_original = norm_to_original[key]
                    break

        if found_original:
            renames[found_original] = canonical

    return renames


def _to_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        if isinstance(val, str):
            v = val.strip()
            if v == "":
                return None
            # normaliza string PT-BR: milhar . e decimal ,
            v = v.replace(".", "").replace(",", ".")
            return float(v)
        return float(val)
    except Exception:
        return None


# =========================
# Parser principal
# =========================
def parse_excel(file_obj) -> List[BalanceteRowDTO]:
    """
    Lê XLSX ou CSV e retorna linhas canônicas (sem tocar no banco).
    Valida a presença das colunas obrigatórias.
    """
    # Carrega conteúdo para buffer seguro
    name = getattr(file_obj, "name", "") or ""
    content = file_obj.read()
    file_obj.seek(0)

    # Carrega DataFrame
    if name.lower().endswith(".csv"):
        try:
            # Tenta abrir em UTF-8
            df = pd.read_csv(io.BytesIO(content), dtype=object, encoding="utf-8", sep=None, engine="python")
        except UnicodeDecodeError:
            # Fallback para Latin1 (ISO-8859-1)
            df = pd.read_csv(io.BytesIO(content), dtype=object, encoding="latin1", sep=None, engine="python")
    else:
        df = pd.read_excel(io.BytesIO(content), dtype=object)


    if df.empty:
        raise BalanceteSchemaError(list(REQUIRED_CANONICAL_COLS), debug_info="DataFrame vazio")

    # Renomeia colunas conforme aliases/normalização
    original_cols = list(df.columns)
    renames = _build_renames(original_cols)
    df = df.rename(columns=renames)

    # Diagnóstico: quais canônicas faltaram?
    missing = [c for c in REQUIRED_CANONICAL_COLS if c not in df.columns]
    if missing:
        debug = (
            f"originais={original_cols} | renames={renames} | "
            f"presentes={list(df.columns)} | required={list(REQUIRED_CANONICAL_COLS)}"
        )
        raise BalanceteSchemaError(missing, debug_info=debug)

    # Monta DTOs
    rows: List[BalanceteRowDTO] = []
    for _, row in df.iterrows():
        conta = str(row.get(CONTA) or "").strip()
        if not conta:
            # ignora linhas sem conta
            continue
        saldo_atual = _to_float(row.get(SALDO_ATUAL))
        saldo_anterior = _to_float(row.get(SALDO_ANTERIOR))
        rows.append(
            BalanceteRowDTO(
                conta=conta,
                saldo_atual=saldo_atual,
                saldo_anterior=saldo_anterior,
                raw=dict(row),
            )
        )
    return rows
