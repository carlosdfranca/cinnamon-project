# core/processing/import_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Iterable, Optional
from decimal import Decimal

from django.db import transaction

from df.models import BalanceteItem, MapeamentoContas


@dataclass(frozen=True)
class ImportErrorItem:
    row_index: int
    reason: str
    raw: dict


@dataclass(frozen=True)
class ImportReport:
    imported: int
    updated: int
    ignored: int
    errors: List[ImportErrorItem]


def _to_decimal(v: Optional[float]) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


@transaction.atomic
def import_balancete(*, fundo_id: int, ano: int, rows: List) -> ImportReport:
    """
    Importa linhas canônicas (BalanceteRowDTO) para BalanceteItem:
    - mapeia contas via MapeamentoContas.conta
    - escreve ano atual e ano anterior (se tiver valor)
    - idempotente (update_or_create)
    """
    if not rows:
        return ImportReport(imported=0, updated=0, ignored=0, errors=[])

    # cache do mapeamento por conta (evita N+1)
    contas = {r.conta for r in rows if getattr(r, "conta", None)}
    mapa_by_conta: Dict[str, MapeamentoContas] = {
        m.conta: m for m in MapeamentoContas.objects.filter(conta__in=list(contas))
    }

    imported = updated = ignored = 0
    errors: List[ImportErrorItem] = []

    for idx, r in enumerate(rows):
        conta = r.conta
        if not conta:
            ignored += 1
            continue

        conta_map = mapa_by_conta.get(conta)
        if conta_map is None:
            ignored += 1
            continue

        has_any = (r.saldo_atual is not None) or (r.saldo_anterior is not None)
        if not has_any:
            ignored += 1
            continue

        # ano atual
        if r.saldo_atual is not None:
            defaults = {"saldo_final": _to_decimal(r.saldo_atual)}
            _, created = BalanceteItem.objects.update_or_create(
                fundo_id=fundo_id,
                ano=ano,
                conta_corrente_id=conta_map.id,
                defaults=defaults,
            )
            if created:
                imported += 1
            else:
                updated += 1

        # ano anterior
        if r.saldo_anterior is not None:
            defaults = {"saldo_final": _to_decimal(r.saldo_anterior)}
            _, created = BalanceteItem.objects.update_or_create(
                fundo_id=fundo_id,
                ano=ano - 1,
                conta_corrente_id=conta_map.id,
                defaults=defaults,
            )
            if created:
                imported += 1
            else:
                updated += 1

    return ImportReport(imported=imported, updated=updated, ignored=ignored, errors=errors)
