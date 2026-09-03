"""Формирование ответа инструмента: пресеты полей, сигнал усечения, предохранитель размера.

Зачем: ответы WB API рассчитаны на программу, а не на модель с ограниченным
контекстом. Замер на живом кабинете (август 2026):

    wb_tariffs_commission   881 000 токенов  (7 408 категорий целиком)
    wb_cards_list            86 000 токенов  (20 карточек; 78 % — фото и описания)
    wb_advert_list           32 000 токенов  (110 кампаний; 71 % — timestamps и ставки)

Потолок вывода одного вызова у клиента — 25 000 токенов (MAX_MCP_OUTPUT_TOKENS
в Claude Code), дальше ответ молча обрезается. Поэтому:

* compact-пресет отдаёт поля, по которым инструмент и вызывают, full — всё;
* если записей ровно столько, сколько просили, ответ дополняется предупреждением
  об усечении — иначе модель строит вывод по срезу, считая его полным;
* предохранитель по размеру не даёт ответу превысить потолок клиента молча.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Порог предохранителя в символах. ~2,2 символа на токен для кириллицы,
# ~4 для латиницы, поэтому 60 000 символов — это 15-27 тысяч токенов.
MAX_RESPONSE_CHARS = int(os.environ.get("WB_MAX_RESPONSE_CHARS", "60000"))

# инструмент → (путь до массива записей, поля compact-режима)
VIEWS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "wb_cards_list": (
        ("cards",),
        ("nmID", "imtID", "vendorCode", "subjectID", "subjectName", "brand",
         "title", "sizes", "dimensions", "needKiz", "updatedAt"),
    ),
    "wb_card_detail": (
        ("cards",),
        ("nmID", "imtID", "vendorCode", "subjectID", "subjectName", "brand",
         "title", "description", "characteristics", "sizes", "dimensions", "updatedAt"),
    ),
    "wb_advert_list": (
        ("adverts",),
        ("id", "status", "bid_type", "currency", "settings", "nm_settings", "restrictions"),
    ),
    "wb_finance_report": (
        (),
        ("rrdId", "rrDate", "saleDt", "docTypeName", "supplierOperName", "sellerOperName",
         "nmId", "vendorCode", "subjectName", "brandName", "techSize", "quantity",
         "retailPrice", "retailAmount", "retailPriceWithDisc", "salePercent",
         "commissionPercent", "ppvzSalesCommission", "ppvzForPay", "forPay",
         "deliveryRub", "deliveryAmount", "returnAmount", "penalty", "deduction",
         "paidStorage", "paidAcceptance", "acquiringFee", "rebillLogisticCost",
         "productDiscountForReport", "spp", "currency"),
    ),
    "wb_finance_report_detailed": (
        (),
        ("rrdId", "rrDate", "saleDt", "docTypeName", "supplierOperName", "nmId",
         "vendorCode", "quantity", "retailPrice", "retailAmount", "ppvzForPay",
         "forPay", "deliveryRub", "penalty", "deduction", "paidStorage", "currency"),
    ),
    "wb_documents_list": (
        ("data", "documents"),
        ("serviceName", "name", "documentType", "creationDate", "periodStart", "periodEnd", "extensions"),
    ),
    "wb_tariffs_commission": (
        ("report",),
        ("subjectID", "subjectName", "parentID", "parentName", "kgvpMarketplace",
         "kgvpSupplier", "kgvpPickup", "paidStorageKgvp"),
    ),
}

# У этих инструментов ответ настолько велик, что full-режим почти всегда
# упирается в потолок клиента: compact включён по умолчанию.
COMPACT_BY_DEFAULT = frozenset(VIEWS)

VIEW_PROP = {
    "type": "string",
    "enum": ["compact", "full"],
    "description": "compact (default) trims heavy fields; full returns the raw API response",
}


def _dig(data: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _put(data: Any, path: tuple[str, ...], value: Any) -> Any:
    if not path:
        return value
    if not isinstance(data, dict):
        return data
    head, rest = path[0], path[1:]
    if head not in data:
        return data
    data = dict(data)
    data[head] = _put(data[head], rest, value)
    return data


def apply_view(name: str, data: Any, view: str) -> tuple[Any, str | None]:
    """Оставить в записях только поля compact-пресета. Возвращает (данные, заметка)."""
    if view == "full" or name not in VIEWS:
        return data, None
    path, fields = VIEWS[name]
    items = _dig(data, path)
    if not isinstance(items, list) or not items:
        return data, None
    keep = set(fields)
    dropped: set[str] = set()
    slim = []
    for item in items:
        if not isinstance(item, dict):
            slim.append(item)
            continue
        dropped |= set(item) - keep
        slim.append({k: v for k, v in item.items() if k in keep})
    if not dropped:
        return data, None
    note = (f'Показаны основные поля ({len(items)} записей). '
            f'Скрыто: {", ".join(sorted(dropped)[:8])}'
            f'{"…" if len(dropped) > 8 else ""}. Полный ответ — с view="full".')
    return _put(data, path, slim), note


def truncation_note(name: str, arguments: dict, data: Any) -> str | None:
    """Предупредить, если записей ровно столько, сколько запрошено."""
    limit = arguments.get("limit")
    if not isinstance(limit, int) or limit <= 0:
        return None
    items = _dig(data, VIEWS[name][0]) if name in VIEWS else data
    if not isinstance(items, list):
        items = data if isinstance(data, list) else None
    if not isinstance(items, list) or len(items) < limit:
        return None
    return (f'Вернулось ровно {limit} записей — данные почти наверняка неполные. '
            f'Повторите с offset/cursor или сузьте фильтр, прежде чем делать выводы '
            f'по всему ассортименту.')


def guard_size(data: Any, max_chars: int = MAX_RESPONSE_CHARS) -> tuple[Any, str | None]:
    """Не дать ответу молча упереться в потолок вывода клиента.

    Самый длинный массив режется так, чтобы уложиться в лимит; сколько именно
    записей осталось и сколько было — сказано в заметке.
    """
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(payload) <= max_chars:
        return data, None

    target_path, target = _longest_list(data)
    if target is None or len(target) < 2:
        return data, (f"Ответ слишком велик ({len(payload)} символов) и будет обрезан клиентом. "
                      f"Сузьте период или фильтр.")

    per_item = max(1, len(payload) // len(target))
    keep = max(1, min(len(target) - 1, max_chars // per_item))
    note = (f"Показаны {keep} записей из {len(target)}: полный ответ ({len(payload)} символов) "
            f"не помещается в лимит вывода клиента. Сузьте фильтр или запросите остальное "
            f"постранично — выводы по этому срезу неполные.")
    return _put(data, target_path, target[:keep]), note


def _longest_list(data: Any, path: tuple[str, ...] = ()) -> tuple[tuple[str, ...], list | None]:
    best_path: tuple[str, ...] = ()
    best: list | None = None
    if isinstance(data, list):
        return path, data
    if isinstance(data, dict):
        for key, value in data.items():
            sub_path, sub = _longest_list(value, path + (key,))
            if sub is not None and (best is None or len(sub) > len(best)):
                best_path, best = sub_path, sub
    return best_path, best


def shape(name: str, arguments: dict, data: Any) -> tuple[Any, list[str]]:
    """Применить пресет, проверить усечение и размер. Возвращает (данные, заметки)."""
    notes: list[str] = []
    view = arguments.get("view") or ("compact" if name in COMPACT_BY_DEFAULT else "full")

    data, note = apply_view(name, data, view)
    if note:
        notes.append(note)

    note = truncation_note(name, arguments, data)
    if note:
        notes.append(note)

    data, note = guard_size(data)
    if note:
        notes.append(note)

    return data, notes
