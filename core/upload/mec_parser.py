# core/upload/mec_parser.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict
import pandas as pd
import io
import unicodedata
import datetime

# =========================
# DTO de saída
# =========================
@dataclass
class MecRowDTO:
    data_posicao: datetime.date
    aplicacao: Optional[float]
    resgate: Optional[float]
    estorno: Optional[float]
    pl: Optional[float]
    qtd_cotas: Optional[float]
    cota: Optional[float]
    raw: Dict  # linha original (debug/erros)


# =========================
# Erros de esquema
# =========================
class MecSchemaError(Exception):
    def __init__(self, missing_columns: List[str], *, debug_info: Optional[str] = None):
        self.missing_columns = missing_columns
        self.debug_info = debug_info
        msg = f"Colunas ausentes: {', '.join(missing_columns)}"
        if debug_info:
            msg += f" | Debug: {debug_info}"
        super().__init__(msg)


# =========================
# Colunas canônicas
# =========================
DATAPOSICAO = "DATAPOSICAO"
VALORAPLICACAO = "VALORAPLICACAO"
VALORRESGATE = "VALORRESGATE"
VALORTOTALESTORNO = "VALORTOTALESTORNO"
VALORPATRIMONIO = "VALORPATRIMONIO"
QUANTIDADECOTAS = "QUANTIDADECOTAS"
VALORCOTA = "VALORCOTA"

REQUIRED_CANONICAL_COLS = (
    DATAPOSICAO,
    VALORAPLICACAO,
    VALORRESGATE,
    VALORTOTALESTORNO,
    VALORPATRIMONIO,
    QUANTIDADECOTAS,
    VALORCOTA,
)


# =========================
# Helpers
# =========================
def _normalize(s: str) -> str:
    s = str(s or "").strip()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = s.replace("_", " ").replace("-", " ").replace("/", " ")
    s = " ".join(s.split()).upper()
    return s

def _build_renames(columns: List[str]) -> Dict[str, str]:
    aliases: Dict[str, List[str]] = {
        DATAPOSICAO: ["DATA POSICAO", "DATA", "DT POSICAO"],
        VALORAPLICACAO: ["VALOR APLICACAO", "APLICACAO", "VL APLICACAO"],
        VALORRESGATE: ["VALOR RESGATE", "RESGATE", "VL RESGATE"],
        VALORTOTALESTORNO: ["VALOR TOTAL ESTORNO", "ESTORNO", "VL ESTORNO"],
        VALORPATRIMONIO: ["VALOR PATRIMONIO", "PATRIMONIO LIQ", "PL"],
        QUANTIDADECOTAS: ["QUANTIDADE COTAS", "QTD COTAS"],
        VALORCOTA: ["VALOR COTA", "COTA"],
    }

    norm_to_original = {_normalize(c): c for c in columns}
    renames: Dict[str, str] = {}

    for canonical, options in aliases.items():
        found = None
        if _normalize(canonical) in norm_to_original:
            found = norm_to_original[_normalize(canonical)]
        else:
            for opt in options:
                if _normalize(opt) in norm_to_original:
                    found = norm_to_original[_normalize(opt)]
                    break
        if found:
            renames[found] = canonical
    return renames

def _to_float(val) -> Optional[float]:
    try:
        if pd.isna(val):
            return None
        if isinstance(val, str):
            v = val.strip()
            if v == "":
                return None
            v = v.replace(".", "").replace(",", ".")
            return float(v)
        return float(val)
    except Exception:
        return None


# =========================
# Parser principal
# =========================
def parse_excel_mec(file_obj) -> List[MecRowDTO]:
    name = getattr(file_obj, "name", "") or ""
    content = file_obj.read()
    file_obj.seek(0)

    if name.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=object, encoding="utf-8", sep=None, engine="python")
    else:
        df = pd.read_excel(io.BytesIO(content), dtype=object)

    if df.empty:
        raise MecSchemaError(list(REQUIRED_CANONICAL_COLS), debug_info="DataFrame vazio")

    original_cols = list(df.columns)
    renames = _build_renames(original_cols)
    df = df.rename(columns=renames)

    missing = [c for c in REQUIRED_CANONICAL_COLS if c not in df.columns]
    if missing:
        debug = (
            f"originais={original_cols} | renames={renames} | "
            f"presentes={list(df.columns)} | required={list(REQUIRED_CANONICAL_COLS)}"
        )
        raise MecSchemaError(missing, debug_info=debug)

    rows: List[MecRowDTO] = []
    for _, row in df.iterrows():
        try:
            data_raw = row.get(DATAPOSICAO)
            if pd.isna(data_raw):
                continue
            if isinstance(data_raw, str):
                data_posicao = pd.to_datetime(data_raw, dayfirst=True).date()
            else:
                data_posicao = pd.to_datetime(data_raw).date()

            rows.append(
                MecRowDTO(
                    data_posicao=data_posicao,
                    aplicacao=_to_float(row.get(VALORAPLICACAO)),
                    resgate=_to_float(row.get(VALORRESGATE)),
                    estorno=_to_float(row.get(VALORTOTALESTORNO)),
                    pl=_to_float(row.get(VALORPATRIMONIO)),
                    qtd_cotas=_to_float(row.get(QUANTIDADECOTAS)),
                    cota=_to_float(row.get(VALORCOTA)),
                    raw=dict(row),
                )
            )
        except Exception as e:
            # Se uma linha falhar, apenas pula (ou você pode acumular em errors)
            continue

    return rows
