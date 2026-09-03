"""Профили инструментов: сколько из 202 ручек видит клиент.

Claude Code грузит схемы по требованию (tool search), и там профили не нужны.
А Cursor, Cline, Continue и Claude Desktop забирают tools/list целиком — там
весь каталог оплачивается в каждом запросе. Переменная WB_TOOLSETS оставляет
только те профили, которыми пользуются:

    WB_TOOLSETS=pricing,ads      # цены и реклама, около 40 инструментов
    WB_TOOLSETS=                 # (по умолчанию) все

Профили нарезаны по рабочим задачам, а не по разделам документации WB: аудит
акций требует одновременно акций, цен и карантина, поэтому они в одном профиле.

Профиль core включён всегда: список магазинов, диагностика, деградации и данные
о токене нужны ровно тогда, когда что-то сломалось, — выключать их нельзя.
"""

from __future__ import annotations

import os
import re

CORE = "core"

# порядок важен: первое совпадение выигрывает
RULES: tuple[tuple[str, str], ...] = (
    (CORE,        r"^wb_(list_shops|diagnostics|degradations|token_info|api_news|seller_info|seller_rating)$"),
    ("pricing",   r"^wb_(prices|promotion|promotions|tariffs)"),
    ("ads",       r"^wb_(advert|search_report|search_texts)"),
    ("catalog",   r"^wb_(cards|card|barcodes|media|subject|subjects|directory|tag|tags|brands|categories|banned)"),
    ("orders",    r"^wb_(orders|order|supply|supplies|dbs|cc|passes|pass|warehouse|warehouses|stocks|fbw|acceptance)"),
    ("analytics", r"^wb_(analytics|nm_report|stats|search_table|search_product|jam)"),
    ("feedback",  r"^wb_(feedback|feedbacks|question|questions|returns|return|goods_return|chat|buyer|new_feedbacks)"),
    ("finance",   r"^wb_(finance|documents|document|deductions|paid_storage|users)"),
)

ALL_PROFILES: tuple[str, ...] = tuple(dict.fromkeys(name for name, _ in RULES))

DESCRIPTIONS = {
    CORE:        "магазины, диагностика, токен",
    "pricing":   "цены, акции, карантин, тарифы и комиссии",
    "ads":       "рекламные кампании, ставки, кластеры, поисковые отчёты",
    "catalog":   "карточки, характеристики, медиа, ярлыки, блокировки",
    "orders":    "заказы FBS/DBS, самовывоз, поставки, склады, остатки",
    "analytics": "воронки продаж, остатки, оборачиваемость, Джем-аналитика",
    "feedback":  "отзывы, вопросы, возвраты, чаты с покупателями",
    "finance":   "финансовые отчёты, баланс, документы, удержания",
}


def profile_of(name: str) -> str:
    for profile, pattern in RULES:
        if re.match(pattern, name):
            return profile
    return CORE  # неизвестное имя лучше показать, чем спрятать


def enabled_profiles() -> set[str] | None:
    """Профили из WB_TOOLSETS. None — ограничение не задано, доступно всё."""
    raw = (os.environ.get("WB_TOOLSETS") or "").strip()
    if not raw:
        return None
    picked = {p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()}
    picked = {p for p in picked if p in ALL_PROFILES}
    return ({CORE} | picked) if picked else None


def is_enabled(name: str) -> bool:
    enabled = enabled_profiles()
    return enabled is None or profile_of(name) in enabled


def disabled_profiles() -> list[str]:
    enabled = enabled_profiles()
    if enabled is None:
        return []
    return [p for p in ALL_PROFILES if p not in enabled]


def availability_note() -> str:
    """Строка для описания wb_list_shops: что именно выключено и как включить.

    Без неё модель, не найдя инструмента, отвечает «такой возможности нет» —
    хотя возможность есть, её просто отключили в конфиге.
    """
    off = disabled_profiles()
    if not off:
        return ""
    listed = ", ".join(f"{p} ({DESCRIPTIONS[p]})" for p in off)
    return (f" Отключены профили инструментов: {listed}. "
            f"Это ограничение конфигурации (WB_TOOLSETS), а не отсутствие возможности.")


def unavailable_message(name: str) -> str:
    profile = profile_of(name)
    return (f"Инструмент {name} отключён профилем: он входит в '{profile}' "
            f"({DESCRIPTIONS.get(profile, '')}), а в WB_TOOLSETS этого профиля нет. "
            f"Добавьте '{profile}' в WB_TOOLSETS и перезапустите сервер.")
