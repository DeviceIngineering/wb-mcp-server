"""Wildberries MCP Server — инструменты для управления бизнесом на WB.

Разделы: Магазины, Товары, Цены, Заказы, Финансы, Реклама, Аналитика,
         Отзывы, Вопросы, Возвраты, Тарифы, Обращения.
Поддержка нескольких магазинов через параметр shop_id: он передаётся явно,
а при единственном магазине подставляется сервером и в схемы не попадает.

В описаниях помечены только инструменты P0 — те, где ошибка означает прямые
финансовые потери (блокировки, убыточные цены и реклама). Остальные градации
(P1-P3) убраны из описаний: они стоили токенов контекста, не влияя на выбор.

v2.2.0 — диспетчеризация инструментов через словари NO_CLIENT_DISPATCH /
         CLIENT_DISPATCH вместо if/elif цепочки + 39 новых инструментов.

v2.3.0 — оптимизация контекста: компактный JSON в ответах, сжатые описания
         инструментов, shop_id скрывается при единственном магазине
         (определения: 27 460 → 17 709 токенов).

v2.3.1 — default в JSON-схемах limit приведён к фактическому дефолту
         handler'ов, добавлена сверка тестом.

v2.4.0 — формирование ответа (wb_mcp/shaping.py): пресеты view=compact|full,
         сигнал усечения, предохранитель размера, фильтр справочника комиссий.
         Корпус живых ответов: 770 506 → 74 947 токенов.

v2.5.0 — профили инструментов (wb_mcp/toolsets.py): WB_TOOLSETS оставляет
         нужные разделы каталога; core (магазины, диагностика, деградации,
         токен) включён всегда. 202 инструмента = 18 011 токенов, pricing+ads
         = 4 925.
"""

import json
import os
import asyncio
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from wb_mcp import shaping, toolsets
from wb_mcp.client import WBClient

# ─── Инициализация ────────────────────────────────────────

app = Server("wb-mcp-server", version="2.6.0")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

# Пул клиентов: {shop_id: WBClient}
_pool: dict[str, WBClient] = {}


def _get_client(shop_id: str) -> WBClient:
    if shop_id in _pool:
        return _pool[shop_id]

    from wb_mcp.settings import get_shop_keys
    keys = get_shop_keys(DATA_DIR, shop_id)
    api_token = keys.get("wb_api_token", "")
    if not api_token:
        raise ValueError(f"Магазин '{shop_id}': не задан WB_API_TOKEN")
    client = WBClient(api_token)
    _pool[shop_id] = client
    return client


# Публичный доступ к пулу клиентов (для app.py / диагностики)
def get_client_for_shop(shop_id: str) -> WBClient:
    return _get_client(shop_id)


async def reset_shop(shop_id: str):
    """Закрыть и удалить клиент конкретного магазина."""
    if shop_id in _pool:
        await _pool[shop_id].close()
        del _pool[shop_id]


async def reset_all_clients():
    """Закрыть всех клиентов."""
    for shop_id in list(_pool.keys()):
        await reset_shop(shop_id)


def get_mcp_app() -> Server:
    """Вернуть MCP Server instance для SSE-транспорта."""
    return app


def _json(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str))]


def _shaped(name: str, arguments: dict, data: Any) -> list[TextContent]:
    """Ответ инструмента: данные плюс заметки о пресете, усечении и размере.

    Заметки идут отдельными блоками, а не полем внутри JSON: у половины ручек WB
    верхний уровень ответа — массив, и обёртка сломала бы все привычные пути.
    """
    data, notes = shaping.shape(name, arguments, data)
    blocks = _json(data)
    blocks.extend(TextContent(type="text", text=note) for note in notes)
    return blocks


# Callback для записи статистики
_stats_callback: Callable[..., Awaitable[None]] | None = None


def set_stats_callback(cb: Callable[..., Awaitable[None]]):
    global _stats_callback
    _stats_callback = cb


# ─── Общий фрагмент shop_id для inputSchema ─────────────────

SHOP_ID_PROP = {"type": "string"}


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> Tool:
    """Создать Tool с необязательным shop_id.

    shop_id не в required: при единственном магазине сервер подставляет его сам
    (см. _call_tool_impl), а при нескольких — возвращает список доступных.
    Пустой required в схему не пишется — это ~7 токенов на инструмент.
    """
    props = {"shop_id": SHOP_ID_PROP}
    if properties:
        props.update(properties)
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = list(required)
    return Tool(name=name, description=description, inputSchema=schema)


# ─── Определение инструментов ─────────────────────────────

TOOLS = [
    # === МАГАЗИНЫ ===
    Tool(
        name="wb_list_shops",
        description="Registered WB shops (магазины): shop_id + name. Use shop_id in all other tools.",
        inputSchema={"type": "object", "properties": {}},
    ),

    # === P0: КАРТОЧКИ И БЛОКИРОВКИ ===
    _tool("wb_card_errors",
          "[P0] Cards with errors: blocked/rejected, incl. IP-holder complaints (заблокированные карточки). Check regularly."),
    _tool("wb_cards_list",
          "List product cards (карточки товаров), cursor pagination.",
          {"limit": {"type": "integer", "default": 100},
           "cursor": {"type": "object", "description": "pagination cursor"},
           "filter": {"type": "object", "description": "filter"}}),
    _tool("wb_card_detail",
          "Card details by nmID (карточка товара).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "nmID list"}},
          ["nm_ids"]),
    _tool("wb_cards_update",
          "Update cards: description, SEO, characteristics (обновить карточку).",
          {"cards": {"type": "array", "items": {"type": "object"}, "description": "updated cards"}},
          ["cards"]),
    _tool("wb_cards_move_to_trash",
          "Move cards to trash by nmID (удалить карточки).",
          {"nm_ids": {"type": "array", "items": {"type": "number"}, "description": "nmIDs to delete"}},
          ["nm_ids"]),
    _tool("wb_cards_recover_from_trash",
          "Restore cards from trash by nmID (восстановить карточки).",
          {"nm_ids": {"type": "array", "items": {"type": "number"}, "description": "nmIDs to restore"}},
          ["nm_ids"]),
    _tool("wb_cards_limits",
          "Card create/edit limits (лимиты карточек)."),
    _tool("wb_cards_create",
          "Create new cards, async, up to 30 min to sync. Get subject characteristics via wb_subject_charcs first (создать карточки).",
          {"cards": {"type": "array", "items": {"type": "object"}, "description": "[{subjectID, variants: [{vendorCode, title, description, brand, dimensions, characteristics, sizes}]}]"}},
          ["cards"]),
    _tool("wb_cards_trash",
          "Cards in trash (корзина).",
          {"limit": {"type": "integer", "default": 100}}),
    _tool("wb_barcodes_generate",
          "Generate barcodes for new goods (баркоды).",
          {"count": {"type": "integer", "default": 1}}),
    _tool("wb_media_upload",
          "Upload photo/video to a card by URL. Warning: REPLACES all existing media (медиа, фото).",
          {"nm_id": {"type": "integer"}, "links": {"type": "array", "items": {"type": "string"}, "description": "image URLs, min 700x900px"}},
          ["nm_id", "links"]),
    _tool("wb_subjects_search",
          "Search WB subjects/categories for card creation (предметы, категории).",
          {"name": {"type": "string", "description": "search by name"},
           "limit": {"type": "integer", "default": 30}}),
    _tool("wb_subject_charcs",
          "Subject characteristics: required/optional card fields (характеристики предмета).",
          {"subject_id": {"type": "integer"}},
          ["subject_id"]),
    _tool("wb_directory",
          "WB reference books: colors, kinds, countries, seasons, vat, tnved (справочники).",
          {"directory": {"type": "string", "description": "colors | kinds | countries | seasons | vat | tnved"},
           "subject_id": {"type": "integer", "description": "for tnved"},
           "search": {"type": "string", "description": "for tnved"}},
          ["directory"]),
    _tool("wb_tags",
          "Seller tags for grouping cards (ярлыки, теги)."),
    _tool("wb_tag_link",
          "Attach/detach tags on a card. Pass the FULL new tag list (привязать ярлык).",
          {"nm_id": {"type": "integer"}, "tag_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_id", "tag_ids"]),
    _tool("wb_tag_create",
          "Create a tag; color is HEX (создать ярлык).",
          {"name": {"type": "string"}, "color": {"type": "string", "default": "#FF0000"}},
          ["name"]),
    _tool("wb_tag_update",
          "Update a tag: name, color (обновить ярлык).",
          {"tag_id": {"type": "integer"}, "name": {"type": "string"}, "color": {"type": "string"}},
          ["tag_id", "name", "color"]),
    _tool("wb_tag_delete",
          "Delete a tag. Fails if still linked to goods — unlink via wb_tag_link first (удалить ярлык).",
          {"tag_id": {"type": "integer"}},
          ["tag_id"]),
    _tool("wb_card_recommendations_get",
          "Recommended goods on a card, cross-sell (рекомендации).",
          {"nm_id": {"type": "integer"}},
          ["nm_id"]),
    _tool("wb_card_recommendations_set",
          "Set recommended goods on a card, max 10 nmID (рекомендации, средний чек).",
          {"nm_id": {"type": "integer"}, "recommended_nm_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_id", "recommended_nm_ids"]),
    _tool("wb_brands_list",
          "Seller brands; subject_id filters by category (бренды).",
          {"subject_id": {"type": "integer", "description": "category filter"}}),

    # === P0: ЦЕНЫ ===
    _tool("wb_prices_list",
          "[P0] Current prices and discounts for all goods (цены, скидки, маржинальность).",
          {"limit": {"type": "integer", "default": 100},
           "offset": {"type": "integer", "default": 0},
           "filter_nm_id": {"type": "integer", "description": "nmID filter"}}),
    _tool("wb_prices_set",
          "[P0] Set prices and discounts. Items: {nmID, price, discount} (установить цену).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, price, discount}]"}},
          ["data"]),
    _tool("wb_prices_quarantine",
          "[P0] Goods in price quarantine: cut over 3x, new price NOT applied (карантин цен). Check regularly.",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}}),
    _tool("wb_prices_club_discount",
          "Set WB Club discounts, max 1000 goods per request (скидка WB Клуба).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, clubDiscount}, ...]"}},
          ["data"]),
    _tool("wb_prices_upload_status",
          "Price upload status by uploadID from wb_prices_set. buffer=true for deferred uploads (статус загрузки цен).",
          {"upload_id": {"type": "integer"}, "buffer": {"type": "boolean", "default": False},
           "details": {"type": "boolean", "default": False, "description": "true = detail for goods with errors"}},
          ["upload_id"]),
    _tool("wb_prices_size_list",
          "Prices per size for one product (цены по размерам).",
          {"nm_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["nm_id"]),
    _tool("wb_prices_b2b_set",
          "Set B2B wholesale discounts: {nmID, wholesaleDiscount} (оптовые скидки).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, wholesaleDiscount}, ...]"}},
          ["data"]),

    # === АКЦИИ И АВТОАКЦИИ (КАЛЕНДАРЬ ПРОМО) ===
    _tool("wb_promotions_list",
          "[P0] WB promotions for a period. type: 'auto' = WB adds goods itself, 'regular' (акции, промо). Monitor auto ones.",
          {"start": {"type": "string", "description": "RFC3339 (2026-06-01T00:00:00Z)"},
           "end": {"type": "string", "description": "RFC3339"},
           "all_promo": {"type": "boolean", "default": False, "description": "false = eligible only, true = all"},
           "promo_type": {"type": "string", "enum": ["auto", "regular"], "description": "type filter: auto | regular"},
           "limit": {"type": "integer", "default": 100, "description": "1-1000"},
           "offset": {"type": "integer", "default": 0}},
          ["start", "end"]),
    _tool("wb_promotions_auto",
          "[P0] Auto-promotions only (type=auto): WB adds goods without asking (автоакции). Regular monitoring keeps prices from dropping.",
          {"start": {"type": "string", "description": "RFC3339"},
           "end": {"type": "string", "description": "RFC3339"}},
          ["start", "end"]),
    _tool("wb_promotions_audit",
          "[P0] Participation audit: which promotions already hold my goods and the price effect (price→planPrice, % drop). For auto-promos WB hides the item list (nomenclaturesAvailable=false) — control prices via wb_prices_list/wb_prices_quarantine. Auto-throttled to 10 req/6 s (аудит акций).",
          {"start": {"type": "string", "description": "RFC3339"},
           "end": {"type": "string", "description": "RFC3339"},
           "only_auto": {"type": "boolean", "default": False, "description": "true = auto-promos only (items hidden); false = all"},
           "max_promotions": {"type": "integer", "default": 25, "description": "how many promos to check, rate-limit guard"}},
          ["start", "end"]),
    _tool("wb_promotions_details",
          "Promotion details: dates, ranging/boost conditions, slots, participationPercentage, advantages, type (детали акции).",
          {"promotion_ids": {"type": "array", "items": {"type": "integer"}}},
          ["promotion_ids"]),
    _tool("wb_promotions_products",
          "Goods eligible for a promotion. in_action: true = participating. Returns price/planPrice, discount/planDiscount (товары акции).",
          {"promotion_id": {"type": "integer"},
           "in_action": {"type": "boolean", "description": "participation filter"},
           "limit": {"type": "integer", "default": 100, "description": "1-1000"},
           "offset": {"type": "integer", "default": 0}},
          ["promotion_id"]),
    _tool("wb_promotions_add_products",
          "Add goods to a promotion. upload_now=false defers until start. Returns uploadID (вступить в акцию).",
          {"promotion_id": {"type": "integer"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}},
           "upload_now": {"type": "boolean", "default": True}},
          ["promotion_id", "nm_ids"]),
    _tool("wb_promotion_exit",
          "[P0] Leave a promotion: restore price and discount via Prices API, WB has no exit endpoint (выйти из акции).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, price, discount}] pre-promo values"}},
          ["data"]),

    # === P0: ФИНАНСЫ И РЕАЛИЗАЦИЯ ===
    _tool("wb_finance_report",
          "[P0] Realization report for a period: commissions, logistics, storage, penalties, payout (отчёт о реализации, прибыль). Use wb_finance_reports_list + wb_finance_report_detailed for detail.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 500}, "rrd_id": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_reports_list",
          "[P0] Realization reports list, finance-api v1, data from 2025-01-01. Then call wb_finance_report_detailed (список отчётов).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "period": {"type": "string", "enum": ["weekly", "monthly"], "default": "weekly"},
           "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_report_detailed",
          "[P0] Realization report detail by reportId: commissions, logistics, storage, penalties, payout. Paginate via rrd_id (детализация отчёта).",
          {"report_id": {"type": "string"}, "limit": {"type": "integer", "default": 500},
           "rrd_id": {"type": "integer", "default": 0}},
          ["report_id"]),
    _tool("wb_finance_acquiring_list",
          "Acquiring cost reports, card payment fees (эквайринг).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "period": {"type": "string", "default": "weekly"},
           "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_acquiring_detailed",
          "Acquiring cost detail for a period (эквайринг, детализация).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 500}, "rrd_id": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),

    # === P0: РЕКЛАМА (ДРР) ===
    # С февраля 2026 WB перевёл рекламу на новую модель: кампании типа 9
    # (seacat), ставки manual/unified, кластеры вместо ключевых фраз.
    _tool("wb_advert_list",
          "[P0] Ad campaigns with settings and bids. statuses: 9=active, 11=paused, 7=finished, 4=ready, 8=cancelled, -1=deleted (реклама, кампании).",
          {"ids": {"type": "array", "items": {"type": "integer"}, "description": "campaign ids, max 50"},
           "statuses": {"type": "array", "items": {"type": "integer"}, "description": "status filter"},
           "payment_type": {"type": "string", "description": "cpm | cpc"}}),
    _tool("wb_advert_count",
          "Campaign counts by type and status; use to get all campaign IDs (количество кампаний)."),
    _tool("wb_advert_create",
          "Create ad campaign (type 9 Search+Catalog, the only one since 2026). bid_type: unified | manual with placement_types (создать кампанию).",
          {"name": {"type": "string"}, "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "offer_ids, max 50"},
           "bid_type": {"type": "string", "default": "unified", "description": "unified | manual"},
           "payment_type": {"type": "string", "default": "cpm", "description": "cpm | cpc"},
           "placement_types": {"type": "array", "items": {"type": "string"}, "description": "for manual: search, recommendations"}},
          ["name", "nm_ids"]),
    _tool("wb_advert_stats",
          "[P0] Campaign stats: spend, views, clicks, CTR, CPC, orders, revenue + daily breakdown in days[]. Limit 3 req/min, period ≤31 d. Spend/revenue over 20% means ДРР too high (статистика рекламы).",
          {"advert_ids": {"type": "array", "items": {"type": "integer"}, "description": "campaign ids"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["advert_ids", "date_from", "date_to"]),
    _tool("wb_advert_balance",
          "Ad account balance: account, balance, bonuses (баланс рекламы)."),
    _tool("wb_advert_budget",
          "Budget of one ad campaign (бюджет кампании).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_deposit",
          "Top up campaign budget. source: 0=account, 1=balance, 3=bonuses (пополнить бюджет).",
          {"advert_id": {"type": "integer"}, "amount": {"type": "integer", "description": "amount, RUB"},
           "source": {"type": "integer", "default": 0}},
          ["advert_id", "amount"]),
    _tool("wb_advert_costs",
          "Ad spend history for a period (затраты на рекламу).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_advert_pause",
          "[P0] Emergency pause of an ad campaign, e.g. when ДРР over 20% (остановить рекламу).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_start",
          "Start an ad campaign (запустить рекламу).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_stop",
          "Finish an ad campaign for good, unlike pause (завершить кампанию).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_delete",
          "Delete an ad campaign, irreversible (удалить кампанию).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_bids_set",
          "[P0] Change CPM/CPC bids. Bids in KOPECKS. placement: search | recommendations | combined for unified (ставки).",
          {"bids": {"type": "array", "items": {"type": "object"},
                    "description": "[{advert_id, nm_bids: [{nm_id, bid_kopecks, placement}]}]"}},
          ["bids"]),
    _tool("wb_advert_bids_recommendations",
          "Recommended bids for a card in a campaign (рекомендованные ставки).",
          {"nm_id": {"type": "integer"}, "advert_id": {"type": "integer"}},
          ["nm_id", "advert_id"]),
    _tool("wb_advert_clusters",
          "[P0] Search clusters of a campaign, replaced keyword phrases in 2026 (поисковые кластеры, запросы, SEO).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_clusters_stats",
          "Search cluster stats for a period; daily=true for per-day rows (статистика кластеров).",
          {"advert_id": {"type": "integer"}, "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "offer_id filter"},
           "daily": {"type": "boolean", "default": False}},
          ["advert_id", "date_from", "date_to"]),
    _tool("wb_advert_cluster_bids",
          "Set bids on specific search clusters. Bid in RUBLES per 1000 views (ставки на кластеры).",
          {"bids": {"type": "array", "items": {"type": "object"},
                    "description": "[{advert_id, nm_id, norm_query, bid}]"}},
          ["bids"]),
    _tool("wb_advert_minus_phrases",
          "Campaign minus-phrases: read without norm_queries, set with them. WB has no plus-phrases since 2026 (минус-фразы).",
          {"advert_id": {"type": "integer"}, "nm_id": {"type": "integer", "description": "offer_id"},
           "norm_queries": {"type": "array", "items": {"type": "string"}, "description": "set minus-phrases; omit to read"}},
          ["advert_id"]),
    _tool("wb_advert_payments",
          "Ad account top-up history for a period, dates YYYY-MM-DD (пополнения счёта).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_advert_rename",
          "Rename an ad campaign (переименовать кампанию).",
          {"advert_id": {"type": "integer"}, "name": {"type": "string"}},
          ["advert_id", "name"]),

    # === КОНТЕНT: расширение ===
    _tool("wb_cards_move_nm",
          "Merge/split cards, max 30 nmID. target_imt set = merge into that imtID, unset = split (объединить карточки).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "target_imt": {"type": "integer", "description": "imtID to merge into; omit to split"}},
          ["nm_ids"]),
    _tool("wb_card_add_nomenclature",
          "Add a nomenclature/size to an existing card by imtID (добавить размер).",
          {"imt_id": {"type": "integer"},
           "cards_to_add": {"type": "array", "items": {"type": "object"}, "description": "new nomenclatures"}},
          ["imt_id", "cards_to_add"]),
    _tool("wb_categories_parent",
          "All parent product categories (родительские категории).",
          {"locale": {"type": "string", "description": "ru | en | zh, default ru"}}),
    _tool("wb_media_upload_file",
          "Upload media as a FILE by URL, server downloads and sends. photo_number from 1, video = 1 (загрузить фото файлом).",
          {"nm_id": {"type": "integer"}, "photo_number": {"type": "integer"},
           "file_url": {"type": "string", "description": "file URL"}},
          ["nm_id", "photo_number", "file_url"]),

    # === FBS: маркировка (КИЗ), пропуска, короба ===
    _tool("wb_order_meta_get",
          "FBS order meta/marking; available keys come from the order's requiredMeta (маркировка заказа).",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_order_meta_set",
          "[P0] Set FBS order marking: meta_type = sgtin|uin|imei|gtin|expiration. Only in status confirm (маркировка, Честный знак).",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin", "expiration"]},
           "value": {"description": "sgtin: Data Matrix array; uin/imei/gtin: string; expiration: dd.mm.yyyy"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_order_meta_delete",
          "Delete FBS order meta by key: imei|uin|gtin|sgtin (удалить маркировку).",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}},
          ["order_id", "key"]),
    _tool("wb_orders_status_history",
          "Order status history, cross-border, max 100 (история статусов).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_orders_client_info",
          "Buyer data for cross-border orders from Turkey (данные покупателя).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_supplies_reshipment",
          "Orders that need reshipment (повторная отгрузка)."),
    _tool("wb_orders_external_stickers",
          "Cross-border delivery stickers, max 100, status complete (стикеры доставки).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_orders_archive",
          "Archived FBS orders for a period: finished or cancelled (архив заказов).",
          {"date_from": {"type": "string", "description": "RFC3339"},
           "date_to": {"type": "string", "description": "RFC3339"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from"]),
    _tool("wb_supply_order_ids",
          "Assembly task IDs inside an FBS supply (задания в поставке).",
          {"supply_id": {"type": "string"}}, ["supply_id"]),
    _tool("wb_passes_offices",
          "Offices/warehouses that require a pass (офисы, пропуска)."),
    _tool("wb_passes_list",
          "Active warehouse passes (пропуска)."),
    _tool("wb_pass_create",
          "Create a warehouse pass, valid 48 h (создать пропуск).",
          {"first_name": {"type": "string"}, "last_name": {"type": "string"},
           "car_model": {"type": "string"}, "car_number": {"type": "string"}, "office_id": {"type": "integer"}},
          ["first_name", "last_name", "car_model", "car_number", "office_id"]),
    _tool("wb_pass_update",
          "Update a warehouse pass (обновить пропуск).",
          {"pass_id": {"type": "integer"}, "first_name": {"type": "string"}, "last_name": {"type": "string"},
           "car_model": {"type": "string"}, "car_number": {"type": "string"}, "office_id": {"type": "integer"}},
          ["pass_id", "first_name", "last_name", "car_model", "car_number", "office_id"]),
    _tool("wb_pass_delete",
          "Delete a warehouse pass (удалить пропуск).",
          {"pass_id": {"type": "integer"}}, ["pass_id"]),
    _tool("wb_supply_trbx_list",
          "Boxes (trbx) of an FBS supply (короба поставки).",
          {"supply_id": {"type": "string"}}, ["supply_id"]),
    _tool("wb_supply_trbx_add",
          "Add boxes to a supply, amount 1..1000, pickup points only while assembling (добавить короба).",
          {"supply_id": {"type": "string"}, "amount": {"type": "integer"}},
          ["supply_id", "amount"]),
    _tool("wb_supply_trbx_delete",
          "Delete boxes from a supply (удалить короба).",
          {"supply_id": {"type": "string"}, "trbx_ids": {"type": "array", "items": {"type": "string"}}},
          ["supply_id", "trbx_ids"]),
    _tool("wb_supply_trbx_stickers",
          "Box QR stickers: svg|zplv|zplh|png (стикеры коробов).",
          {"supply_id": {"type": "string"}, "trbx_ids": {"type": "array", "items": {"type": "string"}},
           "sticker_type": {"type": "string", "enum": ["svg", "zplv", "zplh", "png"]}},
          ["supply_id", "trbx_ids"]),

    # === DBS: доставка силами продавца ===
    _tool("wb_dbs_orders_new", "New DBS orders awaiting assembly (новые DBS-заказы)."),
    _tool("wb_dbs_orders",
          "Finished DBS orders, Unix timestamps, ≤30 days, cursor next (DBS-заказы).",
          {"limit": {"type": "integer", "default": 100}, "next": {"type": "integer", "default": 0},
           "date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"}},
          ["date_from", "date_to"]),
    _tool("wb_dbs_orders_status",
          "DBS order statuses, max 1000 (статусы DBS).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_orders_client",
          "DBS buyer data, after confirm (покупатель DBS).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_orders_delivery_date",
          "Delivery date/time chosen by the DBS buyer, max 1000 (дата доставки).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_groups_info",
          "Paid delivery cost by groupId, max 1000 (стоимость доставки).",
          {"group_ids": {"type": "array", "items": {"type": "string"}}}, ["group_ids"]),
    _tool("wb_dbs_order_action",
          "[P0] Change DBS order status: action = confirm|deliver|receive|reject|cancel. receive/reject need the buyer code (статус DBS-заказа).",
          {"order_id": {"type": "integer"},
           "action": {"type": "string", "enum": ["confirm", "deliver", "receive", "reject", "cancel"]},
           "code": {"type": "string", "description": "buyer code, for receive/reject"}},
          ["order_id", "action"]),
    _tool("wb_dbs_order_meta_get",
          "DBS order meta (метаданные DBS).",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_dbs_order_meta_set",
          "DBS order marking: sgtin|uin|imei|gtin, status confirm (маркировка DBS).",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin"]},
           "value": {"description": "sgtin: array; others: string"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_dbs_order_meta_delete",
          "Delete DBS order meta by key (удалить маркировку DBS).",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}}, ["order_id", "key"]),

    # === CLICK-COLLECT: самовывоз ===
    _tool("wb_cc_orders_new", "New click-and-collect tasks (новые задания самовывоза)."),
    _tool("wb_cc_orders",
          "Finished click-and-collect tasks, Unix timestamps, ≤30 days (задания самовывоза).",
          {"limit": {"type": "integer", "default": 100}, "next": {"type": "integer", "default": 0},
           "date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"}},
          ["date_from", "date_to"]),
    _tool("wb_cc_orders_status",
          "Click-and-collect task statuses (статусы самовывоза).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_cc_orders_client",
          "Buyer data, statuses confirm/prepare (покупатель самовывоза).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_cc_order_identity",
          "[P0] Verify the buyer code when handing over a click-and-collect order (код покупателя).",
          {"order_code": {"type": "string"}, "passcode": {"type": "string"}},
          ["order_code", "passcode"]),
    _tool("wb_cc_order_action",
          "[P0] Change click-and-collect status: action = confirm|prepare|receive|reject|cancel (статус самовывоза).",
          {"order_id": {"type": "integer"},
           "action": {"type": "string", "enum": ["confirm", "prepare", "receive", "reject", "cancel"]}},
          ["order_id", "action"]),
    _tool("wb_cc_order_meta_get",
          "Click-and-collect task meta (метаданные самовывоза).",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_cc_order_meta_set",
          "Click-and-collect marking: sgtin|uin|imei|gtin, status confirm (маркировка самовывоза).",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin"]},
           "value": {"description": "sgtin: array; others: string"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_cc_order_meta_delete",
          "Delete click-and-collect meta by key (удалить маркировку).",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}}, ["order_id", "key"]),

    # === АНАЛИТИКА: расширение ===
    _tool("wb_analytics_brand_share",
          "Brand share in a category, ≤365 days. Needs parentId and brand from the brand_share_parents/brands tools (доля бренда).",
          {"parent_id": {"type": "integer"}, "brand": {"type": "string"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["parent_id", "brand", "date_from", "date_to"]),
    _tool("wb_analytics_brand_share_brands",
          "Seller brands sold in the last 90 days, input for brand-share (бренды для доли)."),
    _tool("wb_analytics_brand_share_parents",
          "Parent categories of a brand, input for brand-share (категории бренда).",
          {"brand": {"type": "string"}, "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "locale": {"type": "string", "description": "ru|en|zh"}},
          ["brand", "date_from", "date_to"]),
    _tool("wb_analytics_region_sale",
          "Sales by region, ≤31 days, YYYY-MM-DD (продажи по регионам).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_excise",
          "Chestny Znak excise/labeling report. Limit 10 req per 5 hours (Честный знак, КиЗ).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_item_rating",
          "Item rating: card views, cart adds, orders, conversions. Jam subscription. Low conversion signals a card or price problem. Max 1000 nmID (рейтинг товаров, конверсия).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_ids"]),
    _tool("wb_analytics_grouped_history",
          "Sales funnel by product groups, per day, compares periods (воронка по группам).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "aggregation_level": {"type": "string", "default": "day"}},
          ["nm_ids", "date_from", "date_to"]),
    _tool("wb_nm_report",
          "Per-nmID report: revenue, orders, returns, conversions. Task-based, waits up to 3 min, kept 3 days (отчёт по номенклатуре).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "date_to": {"type": "string"}}),
    _tool("wb_analytics_stocks_sizes",
          "Stock and turnover report split by size, finds dead sizes (остатки по размерам, неликвид).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("wb_search_table_details",
          "Search analytics per product: positions and conversions by query. Requires Jam (поисковая аналитика).",
          {"body": {"type": "object", "description": "{currentPeriod{start,end}, orderBy{field,mode}, positionCluster, limit, offset, ...}"}},
          ["body"]),
    _tool("wb_search_table_groups",
          "Search analytics by group: subject, brand, tag. Requires Jam (поисковая аналитика по группам).",
          {"body": {"type": "object", "description": "{currentPeriod{start,end}, orderBy, positionCluster, limit, offset, ...}"}},
          ["body"]),
    _tool("wb_search_product_orders",
          "Orders and positions by search query for a product, ≤7 days. Requires Jam (заказы по запросам).",
          {"nm_id": {"type": "integer"}, "search_texts": {"type": "array", "items": {"type": "string"}, "description": "1..30 queries"},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["nm_id", "search_texts", "date_from", "date_to"]),

    # === ОТЗЫВЫ/ВОПРОСЫ: расширение ===
    _tool("wb_new_feedbacks_questions",
          "Flags for unseen feedbacks/questions: hasNewFeedbacks, hasNewQuestions (новые отзывы и вопросы)."),
    _tool("wb_feedbacks_actions",
          "Complain about a feedback or report a product problem, codes from supplier-valuations (жалоба на отзыв).",
          {"feedback_id": {"type": "string"},
           "feedback_valuation": {"type": "integer", "description": "complaint reason"},
           "product_valuation": {"type": "integer", "description": "product problem"}},
          ["feedback_id"]),
    _tool("wb_feedbacks_archive",
          "Archived feedbacks, previously answered, unlike wb_feedbacks_list (архив отзывов).",
          {"take": {"type": "integer", "default": 50}, "skip": {"type": "integer", "default": 0},
           "nm_id": {"type": "integer", "description": "nmID filter"}}),
    _tool("wb_feedbacks_pins",
          "Pinned feedbacks shown first on the card (закреплённые отзывы)."),
    _tool("wb_feedbacks_pins_count",
          "Pinned feedback count, limit 3 per nmID (число закреплённых)."),
    _tool("wb_feedbacks_pins_set",
          "Pin feedbacks, max 3 per nmID (закрепить отзывы).",
          {"feedback_ids": {"type": "array", "items": {"type": "string"}}},
          ["feedback_ids"]),
    _tool("wb_feedbacks_pins_delete",
          "Unpin feedbacks (открепить отзывы).",
          {"feedback_ids": {"type": "array", "items": {"type": "string"}}},
          ["feedback_ids"]),
    _tool("wb_question_get",
          "One buyer question by ID (вопрос покупателя).",
          {"question_id": {"type": "string"}}, ["question_id"]),
    _tool("wb_feedback_order_return",
          "Request a product return from a feedback, only if isAbleReturnProductOrders=true (возврат по отзыву).",
          {"feedback_id": {"type": "string"}}, ["feedback_id"]),
    _tool("wb_feedbacks_count_period",
          "Feedback count for a period, Unix ts, isAnswered filter (число отзывов за период).",
          {"date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"},
           "is_answered": {"type": "boolean"}}),
    _tool("wb_questions_count_period",
          "Question count for a period, Unix ts, isAnswered filter (число вопросов за период).",
          {"date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"},
           "is_answered": {"type": "boolean"}}),

    # === РЕКЛАМА: расширение ===
    _tool("wb_advert_subjects",
          "Subjects available for ad campaigns (предметы для рекламы)."),
    _tool("wb_advert_available_nms",
          "Goods available for campaigns, by subject IDs (товары для рекламы).",
          {"subject_ids": {"type": "array", "items": {"type": "integer"}}}, ["subject_ids"]),

    # === ДЖЕМ: подписка ===
    _tool("wb_jam_subscription",
          "WB Jam subscription state: active, expiry. Check before Jam-only tools (подписка Джем)."),

    # === P0: ТАРИФЫ ЛОГИСТИКИ И ХРАНЕНИЯ ===
    _tool("wb_tariffs_box",
          "[P0] Box logistics tariffs for FBO; tariff growth eats margin (тарифы логистики).",
          {"date": {"type": "string", "description": "YYYY-MM-DD, default today"}}),
    _tool("wb_tariffs_pallet",
          "Pallet logistics tariffs for FBO (тарифы палет).",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}}),
    _tool("wb_tariffs_return",
          "[P0] Reverse logistics tariffs for returns, a hidden cost at high return rates (тарифы возвратов).",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}}),
    _tool("wb_tariffs_commission",
          "[P0] WB commissions by category for FBO, FBS, DBS; input for unit economics (комиссии). "
          "Pass subject to filter: the full reference is 7 400 categories.",
          {"subject": {"type": "string",
                       "description": "category name substring, case-insensitive (название категории)"}}),
    _tool("wb_fbw_transit_tariffs",
          "Transit directions for FBW supplies to regions (транзитные тарифы). Temporarily disabled by WB itself."),

    # === P0: ПЛАТНОЕ ХРАНЕНИЕ ===
    _tool("wb_paid_storage",
          "[P0] Paid storage report; goods with no sales and high storage cost are direct losses (платное хранение).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P1: АНАЛИТИКА ===
    _tool("wb_analytics_detail",
          "Sales funnel per product: views, clicks, cart, orders, revenue, conversions, vs previous period. Limit 3 req/min (воронка продаж).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "nmID list"},
           "brand_names": {"type": "array", "items": {"type": "string"}, "description": "brands"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_history",
          "Sales funnel BY DAY, last week at most, for conversion trends (воронка по дням).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["nm_ids", "date_from", "date_to"]),
    _tool("wb_analytics_stocks",
          "Interactive stock and turnover report: healthy, scarce and dead goods (остатки, оборачиваемость).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from", "date_to"]),
    _tool("wb_warehouse_remains",
          "Stock report split by WB warehouse. Task-based, 10-60 s (остатки по складам)."),
    _tool("wb_analytics_antifraud",
          "Deductions for self-buyouts, published on Wednesdays (удержания за самовыкупы).",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}},
          ["date"]),
    _tool("wb_analytics_acceptance",
          "Paid acceptance report at WB warehouses. Task-based, 10-60 s (платная приёмка).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_banned_products",
          "[P0] Blocked or shadowed cards hidden from the catalogue — lost sales (заблокированные товары).",
          {"shadowed": {"type": "boolean", "default": False, "description": "true = shadowed, false = blocked"}}),
    _tool("wb_deductions",
          "Deductions for substitutions and wrong contents (удержания за подмены). "
          "Both dates are required: WB rejects the call without date_from.",
          {"date_to": {"type": "string", "description": "YYYY-MM-DD"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"},
           "limit": {"type": "integer", "default": 100}},
          ["date_to", "date_from"]),
    _tool("wb_search_report",
          "[P0] Search query report: views, clicks, search positions. Requires Jam. Limit 3 req/min (поисковые запросы, видимость).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "filter"},
           "limit": {"type": "integer", "default": 30}},
          ["date_from", "date_to"]),
    _tool("wb_search_texts",
          "Top search queries for specific goods, max 30 without Jam (поисковые фразы).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 30}},
          ["nm_ids", "date_from", "date_to"]),

    # === ФИНАНСЫ И ИНФО ===
    _tool("wb_finance_balance",
          "[P0] Seller balance: payable, in transit. Token needs the Finance category (баланс продавца)."),
    _tool("wb_seller_info",
          "Seller info: name, profile ID. Works with any token (информация о продавце)."),

    # === P1: ЗАКАЗЫ ===
    _tool("wb_orders_new",
          "New FBS orders awaiting assembly (новые заказы)."),
    _tool("wb_orders_list",
          "All orders for a period (заказы за период).",
          {"date_from": {"type": "string", "description": "RFC3339 (2024-01-01T00:00:00Z)"},
           "date_to": {"type": "string", "description": "RFC3339"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from"]),
    _tool("wb_orders_status",
          "Statuses of specific orders (статусы заказов).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["order_ids"]),
    _tool("wb_order_cancel",
          "Cancel an FBS assembly task, irreversible (отменить заказ).",
          {"order_id": {"type": "integer"}},
          ["order_id"]),
    _tool("wb_orders_stickers",
          "Stickers for FBS assembly tasks, max 100. Formats: svg, zplv, zplh, png (стикеры заказов).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}},
           "sticker_type": {"type": "string", "default": "png"},
           "width": {"type": "integer", "default": 58}, "height": {"type": "integer", "default": 40}},
          ["order_ids"]),
    _tool("wb_supply_create",
          "Create an FBS supply to ship assembled orders (создать поставку).",
          {"name": {"type": "string"}},
          ["name"]),
    _tool("wb_supply_detail",
          "FBS supply info (детали поставки).",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),
    _tool("wb_supply_add_orders",
          "Add assembly tasks to an FBS supply, max 100, tasks move to confirm (добавить заказы в поставку).",
          {"supply_id": {"type": "string"}, "order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["supply_id", "order_ids"]),
    _tool("wb_supply_deliver",
          "Close an FBS supply and hand it to delivery, tasks move to complete (закрыть поставку).",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),
    _tool("wb_supply_barcode",
          "FBS supply QR code for warehouse handover (QR поставки).",
          {"supply_id": {"type": "string"}, "barcode_type": {"type": "string", "default": "png"}},
          ["supply_id"]),
    _tool("wb_supply_delete",
          "Delete an empty active FBS supply (удалить поставку).",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),

    # === P1: ПРОДАЖИ И ОСТАТКИ (СТАТИСТИКА) ===
    _tool("wb_stats_sales",
          "Sales for a period; spots goods that stopped selling (продажи).",
          {"date_from": {"type": "string", "description": "RFC3339"}},
          ["date_from"]),
    _tool("wb_stats_orders",
          "Order statistics including cancellations; for cancel and return analysis (заказы, отмены).",
          {"date_from": {"type": "string"}, "flag": {"type": "integer", "default": 0, "description": "1 = updated only"}},
          ["date_from"]),
    _tool("wb_stats_stocks",
          "[P0] Current stock across ALL WB warehouses (API cap 1000, default 100). nm_ids filters by article. Stock without sales means overpaid storage (остатки).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "offer_id filter"},
           "limit": {"type": "integer", "default": 100}}),

    # === P1: ОТЗЫВЫ И ВОПРОСЫ ===
    _tool("wb_feedbacks_list",
          "Feedback list. Unanswered negatives cut rating and conversion (отзывы).",
          {"is_answered": {"type": "boolean", "description": "true = answered, false = unanswered"},
           "nm_id": {"type": "integer", "description": "nmID filter"},
           "take": {"type": "integer", "default": 50}}),
    _tool("wb_feedbacks_count",
          "Count of unanswered feedbacks (неотвеченные отзывы)."),
    _tool("wb_feedback_reply",
          "Reply to a feedback; edit=true rewrites an existing reply (ответить на отзыв).",
          {"feedback_id": {"type": "string"}, "text": {"type": "string"},
           "edit": {"type": "boolean", "default": False}},
          ["feedback_id", "text"]),
    _tool("wb_seller_rating",
          "Seller rating of the shop (рейтинг продавца)."),
    _tool("wb_questions_list",
          "Buyer questions list (вопросы покупателей).",
          {"is_answered": {"type": "boolean", "description": "filter"},
           "nm_id": {"type": "integer", "description": "nmID filter"},
           "take": {"type": "integer", "default": 50}}),
    _tool("wb_questions_count",
          "Count of unanswered questions (неотвеченные вопросы)."),
    _tool("wb_question_reply",
          "Reply to a buyer question; reject=true declines it (ответить на вопрос).",
          {"question_id": {"type": "string"}, "text": {"type": "string"},
           "reject": {"type": "boolean", "default": False}},
          ["question_id", "text"]),

    # === P1: ВОЗВРАТЫ ===
    _tool("wb_returns_list",
          "Buyer return claims. is_archive=false = pending, NEED an answer; true = archive. actions[] lists allowed actions (возвраты, заявки).",
          {"is_archive": {"type": "boolean", "default": False},
           "nm_id": {"type": "integer", "description": "product filter"},
           "limit": {"type": "integer", "default": 200}}),
    _tool("wb_return_answer",
          "Answer a return claim. action strictly from the claim's actions[]: approve1 (defect check at WB), approve2 (take the item back), autorefund1 (refund without return), reject1/reject2/reject3 (WB refusal templates), rejectcustom (needs comment) (ответ на возврат).",
          {"claim_id": {"type": "string"}, "action": {"type": "string"},
           "comment": {"type": "string", "description": "for rejectcustom"}},
          ["claim_id", "action"]),
    _tool("wb_goods_return_report",
          "Analytics report on goods returned to the seller, max 31 days (отчёт по возвратам).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P2: СКЛАДЫ И ПОСТАВКИ ===
    _tool("wb_warehouses",
          "Seller warehouses (склады продавца)."),
    _tool("wb_warehouse_create",
          "Create a seller warehouse for FBS (создать склад).",
          {"name": {"type": "string"}, "address": {"type": "string"}},
          ["name"]),
    _tool("wb_warehouse_update",
          "Update a seller warehouse (обновить склад).",
          {"warehouse_id": {"type": "integer"}, "name": {"type": "string"},
           "address": {"type": "string"}},
          ["warehouse_id"]),
    _tool("wb_warehouse_delete",
          "Delete a seller warehouse (удалить склад).",
          {"warehouse_id": {"type": "integer"}},
          ["warehouse_id"]),
    _tool("wb_supplies_list",
          "Supplies list (поставки)."),
    _tool("wb_stocks_update",
          "Update FBS stock. Field names are not validated: a typo returns 204 with no update (обновить остатки).",
          {"warehouse_id": {"type": "integer"}, "stocks": {"type": "array", "items": {"type": "object"}, "description": "[{sku, amount}, ...]"}},
          ["warehouse_id", "stocks"]),
    _tool("wb_stocks_get",
          "Get FBS stock by barcodes (остатки FBS).",
          {"warehouse_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "string"}}},
          ["warehouse_id", "skus"]),
    _tool("wb_stocks_delete",
          "Delete FBS stock records by SKU, zeroing them (удалить остатки).",
          {"warehouse_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "string"}}},
          ["warehouse_id", "skus"]),

    # === ПОСТАВКИ FBW (НА СКЛАДЫ WB) ===
    _tool("wb_fbw_supplies",
          "FBW supplies to WB warehouses, read-only; creation lives in the seller portal (поставки FBW).",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0},
           "status_ids": {"type": "array", "items": {"type": "integer"}, "description": "status filter"}}),
    _tool("wb_fbw_supply_detail",
          "FBW supply details (детали поставки FBW).",
          {"supply_id": {"type": "integer"}},
          ["supply_id"]),
    _tool("wb_fbw_supply_goods",
          "Goods inside an FBW supply (товары в поставке).",
          {"supply_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["supply_id"]),
    _tool("wb_fbw_acceptance_options",
          "Warehouses and packaging types available for an FBW supply, by barcodes (варианты приёмки).",
          {"items": {"type": "array", "items": {"type": "object"}, "description": "[{barcode, quantity}, ...]"},
           "warehouse_id": {"type": "integer", "description": "one warehouse"}},
          ["items"]),
    _tool("wb_fbw_warehouses",
          "WB warehouses for FBW supplies (склады FBW). Temporarily disabled by WB itself — returns an explanation, not data."),
    _tool("wb_acceptance_coefficients",
          "[P0] Warehouse acceptance coefficients for 14 days; coefficient 0 or 1 with allowUnload=true means acceptance is open, x2-x7 multiplies the cost (коэффициенты приёмки). Temporarily disabled by WB itself.",
          {"warehouse_ids": {"type": "array", "items": {"type": "integer"}, "description": "warehouse filter"}}),

    # === P2: ОБРАЩЕНИЯ ПОКУПАТЕЛЕЙ ===
    _tool("wb_buyer_chats",
          "Buyer chats, includes replySign for answering. May hold complaints and IP-holder claims (чаты с покупателями)."),
    _tool("wb_chat_events",
          "Chat events, new messages. Cursor pagination: first call without next, then next from the response (события чатов).",
          {"next_cursor": {"type": "integer", "description": "cursor from previous response"}}),
    _tool("wb_chat_send",
          "Send a message to a buyer chat, ≤1000 chars. reply_sign comes from wb_buyer_chats (написать покупателю).",
          {"reply_sign": {"type": "string"}, "message": {"type": "string"}},
          ["reply_sign", "message"]),
    _tool("wb_chat_download",
          "Download a file from a buyer chat; file_id comes from a chat event (файл из чата).",
          {"file_id": {"type": "string"}},
          ["file_id"]),

    # === P1: ДОКУМЕНТЫ ===
    _tool("wb_documents_categories",
          "Document categories: reconciliation acts, УПД, invoices (категории документов)."),
    _tool("wb_documents_list",
          "Seller financial documents: acts, УПД, notices. Needed for accounting (документы, бухгалтерия).",
          {"date_from": {"type": "string", "description": "start date"},
           "date_to": {"type": "string", "description": "end date"},
           "category_id": {"type": "integer", "description": "category id from wb_documents_categories"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("wb_document_download",
          "Download one document, PDF/XML, by ID (скачать документ).",
          {"document_id": {"type": "string", "description": "document id from wb_documents_list"}},
          ["document_id"]),
    _tool("wb_documents_download_bulk",
          "Download several documents in one request by IDs (скачать документы).",
          {"document_ids": {"type": "array", "items": {"type": "string"}}},
          ["document_ids"]),

    # === P3: ПОЛЬЗОВАТЕЛИ ===
    _tool("wb_diagnostics",
          "[P0] Full self-diagnostics: ping all WB API hosts, light real requests per category, token analysis (expiry, scopes). Run FIRST when a tool misbehaves — separates a token problem from a category or WB API change (диагностика)."),
    _tool("wb_token_info",
          "Token info for a shop: scopes, expiry, read-only/sandbox. No WB requests (информация о токене)."),
    Tool(
        name="wb_degradations",
        description="Tool degradations: which MCP tools used to work and now fail steadily, signalling a WB API change. No parameters (деградации).",
        inputSchema={"type": "object", "properties": {}},
    ),
    _tool("wb_api_news",
          "WB seller news including API change announcements; check for integration-breaking changes (новости API).",
          {"from_date": {"type": "string", "description": "news since YYYY-MM-DD"}}),
]


# ─── Handler-функции для инструментов БЕЗ клиента WB ───────

async def _h_list_shops(a: dict) -> Any:
    from wb_mcp.settings import get_shop_list
    return get_shop_list(DATA_DIR)


async def _h_degradations(a: dict) -> Any:
    from wb_mcp import stats
    degraded = await stats.get_tool_degradations()
    if not degraded:
        return {"status": "ok", "message": "Деградаций нет — все инструменты работают штатно"}
    return {"status": "degraded", "tools": degraded,
            "hint": "Эти инструменты стабильно падают после периода успешной работы. Запусти wb_diagnostics и проверь wb_api_news — возможно, WB изменил API."}


NO_CLIENT_DISPATCH: dict[str, Any] = {
    "wb_list_shops": _h_list_shops,
    "wb_degradations": _h_degradations,
}


# ─── Handler-функции для инструментов С клиентом WB ────────
# Сигнатура: async (c: WBClient, a: dict) -> Any

# ── Карточки ──
async def _h_card_errors(c, a): return await c.card_errors_list()
async def _h_cards_list(c, a): return await c.cards_cursor_list(
    limit=a.get("limit", 100), cursor=a.get("cursor"), filter_params=a.get("filter"))
async def _h_card_detail(c, a): return await c.card_detail(a["nm_ids"])
async def _h_cards_update(c, a): return await c.cards_update(a["cards"])
async def _h_cards_move_to_trash(c, a): return await c.cards_move_to_trash(a["nm_ids"])
async def _h_cards_recover_from_trash(c, a): return await c.cards_recover_from_trash(a["nm_ids"])
async def _h_cards_limits(c, a): return await c.cards_limits()
async def _h_cards_create(c, a): return await c.cards_create(a["cards"])
async def _h_cards_trash(c, a): return await c.cards_trash_list(limit=a.get("limit", 100))
async def _h_barcodes_generate(c, a): return await c.barcodes_generate(a.get("count", 1))
async def _h_media_upload(c, a): return await c.media_save_by_links(a["nm_id"], a["links"])
async def _h_subjects_search(c, a): return await c.subjects_list(name=a.get("name"), limit=a.get("limit", 30))
async def _h_subject_charcs(c, a): return await c.subject_charcs(a["subject_id"])
async def _h_directory(c, a): return await c.directory_get(a["directory"], subject_id=a.get("subject_id"), search=a.get("search"))
async def _h_tags(c, a): return await c.tags_list()
async def _h_tag_link(c, a): return await c.tag_nomenclature_link(a["nm_id"], a["tag_ids"])
async def _h_tag_create(c, a): return await c.tag_create(a["name"], color=a.get("color", "#FF0000"))
async def _h_tag_update(c, a): return await c.tag_update(a["tag_id"], a["name"], a["color"])
async def _h_tag_delete(c, a): return await c.tag_delete(a["tag_id"])
async def _h_card_recommendations_get(c, a): return await c.card_recommendations_get(a["nm_id"])
async def _h_card_recommendations_set(c, a): return await c.card_recommendations_set(a["nm_id"], a["recommended_nm_ids"])
async def _h_brands_list(c, a): return await c.brands_list(subject_id=a.get("subject_id"))

# ── Цены ──
async def _h_prices_list(c, a): return await c.prices_list(
    limit=a.get("limit", 100), offset=a.get("offset", 0), filter_nm_id=a.get("filter_nm_id"))
async def _h_prices_set(c, a): return await c.prices_set(a["data"])
async def _h_prices_quarantine(c, a): return await c.prices_quarantine_list(
    limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_prices_club_discount(c, a): return await c.prices_club_discount_set(a["data"])
async def _h_prices_upload_status(c, a):
    if a.get("details"):
        return await c.prices_upload_details(a["upload_id"], buffer=a.get("buffer", False))
    return await c.prices_upload_status(a["upload_id"], buffer=a.get("buffer", False))
async def _h_prices_size_list(c, a): return await c.prices_size_list(a["nm_id"], limit=a.get("limit", 100))
async def _h_prices_b2b_set(c, a): return await c.prices_b2b_set(a["data"])

# ── Акции и автоакции ──
async def _h_promotions_list(c, a): return await c.promotions_list(
    a["start"], a["end"], all_promo=a.get("all_promo", False),
    limit=a.get("limit", 100), offset=a.get("offset", 0), promo_type=a.get("promo_type"))
async def _h_promotions_auto(c, a): return await c.promotions_auto(a["start"], a["end"])
async def _h_promotions_audit(c, a): return await c.promotions_audit(
    a["start"], a["end"], only_auto=a.get("only_auto", False), max_promotions=a.get("max_promotions", 25))
async def _h_promotions_details(c, a): return await c.promotions_details(a["promotion_ids"])
async def _h_promotions_products(c, a): return await c.promotions_nomenclatures(
    a["promotion_id"], in_action=a.get("in_action"), limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_promotions_add_products(c, a): return await c.promotions_upload(
    a["promotion_id"], a["nm_ids"], upload_now=a.get("upload_now", True))
async def _h_promotion_exit(c, a): return await c.promotions_exit(a["data"])

# ── Финансы ──
async def _h_finance_report(c, a): return await c.finance_realization_report(
    a["date_from"], a["date_to"], limit=a.get("limit", 500), rrd_id=a.get("rrd_id", 0))
async def _h_finance_reports_list(c, a): return await c.finance_sales_reports_list(
    a["date_from"], a["date_to"], period=a.get("period", "weekly"),
    limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_finance_report_detailed(c, a): return await c.finance_sales_report_by_id(
    a["report_id"], limit=a.get("limit", 500), rrd_id=a.get("rrd_id", 0))
async def _h_finance_acquiring_list(c, a): return await c.finance_acquiring_list(
    a["date_from"], a["date_to"], period=a.get("period", "weekly"),
    limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_finance_acquiring_detailed(c, a): return await c.finance_acquiring_detailed(
    a["date_from"], a["date_to"], limit=a.get("limit", 500), rrd_id=a.get("rrd_id", 0))

# ── Реклама ──
async def _h_advert_list(c, a): return await c.advert_list(
    ids=a.get("ids"), statuses=a.get("statuses"), payment_type=a.get("payment_type"))
async def _h_advert_count(c, a): return await c.advert_count()
async def _h_advert_create(c, a): return await c.advert_create(
    a["name"], a["nm_ids"], bid_type=a.get("bid_type", "unified"),
    payment_type=a.get("payment_type", "cpm"), placement_types=a.get("placement_types"))
async def _h_advert_stats(c, a): return await c.advert_statistics(a["advert_ids"], a["date_from"], a["date_to"])
async def _h_advert_balance(c, a): return await c.advert_balance()
async def _h_advert_budget(c, a): return await c.advert_budget(a["advert_id"])
async def _h_advert_deposit(c, a): return await c.advert_budget_deposit(a["advert_id"], a["amount"], source=a.get("source", 0))
async def _h_advert_costs(c, a): return await c.advert_costs_history(a["date_from"], a["date_to"])
async def _h_advert_pause(c, a): return await c.advert_pause(a["advert_id"])
async def _h_advert_start(c, a): return await c.advert_start(a["advert_id"])
async def _h_advert_stop(c, a): return await c.advert_stop(a["advert_id"])
async def _h_advert_delete(c, a): return await c.advert_delete(a["advert_id"])
async def _h_advert_bids_set(c, a): return await c.advert_bids_set(a["bids"])
async def _h_advert_bids_recommendations(c, a): return await c.advert_bids_recommendations(a["nm_id"], a["advert_id"])
async def _h_advert_clusters(c, a): return await c.advert_clusters_list(a["advert_id"])
async def _h_advert_clusters_stats(c, a): return await c.advert_clusters_stats(
    a["advert_id"], a["date_from"], a["date_to"], nm_ids=a.get("nm_ids"), daily=a.get("daily", False))
async def _h_advert_cluster_bids(c, a): return await c.advert_cluster_bids_set(a["bids"])
async def _h_advert_minus_phrases(c, a):
    if a.get("norm_queries") is not None:
        return await c.advert_minus_phrases_set(a["advert_id"], a["nm_id"], a["norm_queries"])
    return await c.advert_minus_phrases_get(a["advert_id"], nm_id=a.get("nm_id"))
async def _h_advert_payments(c, a): return await c.advert_payments(a["date_from"], a["date_to"])
async def _h_advert_rename(c, a): return await c.advert_rename(a["advert_id"], a["name"])
async def _h_advert_subjects(c, a): return await c.advert_subjects()
async def _h_advert_available_nms(c, a): return await c.advert_available_nms(a["subject_ids"])

# ── Контент: расширение ──
async def _h_cards_move_nm(c, a): return await c.cards_move_nm(a["nm_ids"], target_imt=a.get("target_imt"))
async def _h_card_add_nomenclature(c, a): return await c.card_add_nomenclature(a["imt_id"], a["cards_to_add"])
async def _h_categories_parent(c, a): return await c.categories_parent(locale=a.get("locale", "ru"))
async def _h_media_upload_file(c, a): return await c.media_upload_file(a["nm_id"], a["photo_number"], a["file_url"])

# ── FBS: маркировка, пропуска, короба ──
async def _h_order_meta_get(c, a): return await c.order_meta_get(a["order_id"])
async def _h_order_meta_set(c, a): return await c.order_meta_set(a["order_id"], a["meta_type"], a["value"])
async def _h_order_meta_delete(c, a): return await c.order_meta_delete(a["order_id"], a["key"])
async def _h_orders_status_history(c, a): return await c.orders_status_history(a["order_ids"])
async def _h_orders_client_info(c, a): return await c.orders_client_info(a["order_ids"])
async def _h_supplies_reshipment(c, a): return await c.supplies_reshipment()
async def _h_orders_external_stickers(c, a): return await c.orders_external_stickers(a["order_ids"])
async def _h_orders_archive(c, a): return await c.orders_archive(a["date_from"], date_to=a.get("date_to"), limit=a.get("limit", 100))
async def _h_supply_order_ids(c, a): return await c.supply_order_ids(a["supply_id"])
async def _h_passes_offices(c, a): return await c.passes_offices()
async def _h_passes_list(c, a): return await c.passes_list()
async def _h_pass_create(c, a): return await c.pass_create(
    a["first_name"], a["last_name"], a["car_model"], a["car_number"], a["office_id"])
async def _h_pass_update(c, a): return await c.pass_update(
    a["pass_id"], a["first_name"], a["last_name"], a["car_model"], a["car_number"], a["office_id"])
async def _h_pass_delete(c, a): return await c.pass_delete(a["pass_id"])
async def _h_supply_trbx_list(c, a): return await c.supply_trbx_list(a["supply_id"])
async def _h_supply_trbx_add(c, a): return await c.supply_trbx_add(a["supply_id"], a["amount"])
async def _h_supply_trbx_delete(c, a): return await c.supply_trbx_delete(a["supply_id"], a["trbx_ids"])
async def _h_supply_trbx_stickers(c, a): return await c.supply_trbx_stickers(
    a["supply_id"], a["trbx_ids"], sticker_type=a.get("sticker_type", "png"))

# ── DBS ──
async def _h_dbs_orders_new(c, a): return await c.dbs_orders_new()
async def _h_dbs_orders(c, a): return await c.dbs_orders(a.get("limit", 100), a.get("next", 0), a["date_from"], a["date_to"])
async def _h_dbs_orders_status(c, a): return await c.dbs_orders_status(a["order_ids"])
async def _h_dbs_orders_client(c, a): return await c.dbs_orders_client(a["order_ids"])
async def _h_dbs_orders_delivery_date(c, a): return await c.dbs_orders_delivery_date(a["order_ids"])
async def _h_dbs_groups_info(c, a): return await c.dbs_groups_info(a["group_ids"])
async def _h_dbs_order_action(c, a): return await c.dbs_order_action(a["order_id"], a["action"], code=a.get("code"))
async def _h_dbs_order_meta_get(c, a): return await c.dbs_order_meta_get(a["order_id"])
async def _h_dbs_order_meta_set(c, a): return await c.dbs_order_meta_set(a["order_id"], a["meta_type"], a["value"])
async def _h_dbs_order_meta_delete(c, a): return await c.dbs_order_meta_delete(a["order_id"], a["key"])

# ── Click-collect ──
async def _h_cc_orders_new(c, a): return await c.cc_orders_new()
async def _h_cc_orders(c, a): return await c.cc_orders(a.get("limit", 100), a.get("next", 0), a["date_from"], a["date_to"])
async def _h_cc_orders_status(c, a): return await c.cc_orders_status(a["order_ids"])
async def _h_cc_orders_client(c, a): return await c.cc_orders_client(a["order_ids"])
async def _h_cc_order_identity(c, a): return await c.cc_order_identity(a["order_code"], a["passcode"])
async def _h_cc_order_action(c, a): return await c.cc_order_action(a["order_id"], a["action"])
async def _h_cc_order_meta_get(c, a): return await c.cc_order_meta_get(a["order_id"])
async def _h_cc_order_meta_set(c, a): return await c.cc_order_meta_set(a["order_id"], a["meta_type"], a["value"])
async def _h_cc_order_meta_delete(c, a): return await c.cc_order_meta_delete(a["order_id"], a["key"])

# ── Аналитика: расширение ──
async def _h_analytics_brand_share(c, a): return await c.analytics_brand_share(
    a["parent_id"], a["brand"], a["date_from"], a["date_to"])
async def _h_analytics_brand_share_brands(c, a): return await c.analytics_brand_share_brands()
async def _h_analytics_brand_share_parents(c, a): return await c.analytics_brand_share_parents(
    a["brand"], a["date_from"], a["date_to"], locale=a.get("locale", "ru"))
async def _h_analytics_region_sale(c, a): return await c.analytics_region_sale(a["date_from"], a["date_to"])
async def _h_analytics_excise(c, a): return await c.analytics_excise_report(a["date_from"], a["date_to"])
async def _h_analytics_item_rating(c, a): return await c.analytics_item_rating(a["nm_ids"])
async def _h_analytics_grouped_history(c, a): return await c.analytics_sales_funnel_grouped_history(
    a["nm_ids"], a["date_from"], a["date_to"], aggregation_level=a.get("aggregation_level", "day"))
async def _h_nm_report(c, a): return await c.nm_report(
    nm_ids=a.get("nm_ids"), date_from=a.get("date_from"), date_to=a.get("date_to"))
async def _h_analytics_stocks_sizes(c, a): return await c.stocks_report_sizes(
    nm_ids=a.get("nm_ids"), date_from=a.get("date_from"), date_to=a.get("date_to"), limit=a.get("limit", 100))
async def _h_search_table_details(c, a): return await c.search_table_details(a["body"])
async def _h_search_table_groups(c, a): return await c.search_table_groups(a["body"])
async def _h_search_product_orders(c, a): return await c.search_product_orders(
    a["nm_id"], a["search_texts"], a["date_from"], a["date_to"])

# ── Отзывы/вопросы: расширение ──
async def _h_new_feedbacks_questions(c, a): return await c.new_feedbacks_questions()
async def _h_feedbacks_actions(c, a): return await c.feedbacks_actions(
    a["feedback_id"], feedback_valuation=a.get("feedback_valuation"), product_valuation=a.get("product_valuation"))
async def _h_feedbacks_archive(c, a): return await c.feedbacks_archive(take=a.get("take", 50), skip=a.get("skip", 0), nm_id=a.get("nm_id"))
async def _h_feedbacks_pins(c, a): return await c.feedbacks_pins_list()
async def _h_feedbacks_pins_count(c, a): return await c.feedbacks_pins_count()
async def _h_feedbacks_pins_set(c, a): return await c.feedbacks_pins_set(a["feedback_ids"])
async def _h_feedbacks_pins_delete(c, a): return await c.feedbacks_pins_delete(a["feedback_ids"])
async def _h_question_get(c, a): return await c.question_get(a["question_id"])
async def _h_feedback_order_return(c, a): return await c.feedback_order_return(a["feedback_id"])
async def _h_feedbacks_count_period(c, a): return await c.feedbacks_count_period(
    date_from=a.get("date_from"), date_to=a.get("date_to"), is_answered=a.get("is_answered"))
async def _h_questions_count_period(c, a): return await c.questions_count_period(
    date_from=a.get("date_from"), date_to=a.get("date_to"), is_answered=a.get("is_answered"))

# ── Джем ──
async def _h_jam_subscription(c, a): return await c.jam_subscription()

# ── Тарифы ──
async def _h_tariffs_box(c, a): return await c.tariffs_box(date=a.get("date"))
async def _h_tariffs_pallet(c, a): return await c.tariffs_pallet(date=a.get("date"))
async def _h_tariffs_return(c, a): return await c.tariffs_return(date=a.get("date"))
async def _h_tariffs_commission(c, a):
    """Комиссии по категориям. WB отдаёт весь справочник — 7 408 строк, 880 000
    токенов, в 35 раз больше потолка вывода клиента. Поэтому фильтр по названию
    категории применяется на сервере: без него инструмент нечитаем."""
    data = await c.tariffs_commission()
    query = (a.get("subject") or "").strip().lower()
    if not query:
        return data
    rows = data.get("report") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return data
    picked = [r for r in rows
              if query in str(r.get("subjectName", "")).lower()
              or query in str(r.get("parentName", "")).lower()]
    return {**data, "report": picked, "filteredBy": a["subject"], "totalCategories": len(rows)}
async def _h_fbw_transit_tariffs(c, a): return await c.fbw_transit_tariffs()

# ── Платное хранение ──
async def _h_paid_storage(c, a): return await c.analytics_paid_storage(a["date_from"], a["date_to"])

# ── Аналитика ──
async def _h_analytics_detail(c, a): return await c.analytics_sales_funnel(
    a["date_from"], a["date_to"], nm_ids=a.get("nm_ids"), brand_names=a.get("brand_names"), limit=a.get("limit", 100))
async def _h_analytics_history(c, a): return await c.analytics_sales_funnel_history(a["nm_ids"], a["date_from"], a["date_to"])
async def _h_analytics_stocks(c, a): return await c.analytics_stocks_report(
    a["date_from"], a["date_to"], nm_ids=a.get("nm_ids"), limit=a.get("limit", 100))
async def _h_warehouse_remains(c, a): return await c.analytics_warehouse_remains()
async def _h_analytics_antifraud(c, a): return await c.analytics_antifraud(a["date"])
async def _h_analytics_acceptance(c, a): return await c.analytics_acceptance_report(a["date_from"], a["date_to"])
async def _h_banned_products(c, a): return await c.analytics_banned_products(shadowed=a.get("shadowed", False))
async def _h_deductions(c, a): return await c.analytics_deductions(a["date_to"], a["date_from"], limit=a.get("limit", 100))
async def _h_search_report(c, a): return await c.search_report(
    a["date_from"], a["date_to"], nm_ids=a.get("nm_ids"), limit=a.get("limit", 30))
async def _h_search_texts(c, a): return await c.search_texts_by_product(
    a["nm_ids"], a["date_from"], a["date_to"], limit=a.get("limit", 30))

# ── Финансы и инфо ──
async def _h_finance_balance(c, a): return await c.finance_balance()
async def _h_seller_info(c, a): return await c.seller_info()
async def _h_seller_rating(c, a): return await c.seller_rating()

# ── Заказы ──
async def _h_orders_new(c, a): return await c.orders_new()
async def _h_orders_list(c, a): return await c.orders_list(a["date_from"], date_to=a.get("date_to"), limit=a.get("limit", 100))
async def _h_orders_status(c, a): return await c.orders_status(a["order_ids"])
async def _h_order_cancel(c, a): return await c.order_cancel(a["order_id"])
async def _h_orders_stickers(c, a): return await c.orders_stickers(
    a["order_ids"], sticker_type=a.get("sticker_type", "png"), width=a.get("width", 58), height=a.get("height", 40))
async def _h_supply_create(c, a): return await c.supply_create(a["name"])
async def _h_supply_detail(c, a): return await c.supply_detail(a["supply_id"])
async def _h_supply_add_orders(c, a): return await c.supply_add_orders(a["supply_id"], a["order_ids"])
async def _h_supply_deliver(c, a): return await c.supply_deliver(a["supply_id"])
async def _h_supply_barcode(c, a): return await c.supply_barcode(a["supply_id"], barcode_type=a.get("barcode_type", "png"))
async def _h_supply_delete(c, a): return await c.supply_delete(a["supply_id"])

# ── Статистика ──
async def _h_stats_sales(c, a): return await c.stats_sales(a["date_from"])
async def _h_stats_orders(c, a): return await c.stats_orders(a["date_from"], flag=a.get("flag", 0))
async def _h_stats_stocks(c, a): return await c.analytics_stocks_wb(nm_ids=a.get("nm_ids"), limit=a.get("limit", 100))

# ── Отзывы ──
async def _h_feedbacks_list(c, a): return await c.feedbacks_list(
    is_answered=a.get("is_answered"), nm_id=a.get("nm_id"), take=a.get("take", 50))
async def _h_feedbacks_count(c, a): return await c.feedbacks_count()
async def _h_feedback_reply(c, a): return await c.feedback_reply(a["feedback_id"], a["text"], edit=a.get("edit", False))
async def _h_questions_list(c, a): return await c.questions_list(
    is_answered=a.get("is_answered"), nm_id=a.get("nm_id"), take=a.get("take", 50))
async def _h_questions_count(c, a): return await c.questions_count()
async def _h_question_reply(c, a): return await c.question_reply(a["question_id"], a["text"], reject=a.get("reject", False))

# ── Возвраты ──
async def _h_returns_list(c, a): return await c.returns_claims(
    is_archive=a.get("is_archive", False), nm_id=a.get("nm_id"), limit=a.get("limit", 200))
async def _h_return_answer(c, a): return await c.returns_claim_answer(a["claim_id"], a["action"], comment=a.get("comment"))
async def _h_goods_return_report(c, a): return await c.analytics_goods_return(a["date_from"], a["date_to"])

# ── Склады ──
async def _h_warehouses(c, a): return await c.warehouses_list()
async def _h_warehouse_create(c, a): return await c.warehouse_create(a["name"], address=a.get("address"))
async def _h_warehouse_update(c, a): return await c.warehouse_update(a["warehouse_id"], name=a.get("name"), address=a.get("address"))
async def _h_warehouse_delete(c, a): return await c.warehouse_delete(a["warehouse_id"])
async def _h_supplies_list(c, a): return await c.supplies_list()
async def _h_stocks_update(c, a): return await c.stocks_update(a["warehouse_id"], a["stocks"])
async def _h_stocks_get(c, a): return await c.stocks_get(a["warehouse_id"], a["skus"])
async def _h_stocks_delete(c, a): return await c.stocks_delete(a["warehouse_id"], a["skus"])

# ── Поставки FBW ──
async def _h_fbw_supplies(c, a): return await c.fbw_supplies_list(
    limit=a.get("limit", 100), offset=a.get("offset", 0), status_ids=a.get("status_ids"))
async def _h_fbw_supply_detail(c, a): return await c.fbw_supply_detail(a["supply_id"])
async def _h_fbw_supply_goods(c, a): return await c.fbw_supply_goods(a["supply_id"], limit=a.get("limit", 100))
async def _h_fbw_acceptance_options(c, a): return await c.fbw_acceptance_options(a["items"], warehouse_id=a.get("warehouse_id"))
async def _h_fbw_warehouses(c, a): return await c.fbw_warehouses()
async def _h_acceptance_coefficients(c, a): return await c.acceptance_coefficients(warehouse_ids=a.get("warehouse_ids"))

# ── Обращения ──
async def _h_buyer_chats(c, a): return await c.buyer_chats_list()
async def _h_chat_events(c, a): return await c.buyer_chat_events(next_cursor=a.get("next_cursor"))
async def _h_chat_send(c, a): return await c.buyer_chat_send(a["reply_sign"], a["message"])
async def _h_chat_download(c, a): return await c.buyer_chat_download(a["file_id"])

# ── Документы ──
async def _h_documents_categories(c, a): return await c.documents_categories()
async def _h_documents_list(c, a): return await c.documents_list(
    date_from=a.get("date_from"), date_to=a.get("date_to"), category_id=a.get("category_id"), limit=a.get("limit", 100))
async def _h_document_download(c, a): return await c.document_download(a["document_id"])
async def _h_documents_download_bulk(c, a): return await c.documents_download_bulk(a["document_ids"])

# ── Пользователи ──
CLIENT_DISPATCH: dict[str, Any] = {
    # Карточки
    "wb_card_errors": _h_card_errors,
    "wb_cards_list": _h_cards_list,
    "wb_card_detail": _h_card_detail,
    "wb_cards_update": _h_cards_update,
    "wb_cards_move_to_trash": _h_cards_move_to_trash,
    "wb_cards_recover_from_trash": _h_cards_recover_from_trash,
    "wb_cards_limits": _h_cards_limits,
    "wb_cards_create": _h_cards_create,
    "wb_cards_trash": _h_cards_trash,
    "wb_barcodes_generate": _h_barcodes_generate,
    "wb_media_upload": _h_media_upload,
    "wb_subjects_search": _h_subjects_search,
    "wb_subject_charcs": _h_subject_charcs,
    "wb_directory": _h_directory,
    "wb_tags": _h_tags,
    "wb_tag_link": _h_tag_link,
    "wb_tag_create": _h_tag_create,
    "wb_tag_update": _h_tag_update,
    "wb_tag_delete": _h_tag_delete,
    "wb_card_recommendations_get": _h_card_recommendations_get,
    "wb_card_recommendations_set": _h_card_recommendations_set,
    "wb_brands_list": _h_brands_list,
    # Цены
    "wb_prices_list": _h_prices_list,
    "wb_prices_set": _h_prices_set,
    "wb_prices_quarantine": _h_prices_quarantine,
    "wb_prices_club_discount": _h_prices_club_discount,
    "wb_prices_upload_status": _h_prices_upload_status,
    "wb_prices_size_list": _h_prices_size_list,
    "wb_prices_b2b_set": _h_prices_b2b_set,
    # Акции
    "wb_promotions_list": _h_promotions_list,
    "wb_promotions_auto": _h_promotions_auto,
    "wb_promotions_audit": _h_promotions_audit,
    "wb_promotions_details": _h_promotions_details,
    "wb_promotions_products": _h_promotions_products,
    "wb_promotions_add_products": _h_promotions_add_products,
    "wb_promotion_exit": _h_promotion_exit,
    # Финансы
    "wb_finance_report": _h_finance_report,
    "wb_finance_reports_list": _h_finance_reports_list,
    "wb_finance_report_detailed": _h_finance_report_detailed,
    "wb_finance_acquiring_list": _h_finance_acquiring_list,
    "wb_finance_acquiring_detailed": _h_finance_acquiring_detailed,
    # Реклама
    "wb_advert_list": _h_advert_list,
    "wb_advert_count": _h_advert_count,
    "wb_advert_create": _h_advert_create,
    "wb_advert_stats": _h_advert_stats,
    "wb_advert_balance": _h_advert_balance,
    "wb_advert_budget": _h_advert_budget,
    "wb_advert_deposit": _h_advert_deposit,
    "wb_advert_costs": _h_advert_costs,
    "wb_advert_pause": _h_advert_pause,
    "wb_advert_start": _h_advert_start,
    "wb_advert_stop": _h_advert_stop,
    "wb_advert_delete": _h_advert_delete,
    "wb_advert_bids_set": _h_advert_bids_set,
    "wb_advert_bids_recommendations": _h_advert_bids_recommendations,
    "wb_advert_clusters": _h_advert_clusters,
    "wb_advert_clusters_stats": _h_advert_clusters_stats,
    "wb_advert_cluster_bids": _h_advert_cluster_bids,
    "wb_advert_minus_phrases": _h_advert_minus_phrases,
    "wb_advert_payments": _h_advert_payments,
    "wb_advert_rename": _h_advert_rename,
    "wb_advert_subjects": _h_advert_subjects,
    "wb_advert_available_nms": _h_advert_available_nms,
    # Контент: расширение
    "wb_cards_move_nm": _h_cards_move_nm,
    "wb_card_add_nomenclature": _h_card_add_nomenclature,
    "wb_categories_parent": _h_categories_parent,
    "wb_media_upload_file": _h_media_upload_file,
    # FBS
    "wb_order_meta_get": _h_order_meta_get,
    "wb_order_meta_set": _h_order_meta_set,
    "wb_order_meta_delete": _h_order_meta_delete,
    "wb_orders_status_history": _h_orders_status_history,
    "wb_orders_client_info": _h_orders_client_info,
    "wb_supplies_reshipment": _h_supplies_reshipment,
    "wb_orders_external_stickers": _h_orders_external_stickers,
    "wb_orders_archive": _h_orders_archive,
    "wb_supply_order_ids": _h_supply_order_ids,
    "wb_passes_offices": _h_passes_offices,
    "wb_passes_list": _h_passes_list,
    "wb_pass_create": _h_pass_create,
    "wb_pass_update": _h_pass_update,
    "wb_pass_delete": _h_pass_delete,
    "wb_supply_trbx_list": _h_supply_trbx_list,
    "wb_supply_trbx_add": _h_supply_trbx_add,
    "wb_supply_trbx_delete": _h_supply_trbx_delete,
    "wb_supply_trbx_stickers": _h_supply_trbx_stickers,
    # DBS
    "wb_dbs_orders_new": _h_dbs_orders_new,
    "wb_dbs_orders": _h_dbs_orders,
    "wb_dbs_orders_status": _h_dbs_orders_status,
    "wb_dbs_orders_client": _h_dbs_orders_client,
    "wb_dbs_orders_delivery_date": _h_dbs_orders_delivery_date,
    "wb_dbs_groups_info": _h_dbs_groups_info,
    "wb_dbs_order_action": _h_dbs_order_action,
    "wb_dbs_order_meta_get": _h_dbs_order_meta_get,
    "wb_dbs_order_meta_set": _h_dbs_order_meta_set,
    "wb_dbs_order_meta_delete": _h_dbs_order_meta_delete,
    # Click-collect
    "wb_cc_orders_new": _h_cc_orders_new,
    "wb_cc_orders": _h_cc_orders,
    "wb_cc_orders_status": _h_cc_orders_status,
    "wb_cc_orders_client": _h_cc_orders_client,
    "wb_cc_order_identity": _h_cc_order_identity,
    "wb_cc_order_action": _h_cc_order_action,
    "wb_cc_order_meta_get": _h_cc_order_meta_get,
    "wb_cc_order_meta_set": _h_cc_order_meta_set,
    "wb_cc_order_meta_delete": _h_cc_order_meta_delete,
    # Аналитика: расширение
    "wb_analytics_brand_share": _h_analytics_brand_share,
    "wb_analytics_brand_share_brands": _h_analytics_brand_share_brands,
    "wb_analytics_brand_share_parents": _h_analytics_brand_share_parents,
    "wb_analytics_region_sale": _h_analytics_region_sale,
    "wb_analytics_excise": _h_analytics_excise,
    "wb_analytics_item_rating": _h_analytics_item_rating,
    "wb_analytics_grouped_history": _h_analytics_grouped_history,
    "wb_nm_report": _h_nm_report,
    "wb_analytics_stocks_sizes": _h_analytics_stocks_sizes,
    "wb_search_table_details": _h_search_table_details,
    "wb_search_table_groups": _h_search_table_groups,
    "wb_search_product_orders": _h_search_product_orders,
    # Отзывы/вопросы: расширение
    "wb_new_feedbacks_questions": _h_new_feedbacks_questions,
    "wb_feedbacks_actions": _h_feedbacks_actions,
    "wb_feedbacks_archive": _h_feedbacks_archive,
    "wb_feedbacks_pins": _h_feedbacks_pins,
    "wb_feedbacks_pins_count": _h_feedbacks_pins_count,
    "wb_feedbacks_pins_set": _h_feedbacks_pins_set,
    "wb_feedbacks_pins_delete": _h_feedbacks_pins_delete,
    "wb_question_get": _h_question_get,
    "wb_feedback_order_return": _h_feedback_order_return,
    "wb_feedbacks_count_period": _h_feedbacks_count_period,
    "wb_questions_count_period": _h_questions_count_period,
    # Джем
    "wb_jam_subscription": _h_jam_subscription,
    # Тарифы
    "wb_tariffs_box": _h_tariffs_box,
    "wb_tariffs_pallet": _h_tariffs_pallet,
    "wb_tariffs_return": _h_tariffs_return,
    "wb_tariffs_commission": _h_tariffs_commission,
    "wb_fbw_transit_tariffs": _h_fbw_transit_tariffs,
    # Платное хранение
    "wb_paid_storage": _h_paid_storage,
    # Аналитика
    "wb_analytics_detail": _h_analytics_detail,
    "wb_analytics_history": _h_analytics_history,
    "wb_analytics_stocks": _h_analytics_stocks,
    "wb_warehouse_remains": _h_warehouse_remains,
    "wb_analytics_antifraud": _h_analytics_antifraud,
    "wb_analytics_acceptance": _h_analytics_acceptance,
    "wb_banned_products": _h_banned_products,
    "wb_deductions": _h_deductions,
    "wb_search_report": _h_search_report,
    "wb_search_texts": _h_search_texts,
    # Финансы и инфо
    "wb_finance_balance": _h_finance_balance,
    "wb_seller_info": _h_seller_info,
    "wb_seller_rating": _h_seller_rating,
    # Заказы
    "wb_orders_new": _h_orders_new,
    "wb_orders_list": _h_orders_list,
    "wb_orders_status": _h_orders_status,
    "wb_order_cancel": _h_order_cancel,
    "wb_orders_stickers": _h_orders_stickers,
    "wb_supply_create": _h_supply_create,
    "wb_supply_detail": _h_supply_detail,
    "wb_supply_add_orders": _h_supply_add_orders,
    "wb_supply_deliver": _h_supply_deliver,
    "wb_supply_barcode": _h_supply_barcode,
    "wb_supply_delete": _h_supply_delete,
    # Статистика
    "wb_stats_sales": _h_stats_sales,
    "wb_stats_orders": _h_stats_orders,
    "wb_stats_stocks": _h_stats_stocks,
    # Отзывы
    "wb_feedbacks_list": _h_feedbacks_list,
    "wb_feedbacks_count": _h_feedbacks_count,
    "wb_feedback_reply": _h_feedback_reply,
    "wb_questions_list": _h_questions_list,
    "wb_questions_count": _h_questions_count,
    "wb_question_reply": _h_question_reply,
    # Возвраты
    "wb_returns_list": _h_returns_list,
    "wb_return_answer": _h_return_answer,
    "wb_goods_return_report": _h_goods_return_report,
    # Склады
    "wb_warehouses": _h_warehouses,
    "wb_warehouse_create": _h_warehouse_create,
    "wb_warehouse_update": _h_warehouse_update,
    "wb_warehouse_delete": _h_warehouse_delete,
    "wb_supplies_list": _h_supplies_list,
    "wb_stocks_update": _h_stocks_update,
    "wb_stocks_get": _h_stocks_get,
    "wb_stocks_delete": _h_stocks_delete,
    # Поставки FBW
    "wb_fbw_supplies": _h_fbw_supplies,
    "wb_fbw_supply_detail": _h_fbw_supply_detail,
    "wb_fbw_supply_goods": _h_fbw_supply_goods,
    "wb_fbw_acceptance_options": _h_fbw_acceptance_options,
    "wb_fbw_warehouses": _h_fbw_warehouses,
    "wb_acceptance_coefficients": _h_acceptance_coefficients,
    # Обращения
    "wb_buyer_chats": _h_buyer_chats,
    "wb_chat_events": _h_chat_events,
    "wb_chat_send": _h_chat_send,
    "wb_chat_download": _h_chat_download,
    # Документы
    "wb_documents_categories": _h_documents_categories,
    "wb_documents_list": _h_documents_list,
    "wb_document_download": _h_document_download,
    "wb_documents_download_bulk": _h_documents_download_bulk,
    # Пользователи
}


# ─── Спец-handlers, требующие данных магазина (get_shop_keys) ──

async def _h_diagnostics(c, a, shop_id: str) -> Any:
    from wb_mcp import diagnostics as diag
    from wb_mcp.settings import get_shop_keys
    shop = get_shop_keys(DATA_DIR, shop_id)
    return await diag.full_diagnostics(shop_id, shop.get("name", shop_id), shop.get("wb_api_token", ""), c)


async def _h_token_info(c, a, shop_id: str) -> Any:
    from wb_mcp import diagnostics as diag
    from wb_mcp.settings import get_shop_keys
    shop = get_shop_keys(DATA_DIR, shop_id)
    return diag.decode_token(shop.get("wb_api_token", ""))


async def _h_api_news(c, a, shop_id: str) -> Any:
    from wb_mcp import diagnostics as diag
    from wb_mcp.settings import get_shop_keys
    shop = get_shop_keys(DATA_DIR, shop_id)
    return await diag.fetch_api_news(shop.get("wb_api_token", ""), from_date=a.get("from_date"))


# Handlers, которым кроме клиента нужен shop_id (для get_shop_keys)
SHOP_DISPATCH: dict[str, Any] = {
    "wb_diagnostics": _h_diagnostics,
    "wb_token_info": _h_token_info,
    "wb_api_news": _h_api_news,
}


# ─── Регистрация ──────────────────────────────────────────
#
# TODO(mcp 2.x): декораторного low-level API (@app.list_tools / @app.call_tool)
# в mcp>=2.0.0 больше нет — обработчики передаются в Server(...) как
# on_list_tools / on_call_tool и возвращают ListToolsResult / CallToolResult.
# Пока зависимость закреплена как mcp[cli]<2 (см. pyproject.toml); переход на 2.x
# — отдельная задача, вместе с миграцией с устаревшего SSE-транспорта на
# Streamable HTTP.

def _visible_tools() -> list[Tool]:
    """Инструменты для list_tools.

    При одном магазине shop_id убирается из схем: сервер подставит его сам
    (см. _call_tool_impl), а 200 повторов параметра стоят ~3400 токенов
    контекста в каждой сессии. Как только магазинов становится больше одного,
    параметр возвращается в схемы.
    """
    try:
        from wb_mcp.settings import load_shops
        if len(load_shops(DATA_DIR)) > 1:
            return TOOLS
    except Exception:
        return TOOLS

    visible: list[Tool] = []
    for t in TOOLS:
        props = t.inputSchema.get("properties") or {}
        if "shop_id" not in props:
            visible.append(t)
            continue
        schema = dict(t.inputSchema)
        schema["properties"] = {k: v for k, v in props.items() if k != "shop_id"}
        visible.append(Tool(name=t.name, description=t.description, inputSchema=schema))
    return visible


def _enabled_tools(tools: list[Tool]) -> list[Tool]:
    """Отсечь профили, выключенные через WB_TOOLSETS, и сказать об этом в описании.

    Инструмент, которого модель не видит, превращается в ответ «такой возможности
    нет». Поэтому список выключенного попадает в описание wb_list_shops — модель
    может назвать причину, а не выдумать ограничение.
    """
    note = toolsets.availability_note()
    if not note:
        return tools
    result = []
    for t in tools:
        if not toolsets.is_enabled(t.name):
            continue
        description = t.description + note if t.name == "wb_list_shops" else t.description
        result.append(Tool(name=t.name, description=description, inputSchema=t.inputSchema))
    return result


@app.list_tools()
async def list_tools() -> list[Tool]:
    return _enabled_tools(_visible_tools())


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    start = time.monotonic()
    success = True
    error_text = None
    shop_id = arguments.get("shop_id", "")
    try:
        result = await _call_tool_impl(name, arguments)
        return result
    except Exception as e:
        success = False
        error_text = f"{type(e).__name__}: {e}"
        return [TextContent(type="text", text=f"Ошибка: {error_text}")]
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        if _stats_callback:
            try:
                await _stats_callback(name, duration_ms, success, error_text, shop_id)
            except Exception:
                pass


async def _call_tool_impl(name: str, arguments: dict) -> list[TextContent]:
    # Профиль проверяется первым: иначе выключенный инструмент упрётся в ошибку
    # про магазин или токен, и причина отказа останется невидимой.
    if not toolsets.is_enabled(name):
        return [TextContent(type="text", text=toolsets.unavailable_message(name))]

    if name in NO_CLIENT_DISPATCH:
        return _shaped(name, arguments, await NO_CLIENT_DISPATCH[name](arguments))

    shop_id = arguments.get("shop_id", "")
    if not shop_id:
        from wb_mcp.settings import load_shops
        shops = load_shops(DATA_DIR)
        if len(shops) == 1:
            shop_id = next(iter(shops))
        else:
            return [TextContent(type="text", text=f"Укажите shop_id. Доступные: {list(shops.keys())}")]

    c = _get_client(shop_id)

    if name in CLIENT_DISPATCH:
        return _shaped(name, arguments, await CLIENT_DISPATCH[name](c, arguments))

    if name in SHOP_DISPATCH:
        return _shaped(name, arguments, await SHOP_DISPATCH[name](c, arguments, shop_id))

    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


# Инструментам с compact-пресетом добавляется переключатель view.
for _tool_with_view in TOOLS:
    if _tool_with_view.name in shaping.VIEWS:
        _tool_with_view.inputSchema.setdefault("properties", {})["view"] = dict(shaping.VIEW_PROP)


# ─── Точка входа ──────────────────────────────────────────

def main():
    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
