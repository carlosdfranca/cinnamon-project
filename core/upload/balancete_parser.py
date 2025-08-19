# core/upload/balancete_parser.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
import pandas as pd
import io
import unicodedata

REQUIRED_CANONICAL_COLS = ("CONTA", "SALDO ATUAL", "SALDO ANTERIOR")


@dataclass(frozen=True)
class BalanceteRowDTO:
    conta: str
    saldo_atual: Optional[float]
    saldo_anterior: Optional[float]
    raw: Dict  # linha original (debug/erros)


class BalanceteSchemaError(Exception):
    def __init__(self, missing_columns: List[str]):
        self.missing_columns = missing_columns
        super().__init__(f"Colunas ausentes: {', '.join(missing_columns)}")


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


def _build_renames(columns: List[str]) -> Dict[str, str]:
    """
    Mapeia colunas da planilha para os canônicos:
    - CONTA ↔ {CONTA, COD CONTA, CODIGO, C CONTA}
    - SALDO ATUAL ↔ {SALDO, SALDO ATUAL, ATUAL}
    - SALDO ANTERIOR ↔ {SALDO ANTERIOR, ANTERIOR, SALDO PREVIO}
    """
    aliases = {
        "CONTA": {"CONTA", "COD CONTA", "CODIGO", "COD", "CODIGO CONTA", "C CONTA", "ID CONTA"},
        "SALDO ATUAL": {"SALDO", "SALDO ATUAL", "ATUAL", "VALOR ATUAL"},
        "SALDO ANTERIOR": {"SALDO ANTERIOR", "ANTERIOR", "VALOR ANTERIOR", "SALDO PREVIO"},
    }
    norm_to_original = {_normalize(c): c for c in columns}
    renames: Dict[str, str] = {}

    for canonical, options in aliases.items():
        found = None
        for opt in options:
            key = _normalize(opt)
            # tenta normalizado exato
            if key in norm_to_original:
                found = norm_to_original[key]
                break
        # fallback: se já existir a coluna canônica literal
        if not found and canonical in columns:
            found = canonical
        if found:
            renames[found] = canonical
    return renames


def _to_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        # strings com milhar/ponto e vírgula
        if isinstance(val, str):
            v = val.strip().replace(".", "").replace(",", ".")
            return float(v)
        return float(val)
    except Exception:
        return None


def parse_excel(file_obj) -> List[BalanceteRowDTO]:
    """
    Lê XLSX ou CSV e retorna linhas canônicas (sem tocar no banco).
    Valida a presença das colunas obrigatórias.
    """
    # buffer pra permitir repetidas leituras seguras
    name = getattr(file_obj, "name", "") or ""
    content = file_obj.read()
    file_obj.seek(0)

    df: pd.DataFrame
    if name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=object, encoding="utf-8", sep=None, engine="python")
    else:
        # padrão: Excel
        df = pd.read_excel(io.BytesIO(content), dtype=object)

    if df.empty:
        raise BalanceteSchemaError(list(REQUIRED_CANONICAL_COLS))

    renames = _build_renames(list(df.columns))
    df = df.rename(columns=renames)

    missing = [c for c in REQUIRED_CANONICAL_COLS if c not in df.columns]
    if missing:
        raise BalanceteSchemaError(missing)

    rows: List[BalanceteRowDTO] = []
    for _, row in df.iterrows():
        conta = str(row.get("CONTA") or "").strip()
        if not conta:
            # ignora linhas sem conta
            continue
        saldo_atual = _to_float(row.get("SALDO ATUAL"))
        saldo_anterior = _to_float(row.get("SALDO ANTERIOR"))
        rows.append(
            BalanceteRowDTO(
                conta=conta,
                saldo_atual=saldo_atual,
                saldo_anterior=saldo_anterior,
                raw=dict(row),
            )
        )
    return rows
