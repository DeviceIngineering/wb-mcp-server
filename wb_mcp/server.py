"""Wildberries MCP Server — инструменты для управления бизнесом на WB.

Разделы: Магазины, Товары, Цены, Заказы, Финансы, Реклама, Аналитика,
         Отзывы, Вопросы, Возвраты, Тарифы, Обращения.
Поддержка нескольких магазинов через параметр shop_id.

Приоритеты инструментов (по критичности для бизнеса):
  P0 — прямые финансовые потери (блокировки, убыточные цены/реклама)
  P1 — операционные метрики (заказы, продажи, остатки, отзывы)
  P2 — справочные данные (склады, лимиты, категории)
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

from wb_mcp.client import WBClient

# ─── Инициализация ────────────────────────────────────────

app = Server("wb-mcp-server")

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
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2, default=str))]


# Callback для записи статистики
_stats_callback: Callable[..., Awaitable[None]] | None = None


def set_stats_callback(cb: Callable[..., Awaitable[None]]):
    global _stats_callback
    _stats_callback = cb


# ─── Общий фрагмент shop_id для inputSchema ─────────────────

SHOP_ID_PROP = {"type": "string", "description": "ID магазина (из wb_list_shops)"}


def _tool(name: str, description: str, properties: dict | None = None, required: list | None = None) -> Tool:
    """Создать Tool с обязательным shop_id."""
    props = {"shop_id": SHOP_ID_PROP}
    if properties:
        props.update(properties)
    req = ["shop_id"]
    if required:
        req.extend(required)
    return Tool(name=name, description=description, inputSchema={"type": "object", "properties": props, "required": req})


# ─── Определение инструментов ─────────────────────────────

TOOLS = [
    # === МАГАЗИНЫ ===
    Tool(
        name="wb_list_shops",
        description="Список зарегистрированных магазинов Wildberries. Возвращает shop_id и название. Используй shop_id для всех остальных инструментов.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),

    # === P0: КАРТОЧКИ И БЛОКИРОВКИ ===
    _tool("wb_card_errors",
          "[P0] Карточки с ошибками — заблокированные и отклонённые. КРИТИЧНО: показывает карточки заблокированные по обращениям правообладателей! Проверяй регулярно чтобы не потерять продажи."),
    _tool("wb_cards_list",
          "[P1] Список карточек товаров (курсорная пагинация).",
          {"limit": {"type": "integer", "default": 100},
           "cursor": {"type": "object", "description": "Курсор пагинации (опц.)"},
           "filter": {"type": "object", "description": "Фильтр (опц.)"}}),
    _tool("wb_card_detail",
          "[P1] Подробная информация по карточкам (по nmID).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Список nmID товаров"}},
          ["nm_ids"]),
    _tool("wb_cards_update",
          "[P1] Обновить карточки (описание, SEO, характеристики). Используй для SEO-оптимизации против конкурентов.",
          {"cards": {"type": "array", "items": {"type": "object"}, "description": "Массив обновлённых карточек"}},
          ["cards"]),
    _tool("wb_cards_move_to_trash",
          "[P1] Переместить карточки в корзину (удаление). Принимает список nmID.",
          {"nm_ids": {"type": "array", "items": {"type": "number"}, "description": "Список nmID товаров для удаления"}},
          ["nm_ids"]),
    _tool("wb_cards_recover_from_trash",
          "[P1] Восстановить карточки из корзины. Принимает список nmID.",
          {"nm_ids": {"type": "array", "items": {"type": "number"}, "description": "Список nmID товаров для восстановления"}},
          ["nm_ids"]),
    _tool("wb_cards_limits",
          "[P2] Лимиты на создание/редактирование карточек."),
    _tool("wb_cards_create",
          "[P1] СОЗДАТЬ новые карточки товаров (асинхронно, синхронизация до 30 мин). Перед созданием получи характеристики предмета через wb_subject_charcs.",
          {"cards": {"type": "array", "items": {"type": "object"}, "description": "Массив: [{subjectID, variants: [{vendorCode, title, description, brand, dimensions, characteristics, sizes}]}]"}},
          ["cards"]),
    _tool("wb_cards_trash",
          "[P2] Список карточек в корзине.",
          {"limit": {"type": "integer", "default": 100}}),
    _tool("wb_barcodes_generate",
          "[P2] Сгенерировать баркоды для новых товаров.",
          {"count": {"type": "integer", "default": 1}}),
    _tool("wb_media_upload",
          "[P1] Загрузить фото/видео в карточку по ссылкам. ВНИМАНИЕ: полностью ЗАМЕНЯЕТ существующие медиа карточки!",
          {"nm_id": {"type": "integer"}, "links": {"type": "array", "items": {"type": "string"}, "description": "Ссылки на изображения (≥700x900px)"}},
          ["nm_id", "links"]),
    _tool("wb_subjects_search",
          "[P2] Поиск предметов (категорий) WB для создания карточек.",
          {"name": {"type": "string", "description": "Поиск по названию (опц.)"},
           "limit": {"type": "integer", "default": 30}}),
    _tool("wb_subject_charcs",
          "[P2] Характеристики предмета (обязательные/опциональные поля для карточки).",
          {"subject_id": {"type": "integer"}},
          ["subject_id"]),
    _tool("wb_directory",
          "[P2] Справочники WB: colors, kinds (пол), countries, seasons, vat, tnved.",
          {"directory": {"type": "string", "description": "colors | kinds | countries | seasons | vat | tnved"},
           "subject_id": {"type": "integer", "description": "Для tnved (опц.)"},
           "search": {"type": "string", "description": "Для tnved (опц.)"}},
          ["directory"]),
    _tool("wb_tags",
          "[P2] Список ярлыков (тегов) продавца для группировки карточек."),
    _tool("wb_tag_link",
          "[P2] Привязать/снять ярлыки с карточки (передаётся ПОЛНЫЙ новый список ярлыков карточки).",
          {"nm_id": {"type": "integer"}, "tag_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_id", "tag_ids"]),

    # === P0: ЦЕНЫ ===
    _tool("wb_prices_list",
          "[P0] Текущие цены и скидки на все товары. КРИТИЧНО: мониторинг для контроля маржинальности.",
          {"limit": {"type": "integer", "default": 1000},
           "offset": {"type": "integer", "default": 0},
           "filter_nm_id": {"type": "integer", "description": "Фильтр по конкретному nmID (опц.)"}}),
    _tool("wb_prices_set",
          "[P0] Установить/обновить цены и скидки. Каждый элемент: {nmID, price, discount}.",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "Массив: [{nmID, price, discount}, ...]"}},
          ["data"]),
    _tool("wb_prices_quarantine",
          "[P0] Товары в ценовом карантине — цена снижена слишком сильно (≥3x), новая цена НЕ применяется. Проверяй регулярно!",
          {"limit": {"type": "integer", "default": 1000}, "offset": {"type": "integer", "default": 0}}),
    _tool("wb_prices_club_discount",
          "[P1] Установить скидки WB Клуба (≤1000 товаров за запрос).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, clubDiscount}, ...]"}},
          ["data"]),
    _tool("wb_prices_upload_status",
          "[P1] Статус загрузки цен по uploadID (из wb_prices_set). buffer=true — для отложенных загрузок (скидки к будущей акции).",
          {"upload_id": {"type": "integer"}, "buffer": {"type": "boolean", "default": False},
           "details": {"type": "boolean", "default": False, "description": "true = детализация по товарам с ошибками"}},
          ["upload_id"]),
    _tool("wb_prices_size_list",
          "[P2] Цены по размерам конкретного товара.",
          {"nm_id": {"type": "integer"}, "limit": {"type": "integer", "default": 100}},
          ["nm_id"]),

    # === АКЦИИ И АВТОАКЦИИ (КАЛЕНДАРЬ ПРОМО) ===
    _tool("wb_promotions_list",
          "[P0] Список акций WB за период. type акции: 'auto' = АВТОАКЦИЯ (WB добавляет товары сам!), 'regular' = обычная. КРИТИЧНО: мониторь автоакции регулярно.",
          {"start": {"type": "string", "description": "RFC3339 (2026-06-01T00:00:00Z)"},
           "end": {"type": "string", "description": "RFC3339"},
           "all_promo": {"type": "boolean", "default": False, "description": "false = только доступные для участия, true = все"},
           "promo_type": {"type": "string", "enum": ["auto", "regular"], "description": "Фильтр по типу: auto | regular (опц.)"},
           "limit": {"type": "integer", "default": 1000, "description": "1–1000"},
           "offset": {"type": "integer", "default": 0}},
          ["start", "end"]),
    _tool("wb_promotions_auto",
          "[P0] ТОЛЬКО автоакции (type=auto) за период — WB добавляет товары автоматически. Используй для регулярного мониторинга, чтобы цены не упали без твоего ведома.",
          {"start": {"type": "string", "description": "RFC3339"},
           "end": {"type": "string", "description": "RFC3339"}},
          ["start", "end"]),
    _tool("wb_promotions_audit",
          "[P0] Аудит участия: в какие акции WB УЖЕ добавил мои товары и каков ценовой эффект (price→planPrice, % падения, скидка). ВАЖНО: для автоакций состав товаров WB через API не отдаёт (помечаются nomenclaturesAvailable=false) — контроль цен через wb_prices_list/wb_prices_quarantine. Авто-throttle под лимит 10 req/6 сек.",
          {"start": {"type": "string", "description": "RFC3339"},
           "end": {"type": "string", "description": "RFC3339"},
           "only_auto": {"type": "boolean", "default": False, "description": "true = только автоакции (состав недоступен); false = все акции"},
           "max_promotions": {"type": "integer", "default": 25, "description": "Сколько акций проверить (защита от лимита)"}},
          ["start", "end"]),
    _tool("wb_promotions_details",
          "[P1] Детали акций: даты, условия (ranging/boost), слоты участников, participationPercentage, бонусы (advantages), type.",
          {"promotion_ids": {"type": "array", "items": {"type": "integer"}}},
          ["promotion_ids"]),
    _tool("wb_promotions_products",
          "[P1] Товары, подходящие для акции. in_action: true = уже участвуют, false = не участвуют. Возвращает price/planPrice и discount/planDiscount.",
          {"promotion_id": {"type": "integer"},
           "in_action": {"type": "boolean", "description": "Фильтр участия (опц.)"},
           "limit": {"type": "integer", "default": 1000, "description": "1–1000"},
           "offset": {"type": "integer", "default": 0}},
          ["promotion_id"]),
    _tool("wb_promotions_add_products",
          "[P1] Добавить товары в акцию. upload_now=false — отложенно (применится при старте акции). Возвращает uploadID для отслеживания.",
          {"promotion_id": {"type": "integer"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}},
           "upload_now": {"type": "boolean", "default": True}},
          ["promotion_id", "nm_ids"]),
    _tool("wb_promotion_exit",
          "[P0] Выйти из акции/автоакции — восстановить цену и скидку (отдельного API выхода у WB нет, делается через Prices API).",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, price, discount}, ...] — доакционные значения"}},
          ["data"]),

    # === P0: ФИНАНСЫ И РЕАЛИЗАЦИЯ ===
    _tool("wb_finance_report",
          "[P0] Детальный отчёт по реализации за период (новый finance-api с fallback на старый эндпоинт). Содержит ВСЕ: комиссии, логистику, хранение, штрафы, к оплате. КРИТИЧНО: единственный способ увидеть реальную прибыль.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 100000}, "rrd_id": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),

    # === P0: РЕКЛАМА (ДРР) ===
    # С февраля 2026 WB перевёл рекламу на новую модель: кампании типа 9
    # (seacat), ставки manual/unified, кластеры вместо ключевых фраз.
    _tool("wb_advert_list",
          "[P0] Список рекламных кампаний с настройками и ставками. statuses: 9=активна, 11=пауза, 7=завершена, 4=готова, 8=отменена, -1=удалена.",
          {"ids": {"type": "array", "items": {"type": "integer"}, "description": "ID кампаний, ≤50 (опц.)"},
           "statuses": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по статусам (опц.)"},
           "payment_type": {"type": "string", "description": "cpm | cpc (опц.)"}}),
    _tool("wb_advert_create",
          "[P1] Создать рекламную кампанию (тип 9 «Поиск+Каталог» — единственный с 2026). bid_type: unified (единая ставка) | manual (ручная, с placement_types).",
          {"name": {"type": "string"}, "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Артикулы, ≤50"},
           "bid_type": {"type": "string", "default": "unified", "description": "unified | manual"},
           "payment_type": {"type": "string", "default": "cpm", "description": "cpm | cpc"},
           "placement_types": {"type": "array", "items": {"type": "string"}, "description": "Для manual: search, recommendations"}},
          ["name", "nm_ids"]),
    _tool("wb_advert_stats",
          "[P0] Полная статистика кампаний: расходы, показы, клики, CTR, CPC, заказы, выручка + дневная детализация в days[]. ЛИМИТ: 3 запроса/мин, период ≤31 дня! КРИТИЧНО: если расход/выручка > 20% — ДРР слишком высокий!",
          {"advert_ids": {"type": "array", "items": {"type": "integer"}, "description": "ID кампаний"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["advert_ids", "date_from", "date_to"]),
    _tool("wb_advert_balance",
          "[P1] Баланс рекламного кабинета (счёт, баланс, бонусы)."),
    _tool("wb_advert_budget",
          "[P1] Бюджет конкретной рекламной кампании.",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_deposit",
          "[P1] Пополнить бюджет кампании. source: 0=счёт, 1=баланс, 3=бонусы.",
          {"advert_id": {"type": "integer"}, "amount": {"type": "integer", "description": "Сумма в рублях"},
           "source": {"type": "integer", "default": 0}},
          ["advert_id", "amount"]),
    _tool("wb_advert_costs",
          "[P1] История затрат на рекламу за период.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_advert_pause",
          "[P0] Экстренная ОСТАНОВКА (пауза) рекламной кампании. Используй при ДРР > 20%.",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_start",
          "[P1] Запустить рекламную кампанию.",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_stop",
          "[P1] ЗАВЕРШИТЬ рекламную кампанию (окончательно, в отличие от паузы).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_delete",
          "[P2] Удалить рекламную кампанию (необратимо).",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_bids_set",
          "[P0] Изменить ставки CPM/CPC кампаний. Ставки в КОПЕЙКАХ. placement: search | recommendations | combined (combined — для unified-кампаний).",
          {"bids": {"type": "array", "items": {"type": "object"},
                    "description": "[{advert_id, nm_bids: [{nm_id, bid_kopecks, placement}]}]"}},
          ["bids"]),
    _tool("wb_advert_bids_recommendations",
          "[P1] Рекомендуемые ставки для карточки в кампании.",
          {"nm_id": {"type": "integer"}, "advert_id": {"type": "integer"}},
          ["nm_id", "advert_id"]),
    _tool("wb_advert_clusters",
          "[P0] Поисковые кластеры кампании (замена «ключевых фраз» с 2026). КРИТИЧНО: мониторинг поисковых запросов и SEO-позиций.",
          {"advert_id": {"type": "integer"}},
          ["advert_id"]),
    _tool("wb_advert_clusters_stats",
          "[P1] Статистика по поисковым кластерам кампании за период. daily=true — детализация по дням.",
          {"advert_id": {"type": "integer"}, "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр артикулов (опц.)"},
           "daily": {"type": "boolean", "default": False}},
          ["advert_id", "date_from", "date_to"]),
    _tool("wb_advert_cluster_bids",
          "[P1] Установить ставки на конкретные поисковые кластеры. Ставка в РУБЛЯХ за 1000 показов.",
          {"bids": {"type": "array", "items": {"type": "object"},
                    "description": "[{advert_id, nm_id, norm_query, bid}]"}},
          ["bids"]),
    _tool("wb_advert_minus_phrases",
          "[P1] Минус-фразы кампании: получить (без norm_queries) или установить (с norm_queries). Плюс-фраз в WB с 2026 нет.",
          {"advert_id": {"type": "integer"}, "nm_id": {"type": "integer", "description": "Артикул"},
           "norm_queries": {"type": "array", "items": {"type": "string"}, "description": "Установить минус-фразы (опц.; без него — чтение)"}},
          ["advert_id"]),
    _tool("wb_advert_payments",
          "[P1] История пополнений рекламного счёта за период (даты YYYY-MM-DD).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_advert_rename",
          "[P2] Переименовать рекламную кампанию.",
          {"advert_id": {"type": "integer"}, "name": {"type": "string"}},
          ["advert_id", "name"]),

    # === КОНТЕНT: расширение ===
    _tool("wb_cards_move_nm",
          "[P2] Объединить/разъединить карточки (≤30 nmID). target_imt задан = объединить в этот imtID; не задан = разъединить.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "target_imt": {"type": "integer", "description": "imtID для объединения (опц.; без него — разъединение)"}},
          ["nm_ids"]),
    _tool("wb_card_add_nomenclature",
          "[P2] Добавить номенклатуру/размер в существующую карточку (по imtID).",
          {"imt_id": {"type": "integer"},
           "cards_to_add": {"type": "array", "items": {"type": "object"}, "description": "Массив новых номенклатур"}},
          ["imt_id", "cards_to_add"]),
    _tool("wb_categories_parent",
          "[P2] Все родительские категории товаров.",
          {"locale": {"type": "string", "description": "ru | en | zh (по умолч. ru)"}}),
    _tool("wb_media_upload_file",
          "[P1] Загрузить медиа ФАЙЛОМ по ссылке (сервер скачает и отправит). photo_number с 1; видео = 1; новое фото — номер больше уже загруженных.",
          {"nm_id": {"type": "integer"}, "photo_number": {"type": "integer"},
           "file_url": {"type": "string", "description": "URL файла для скачивания"}},
          ["nm_id", "photo_number", "file_url"]),

    # === FBS: маркировка (КИЗ), пропуска, короба ===
    _tool("wb_order_meta_get",
          "[P1] Метаданные/маркировка заказа FBS (доступные ключи — из requiredMeta заказа).",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_order_meta_set",
          "[P0] Задать маркировку заказа FBS: meta_type = sgtin|uin|imei|gtin|expiration. Только в статусе confirm. КРИТИЧНО для маркированных товаров.",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin", "expiration"]},
           "value": {"description": "sgtin — массив Data Matrix; uin/imei/gtin — строка; expiration — dd.mm.yyyy"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_order_meta_delete",
          "[P2] Удалить метаданные заказа FBS по ключу (imei|uin|gtin|sgtin).",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}},
          ["order_id", "key"]),
    _tool("wb_orders_status_history",
          "[P2] История статусов заказов (трансграничные, ≤100).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_orders_client_info",
          "[P2] Данные покупателя (трансграничные заказы из Турции).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_supplies_reshipment",
          "[P1] Заказы, требующие повторной отгрузки (reshipment)."),
    _tool("wb_orders_external_stickers",
          "[P2] Стикеры трансграничной доставки (≤100, статус complete).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_passes_offices",
          "[P2] Офисы/склады, требующие пропуск."),
    _tool("wb_passes_list",
          "[P2] Список действующих пропусков на склад."),
    _tool("wb_pass_create",
          "[P2] Создать пропуск на склад (действует 48 ч).",
          {"first_name": {"type": "string"}, "last_name": {"type": "string"},
           "car_model": {"type": "string"}, "car_number": {"type": "string"}, "office_id": {"type": "integer"}},
          ["first_name", "last_name", "car_model", "car_number", "office_id"]),
    _tool("wb_pass_update",
          "[P2] Обновить пропуск.",
          {"pass_id": {"type": "integer"}, "first_name": {"type": "string"}, "last_name": {"type": "string"},
           "car_model": {"type": "string"}, "car_number": {"type": "string"}, "office_id": {"type": "integer"}},
          ["pass_id", "first_name", "last_name", "car_model", "car_number", "office_id"]),
    _tool("wb_pass_delete",
          "[P2] Удалить пропуск.",
          {"pass_id": {"type": "integer"}}, ["pass_id"]),
    _tool("wb_supply_trbx_list",
          "[P2] Короба (trbx) поставки FBS.",
          {"supply_id": {"type": "string"}}, ["supply_id"]),
    _tool("wb_supply_trbx_add",
          "[P2] Добавить короба в поставку (amount 1..1000, только ПВЗ при сборке).",
          {"supply_id": {"type": "string"}, "amount": {"type": "integer"}},
          ["supply_id", "amount"]),
    _tool("wb_supply_trbx_delete",
          "[P2] Удалить короба из поставки.",
          {"supply_id": {"type": "string"}, "trbx_ids": {"type": "array", "items": {"type": "string"}}},
          ["supply_id", "trbx_ids"]),
    _tool("wb_supply_trbx_stickers",
          "[P2] QR-стикеры коробов (svg|zplv|zplh|png).",
          {"supply_id": {"type": "string"}, "trbx_ids": {"type": "array", "items": {"type": "string"}},
           "sticker_type": {"type": "string", "enum": ["svg", "zplv", "zplh", "png"]}},
          ["supply_id", "trbx_ids"]),

    # === DBS: доставка силами продавца ===
    _tool("wb_dbs_orders_new", "[P1] Новые DBS-заказы (ожидают сборки)."),
    _tool("wb_dbs_orders",
          "[P1] Завершённые DBS-заказы (Unix-таймстампы, ≤30 дней, курсор next).",
          {"limit": {"type": "integer", "default": 100}, "next": {"type": "integer", "default": 0},
           "date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"}},
          ["date_from", "date_to"]),
    _tool("wb_dbs_orders_status",
          "[P1] Статусы DBS-заказов (≤1000).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_orders_client",
          "[P1] Данные покупателя DBS (после confirm).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_orders_delivery_date",
          "[P1] Выбранные покупателем дата/время доставки DBS (≤1000).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_dbs_groups_info",
          "[P2] Стоимость платной доставки по groupId (≤1000).",
          {"group_ids": {"type": "array", "items": {"type": "string"}}}, ["group_ids"]),
    _tool("wb_dbs_order_action",
          "[P0] Сменить статус DBS-заказа: action = confirm|deliver|receive|reject|cancel. receive/reject требуют code покупателя.",
          {"order_id": {"type": "integer"},
           "action": {"type": "string", "enum": ["confirm", "deliver", "receive", "reject", "cancel"]},
           "code": {"type": "string", "description": "Код подтверждения (для receive/reject)"}},
          ["order_id", "action"]),
    _tool("wb_dbs_order_meta_get",
          "[P2] Метаданные DBS-заказа.",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_dbs_order_meta_set",
          "[P1] Маркировка DBS-заказа: sgtin|uin|imei|gtin (статус confirm).",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin"]},
           "value": {"description": "sgtin — массив; остальное — строка"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_dbs_order_meta_delete",
          "[P2] Удалить метаданные DBS-заказа по ключу.",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}}, ["order_id", "key"]),

    # === CLICK-COLLECT: самовывоз ===
    _tool("wb_cc_orders_new", "[P1] Новые задания самовывоза."),
    _tool("wb_cc_orders",
          "[P1] Завершённые задания самовывоза (Unix-таймстампы, ≤30 дней).",
          {"limit": {"type": "integer", "default": 100}, "next": {"type": "integer", "default": 0},
           "date_from": {"type": "integer", "description": "Unix ts"}, "date_to": {"type": "integer"}},
          ["date_from", "date_to"]),
    _tool("wb_cc_orders_status",
          "[P1] Статусы заданий самовывоза.",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_cc_orders_client",
          "[P1] Данные покупателя (статусы confirm/prepare).",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}}, ["order_ids"]),
    _tool("wb_cc_order_identity",
          "[P0] Проверить код покупателя при выдаче самовывоза.",
          {"order_code": {"type": "string"}, "passcode": {"type": "string"}},
          ["order_code", "passcode"]),
    _tool("wb_cc_order_action",
          "[P0] Сменить статус задания самовывоза: action = confirm|prepare|receive|reject|cancel.",
          {"order_id": {"type": "integer"},
           "action": {"type": "string", "enum": ["confirm", "prepare", "receive", "reject", "cancel"]}},
          ["order_id", "action"]),
    _tool("wb_cc_order_meta_get",
          "[P2] Метаданные задания самовывоза.",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _tool("wb_cc_order_meta_set",
          "[P1] Маркировка задания самовывоза: sgtin|uin|imei|gtin (статус confirm).",
          {"order_id": {"type": "integer"},
           "meta_type": {"type": "string", "enum": ["sgtin", "uin", "imei", "gtin"]},
           "value": {"description": "sgtin — массив; остальное — строка"}},
          ["order_id", "meta_type", "value"]),
    _tool("wb_cc_order_meta_delete",
          "[P2] Удалить метаданные задания самовывоза по ключу.",
          {"order_id": {"type": "integer"}, "key": {"type": "string"}}, ["order_id", "key"]),

    # === АНАЛИТИКА: расширение ===
    _tool("wb_analytics_brand_share",
          "[P1] Доля бренда в категории (≤365 дней). Нужны parentId и brand из wb_analytics_brand_share_parents/brands.",
          {"parent_id": {"type": "integer"}, "brand": {"type": "string"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["parent_id", "brand", "date_from", "date_to"]),
    _tool("wb_analytics_brand_share_brands",
          "[P2] Бренды продавца (продавались за 90 дней) — для brand-share."),
    _tool("wb_analytics_brand_share_parents",
          "[P2] Родительские категории бренда — для brand-share.",
          {"brand": {"type": "string"}, "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "locale": {"type": "string", "description": "ru|en|zh"}},
          ["brand", "date_from", "date_to"]),
    _tool("wb_analytics_region_sale",
          "[P1] Продажи по регионам (≤31 дня, YYYY-MM-DD).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_goods_labeling",
          "[P1] Удержания за отсутствие обязательной маркировки (≤31 дня, с фото нарушений).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_search_table_details",
          "[P1] Поисковая аналитика по товарам (позиции/конверсии по запросам). ТРЕБУЕТ подписку Джем.",
          {"body": {"type": "object", "description": "{currentPeriod{start,end}, orderBy{field,mode}, positionCluster, limit, offset, ...}"}},
          ["body"]),
    _tool("wb_search_table_groups",
          "[P1] Поисковая аналитика по группам (предмет/бренд/тег). ТРЕБУЕТ подписку Джем.",
          {"body": {"type": "object", "description": "{currentPeriod{start,end}, orderBy, positionCluster, limit, offset, ...}"}},
          ["body"]),
    _tool("wb_search_product_orders",
          "[P1] Заказы и позиции по поисковым запросам для товара (≤7 дней). ТРЕБУЕТ подписку Джем.",
          {"nm_id": {"type": "integer"}, "search_texts": {"type": "array", "items": {"type": "string"}, "description": "1..30 запросов"},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["nm_id", "search_texts", "date_from", "date_to"]),

    # === ОТЗЫВЫ/ВОПРОСЫ: расширение ===
    _tool("wb_new_feedbacks_questions",
          "[P1] Флаги непросмотренных отзывов/вопросов (hasNewFeedbacks/hasNewQuestions) — для регулярного мониторинга."),
    _tool("wb_feedbacks_actions",
          "[P2] Жалоба на отзыв / сообщить о проблеме товара (коды из supplier-valuations).",
          {"feedback_id": {"type": "string"},
           "feedback_valuation": {"type": "integer", "description": "Причина жалобы на отзыв (опц.)"},
           "product_valuation": {"type": "integer", "description": "Проблема товара (опц.)"}},
          ["feedback_id"]),
    _tool("wb_question_get",
          "[P2] Один вопрос покупателя по ID.",
          {"question_id": {"type": "string"}}, ["question_id"]),
    _tool("wb_feedback_order_return",
          "[P1] Запросить возврат товара по отзыву (только если isAbleReturnProductOrders=true).",
          {"feedback_id": {"type": "string"}}, ["feedback_id"]),
    _tool("wb_feedbacks_count_period",
          "[P2] Число отзывов за период (Unix ts, фильтр isAnswered). Отличие от wb_feedbacks_count (неотвеченные).",
          {"date_from": {"type": "integer", "description": "Unix ts (опц.)"}, "date_to": {"type": "integer"},
           "is_answered": {"type": "boolean"}}),
    _tool("wb_questions_count_period",
          "[P2] Число вопросов за период (Unix ts, фильтр isAnswered). Отличие от wb_questions_count (неотвеченные).",
          {"date_from": {"type": "integer", "description": "Unix ts (опц.)"}, "date_to": {"type": "integer"},
           "is_answered": {"type": "boolean"}}),

    # === РЕКЛАМА: расширение ===
    _tool("wb_advert_subjects",
          "[P2] Предметы, доступные для рекламных кампаний."),
    _tool("wb_advert_available_nms",
          "[P2] Товары (nm), доступные для кампаний, по ID предметов.",
          {"subject_ids": {"type": "array", "items": {"type": "integer"}}}, ["subject_ids"]),

    # === P0: ТАРИФЫ ЛОГИСТИКИ И ХРАНЕНИЯ ===
    _tool("wb_tariffs_box",
          "[P0] Тарифы на логистику коробов (FBO). КРИТИЧНО: рост тарифов = рост расходов = торговля в минус!",
          {"date": {"type": "string", "description": "Дата YYYY-MM-DD (опц., по умолчанию сегодня)"}}),
    _tool("wb_tariffs_pallet",
          "[P1] Тарифы на логистику палет (FBO).",
          {"date": {"type": "string", "description": "Дата YYYY-MM-DD (опц.)"}}),
    _tool("wb_tariffs_return",
          "[P0] Тарифы на обратную логистику (возвраты). КРИТИЧНО: скрытые расходы при высоком проценте возвратов.",
          {"date": {"type": "string", "description": "Дата YYYY-MM-DD (опц.)"}}),
    _tool("wb_tariffs_commission",
          "[P0] Комиссии WB по категориям (FBO, FBS, DBS). Для расчёта unit-экономики."),

    # === P0: ПЛАТНОЕ ХРАНЕНИЕ ===
    _tool("wb_paid_storage",
          "[P0] Отчёт по платному хранению на складах WB. КРИТИЧНО: товары с нулевыми продажами и высокой стоимостью хранения = прямые убытки!",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P1: АНАЛИТИКА ===
    _tool("wb_analytics_detail",
          "[P1] Воронка продаж по товарам: просмотры, клики, корзина, заказы, выручка, конверсии (+ сравнение с прошлым периодом). Падение конверсий = проблема SEO или конкурент обошёл. ЛИМИТ 3/мин.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Список nmID (опц.)"},
           "brand_names": {"type": "array", "items": {"type": "string"}, "description": "Бренды (опц.)"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_history",
          "[P1] Воронка продаж по ДНЯМ (максимум последняя неделя). Для трендов конверсии.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["nm_ids", "date_from", "date_to"]),
    _tool("wb_analytics_stocks",
          "[P1] Интерактивный отчёт по остаткам и оборачиваемости (актуальные, дефицитные, неликвидные товары).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "limit": {"type": "integer", "default": 100}},
          ["date_from", "date_to"]),
    _tool("wb_warehouse_remains",
          "[P1] Отчёт об остатках на складах WB с разбивкой по складам (task-based, ~10-60 сек)."),
    _tool("wb_analytics_antifraud",
          "[P1] Удержания за самовыкупы (отчёт публикуется по средам).",
          {"date": {"type": "string", "description": "YYYY-MM-DD"}},
          ["date"]),
    _tool("wb_analytics_acceptance",
          "[P1] Отчёт по платной приёмке на складах WB (task-based, ~10-60 сек).",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_banned_products",
          "[P0] Заблокированные (blocked) или скрытые из каталога (shadowed) карточки. КРИТИЧНО: это потерянные продажи — проверяй регулярно!",
          {"shadowed": {"type": "boolean", "default": False, "description": "true = скрытые, false = заблокированные"}}),
    _tool("wb_deductions",
          "[P1] Удержания за подмены и неверные вложения.",
          {"date_to": {"type": "string", "description": "YYYY-MM-DD"},
           "date_from": {"type": "string", "description": "(опц.)"},
           "limit": {"type": "integer", "default": 100}},
          ["date_to"]),
    _tool("wb_search_report",
          "[P0] Отчёт по поисковым запросам: показы, клики, позиции в поиске (подписка Джем). КРИТИЧНО: видимость в поиске = продажи. ЛИМИТ 3/мин.",
          {"date_from": {"type": "string"}, "date_to": {"type": "string"},
           "nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "limit": {"type": "integer", "default": 30}},
          ["date_from", "date_to"]),
    _tool("wb_search_texts",
          "[P1] Топ поисковых запросов по конкретным товарам (≤30 на тарифе без Джема).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 30}},
          ["nm_ids", "date_from", "date_to"]),

    # === ФИНАНСЫ И ИНФО ===
    _tool("wb_finance_balance",
          "[P0] Баланс продавца (к выводу, в пути и т.д.). Требует категорию «Финансы» в токене."),
    _tool("wb_seller_info",
          "[P2] Информация о продавце: название, ID профиля. Работает с любым токеном."),

    # === P1: ЗАКАЗЫ ===
    _tool("wb_orders_new",
          "[P1] Новые заказы FBS — ожидают сборки."),
    _tool("wb_orders_list",
          "[P1] Все заказы за период.",
          {"date_from": {"type": "string", "description": "RFC3339 (2024-01-01T00:00:00Z)"},
           "date_to": {"type": "string", "description": "RFC3339 (опц.)"},
           "limit": {"type": "integer", "default": 1000}},
          ["date_from"]),
    _tool("wb_orders_status",
          "[P1] Статусы конкретных заказов.",
          {"order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["order_ids"]),
    _tool("wb_order_cancel",
          "[P1] ОТМЕНИТЬ сборочное задание FBS (необратимо).",
          {"order_id": {"type": "integer"}},
          ["order_id"]),
    _tool("wb_orders_stickers",
          "[P1] Стикеры для сборочных заданий FBS (≤100 за запрос). Форматы: svg, zplv, zplh, png.",
          {"order_ids": {"type": "array", "items": {"type": "integer"}},
           "sticker_type": {"type": "string", "default": "png"},
           "width": {"type": "integer", "default": 58}, "height": {"type": "integer", "default": 40}},
          ["order_ids"]),
    _tool("wb_supply_create",
          "[P1] Создать поставку FBS (для отгрузки собранных заказов).",
          {"name": {"type": "string"}},
          ["name"]),
    _tool("wb_supply_detail",
          "[P2] Информация о поставке FBS.",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),
    _tool("wb_supply_add_orders",
          "[P1] Добавить сборочные задания в поставку FBS (≤100, статус заданий → confirm).",
          {"supply_id": {"type": "string"}, "order_ids": {"type": "array", "items": {"type": "integer"}}},
          ["supply_id", "order_ids"]),
    _tool("wb_supply_deliver",
          "[P1] Закрыть поставку FBS и передать в доставку (статусы заданий → complete).",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),
    _tool("wb_supply_barcode",
          "[P2] QR-код поставки FBS для отгрузки на склад.",
          {"supply_id": {"type": "string"}, "barcode_type": {"type": "string", "default": "png"}},
          ["supply_id"]),
    _tool("wb_supply_delete",
          "[P2] Удалить пустую активную поставку FBS.",
          {"supply_id": {"type": "string"}},
          ["supply_id"]),

    # === P1: ПРОДАЖИ И ОСТАТКИ (СТАТИСТИКА) ===
    _tool("wb_stats_sales",
          "[P1] Продажи за период. КРИТИЧНО: мониторинг для выявления товаров, прекративших продаваться.",
          {"date_from": {"type": "string", "description": "RFC3339"}},
          ["date_from"]),
    _tool("wb_stats_orders",
          "[P1] Заказы (статистика) — включая отмены. Для анализа отмен и возвратов.",
          {"date_from": {"type": "string"}, "flag": {"type": "integer", "default": 0, "description": "1 = только обновлённые"}},
          ["date_from"]),
    _tool("wb_stats_stocks",
          "[P0] Текущие остатки на ВСЕХ складах WB (обновление раз в 30 мин, лимит 3/мин). КРИТИЧНО: товары с остатками но без продаж = переплата за хранение."),

    # === P1: ОТЗЫВЫ И ВОПРОСЫ ===
    _tool("wb_feedbacks_list",
          "[P1] Список отзывов. Негативные отзывы без ответа снижают рейтинг и конверсию.",
          {"is_answered": {"type": "boolean", "description": "Фильтр: true=отвеченные, false=неотвеченные (опц.)"},
           "nm_id": {"type": "integer", "description": "Фильтр по nmID товара (опц.)"},
           "take": {"type": "integer", "default": 50}}),
    _tool("wb_feedbacks_count",
          "[P1] Количество неотвеченных отзывов."),
    _tool("wb_feedback_reply",
          "[P1] Ответить на отзыв (edit=true — отредактировать существующий ответ).",
          {"feedback_id": {"type": "string"}, "text": {"type": "string"},
           "edit": {"type": "boolean", "default": False}},
          ["feedback_id", "text"]),
    _tool("wb_seller_rating",
          "[P1] Рейтинг продавца (общий рейтинг магазина)."),
    _tool("wb_questions_list",
          "[P1] Список вопросов от покупателей.",
          {"is_answered": {"type": "boolean", "description": "Фильтр (опц.)"},
           "nm_id": {"type": "integer", "description": "Фильтр по nmID (опц.)"},
           "take": {"type": "integer", "default": 50}}),
    _tool("wb_questions_count",
          "[P1] Количество неотвеченных вопросов."),
    _tool("wb_question_reply",
          "[P1] Ответить на вопрос покупателя (reject=true — отклонить вопрос).",
          {"question_id": {"type": "string"}, "text": {"type": "string"},
           "reject": {"type": "boolean", "default": False}},
          ["question_id", "text"]),

    # === P1: ВОЗВРАТЫ ===
    _tool("wb_returns_list",
          "[P1] Заявки покупателей на возврат. is_archive=false — на рассмотрении (ТРЕБУЮТ ответа!), true — архив. В ответе actions[] — допустимые действия по каждой заявке. Массовые возвраты = проблема качества или карточки.",
          {"is_archive": {"type": "boolean", "default": False},
           "nm_id": {"type": "integer", "description": "Фильтр по товару (опц.)"},
           "limit": {"type": "integer", "default": 200}}),
    _tool("wb_return_answer",
          "[P1] Ответить на заявку возврата. action строго из actions[] заявки: approve1 (проверка брака на складе WB), approve2 (забрать товар себе), autorefund1 (вернуть деньги без возврата товара), reject1/reject2/reject3 (шаблоны отказа WB), rejectcustom (свой комментарий — обязателен comment).",
          {"claim_id": {"type": "string"}, "action": {"type": "string"},
           "comment": {"type": "string", "description": "Для rejectcustom (опц.)"}},
          ["claim_id", "action"]),
    _tool("wb_goods_return_report",
          "[P2] Аналитический отчёт по возвратам товаров продавцу (макс. 31 день).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),

    # === P2: СКЛАДЫ И ПОСТАВКИ ===
    _tool("wb_warehouses",
          "[P2] Список складов продавца."),
    _tool("wb_supplies_list",
          "[P2] Список поставок."),
    _tool("wb_stocks_update",
          "[P2] Обновить остатки на складе FBS. ВНИМАНИЕ: имена полей не валидируются — опечатка даст 204 без обновления!",
          {"warehouse_id": {"type": "integer"}, "stocks": {"type": "array", "items": {"type": "object"}, "description": "[{sku, amount}, ...]"}},
          ["warehouse_id", "stocks"]),
    _tool("wb_stocks_get",
          "[P2] Получить остатки на складе FBS по баркодам.",
          {"warehouse_id": {"type": "integer"}, "skus": {"type": "array", "items": {"type": "string"}}},
          ["warehouse_id", "skus"]),

    # === ПОСТАВКИ FBW (НА СКЛАДЫ WB) ===
    _tool("wb_fbw_supplies",
          "[P1] Список поставок FBW на склады WB (информационно; создание поставки — только в ЛК).",
          {"limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0},
           "status_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по статусам (опц.)"}}),
    _tool("wb_fbw_supply_detail",
          "[P2] Детали поставки FBW.",
          {"supply_id": {"type": "integer"}},
          ["supply_id"]),
    _tool("wb_fbw_supply_goods",
          "[P2] Товары в поставке FBW.",
          {"supply_id": {"type": "integer"}, "limit": {"type": "integer", "default": 1000}},
          ["supply_id"]),
    _tool("wb_fbw_acceptance_options",
          "[P1] Доступные склады и типы упаковки для поставки FBW по баркодам.",
          {"items": {"type": "array", "items": {"type": "object"}, "description": "[{barcode, quantity}, ...]"},
           "warehouse_id": {"type": "integer", "description": "Конкретный склад (опц.)"}},
          ["items"]),
    _tool("wb_fbw_warehouses",
          "[P2] Список складов WB для поставок FBW."),
    _tool("wb_acceptance_coefficients",
          "[P0] Коэффициенты приёмки складов WB на 14 дней. Приёмка доступна при coefficient 0 или 1 и allowUnload=true. КРИТИЧНО для планирования поставок: коэффициент x2-x7 = кратная переплата за приёмку!",
          {"warehouse_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр складов (опц.)"}}),

    # === P2: ОБРАЩЕНИЯ ПОКУПАТЕЛЕЙ ===
    _tool("wb_buyer_chats",
          "[P1] Чаты с покупателями (содержит replySign для ответа). Может содержать жалобы и обращения правообладателей."),
    _tool("wb_chat_events",
          "[P1] События чатов (новые сообщения). Курсорная пагинация: первый вызов без next, далее next из ответа.",
          {"next_cursor": {"type": "integer", "description": "Курсор из предыдущего ответа (опц.)"}}),
    _tool("wb_chat_send",
          "[P1] Отправить сообщение покупателю в чат (≤1000 символов). reply_sign — из wb_buyer_chats.",
          {"reply_sign": {"type": "string"}, "message": {"type": "string"}},
          ["reply_sign", "message"]),

    # === P1: ДОКУМЕНТЫ ===
    _tool("wb_documents_categories",
          "[P2] Категории документов (типы: акты сверки, УПД, счета-фактуры и т.д.)."),
    _tool("wb_documents_list",
          "[P1] Список финансовых документов продавца (акты, УПД, уведомления). КРИТИЧНО: необходимо для бухгалтерии и контроля финансов.",
          {"date_from": {"type": "string", "description": "Дата начала (опц.)"},
           "date_to": {"type": "string", "description": "Дата конца (опц.)"},
           "category_id": {"type": "integer", "description": "ID категории из wb_documents_categories (опц.)"},
           "limit": {"type": "integer", "default": 100}}),
    _tool("wb_document_download",
          "[P1] Скачать конкретный документ (PDF/XML) по его ID.",
          {"document_id": {"type": "string", "description": "ID документа из wb_documents_list"}},
          ["document_id"]),

    # === ДИАГНОСТИКА ===
    _tool("wb_diagnostics",
          "[P0] ПОЛНАЯ САМОДИАГНОСТИКА: ping всех хостов WB API + лёгкие реальные запросы по каждой категории + анализ токена (срок действия, права). Используй ПЕРВЫМ ДЕЛОМ если какой-то инструмент не работает — покажет, проблема в токене, в конкретной категории API или в изменении API со стороны WB."),
    _tool("wb_token_info",
          "[P1] Информация о токене магазина: категории доступа, срок действия, read-only/sandbox. Быстрая проверка без запросов к WB."),
    Tool(
        name="wb_degradations",
        description="[P0] Деградации инструментов: какие MCP-инструменты раньше работали, а теперь стабильно падают (сигнал изменения WB API). Без параметров.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    _tool("wb_api_news",
          "[P1] Новости WB для продавцов (включая анонсы изменений API). Используй для проверки, не анонсировал ли WB изменения, ломающие интеграцию.",
          {"from_date": {"type": "string", "description": "Новости с даты YYYY-MM-DD (опц.)"}}),
]


# ─── Регистрация ──────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


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
    # Магазины (без shop_id)
    if name == "wb_list_shops":
        from wb_mcp.settings import get_shop_list
        return _json(get_shop_list(DATA_DIR))

    # Деградации (без shop_id)
    if name == "wb_degradations":
        from wb_mcp import stats
        degraded = await stats.get_tool_degradations()
        if not degraded:
            return _json({"status": "ok", "message": "Деградаций нет — все инструменты работают штатно"})
        return _json({"status": "degraded", "tools": degraded,
                      "hint": "Эти инструменты стабильно падают после периода успешной работы. Запусти wb_diagnostics и проверь wb_api_news — возможно, WB изменил API."})

    shop_id = arguments.get("shop_id", "")
    if not shop_id:
        from wb_mcp.settings import load_shops
        shops = load_shops(DATA_DIR)
        if len(shops) == 1:
            shop_id = next(iter(shops))
        else:
            return [TextContent(type="text", text=f"Укажите shop_id. Доступные магазины: {list(shops.keys())}")]

    c = _get_client(shop_id)

    # ── Карточки ──────────────────────────────────────────
    if name == "wb_card_errors":
        return _json(await c.card_errors_list())
    if name == "wb_cards_list":
        return _json(await c.cards_cursor_list(
            limit=arguments.get("limit", 100),
            cursor=arguments.get("cursor"),
            filter_params=arguments.get("filter"),
        ))
    if name == "wb_card_detail":
        return _json(await c.card_detail(arguments["nm_ids"]))
    if name == "wb_cards_update":
        return _json(await c.cards_update(arguments["cards"]))
    if name == "wb_cards_move_to_trash":
        return _json(await c.cards_move_to_trash(arguments["nm_ids"]))
    if name == "wb_cards_recover_from_trash":
        return _json(await c.cards_recover_from_trash(arguments["nm_ids"]))
    if name == "wb_cards_limits":
        return _json(await c.cards_limits())
    if name == "wb_cards_create":
        return _json(await c.cards_create(arguments["cards"]))
    if name == "wb_cards_trash":
        return _json(await c.cards_trash_list(limit=arguments.get("limit", 100)))
    if name == "wb_barcodes_generate":
        return _json(await c.barcodes_generate(arguments.get("count", 1)))
    if name == "wb_media_upload":
        return _json(await c.media_save_by_links(arguments["nm_id"], arguments["links"]))
    if name == "wb_subjects_search":
        return _json(await c.subjects_list(name=arguments.get("name"), limit=arguments.get("limit", 30)))
    if name == "wb_subject_charcs":
        return _json(await c.subject_charcs(arguments["subject_id"]))
    if name == "wb_directory":
        return _json(await c.directory_get(arguments["directory"],
                                           subject_id=arguments.get("subject_id"),
                                           search=arguments.get("search")))
    if name == "wb_tags":
        return _json(await c.tags_list())
    if name == "wb_tag_link":
        return _json(await c.tag_nomenclature_link(arguments["nm_id"], arguments["tag_ids"]))

    # ── Цены ──────────────────────────────────────────────
    if name == "wb_prices_list":
        return _json(await c.prices_list(
            limit=arguments.get("limit", 1000),
            offset=arguments.get("offset", 0),
            filter_nm_id=arguments.get("filter_nm_id"),
        ))
    if name == "wb_prices_set":
        return _json(await c.prices_set(arguments["data"]))
    if name == "wb_prices_quarantine":
        return _json(await c.prices_quarantine_list(
            limit=arguments.get("limit", 1000),
            offset=arguments.get("offset", 0),
        ))
    if name == "wb_prices_club_discount":
        return _json(await c.prices_club_discount_set(arguments["data"]))
    if name == "wb_prices_upload_status":
        if arguments.get("details"):
            return _json(await c.prices_upload_details(arguments["upload_id"], buffer=arguments.get("buffer", False)))
        return _json(await c.prices_upload_status(arguments["upload_id"], buffer=arguments.get("buffer", False)))
    if name == "wb_prices_size_list":
        return _json(await c.prices_size_list(arguments["nm_id"], limit=arguments.get("limit", 100)))

    # ── Акции и автоакции (календарь промо) ───────────────
    if name == "wb_promotions_list":
        return _json(await c.promotions_list(
            arguments["start"], arguments["end"],
            all_promo=arguments.get("all_promo", False),
            limit=arguments.get("limit", 1000),
            offset=arguments.get("offset", 0),
            promo_type=arguments.get("promo_type"),
        ))
    if name == "wb_promotions_auto":
        return _json(await c.promotions_auto(arguments["start"], arguments["end"]))
    if name == "wb_promotions_audit":
        return _json(await c.promotions_audit(
            arguments["start"], arguments["end"],
            only_auto=arguments.get("only_auto", False),
            max_promotions=arguments.get("max_promotions", 25),
        ))
    if name == "wb_promotions_details":
        return _json(await c.promotions_details(arguments["promotion_ids"]))
    if name == "wb_promotions_products":
        return _json(await c.promotions_nomenclatures(
            arguments["promotion_id"],
            in_action=arguments.get("in_action"),
            limit=arguments.get("limit", 1000),
            offset=arguments.get("offset", 0),
        ))
    if name == "wb_promotions_add_products":
        return _json(await c.promotions_upload(
            arguments["promotion_id"], arguments["nm_ids"],
            upload_now=arguments.get("upload_now", True),
        ))
    if name == "wb_promotion_exit":
        return _json(await c.promotions_exit(arguments["data"]))

    # ── Финансы ───────────────────────────────────────────
    if name == "wb_finance_report":
        return _json(await c.finance_realization_report(
            arguments["date_from"], arguments["date_to"],
            limit=arguments.get("limit", 100000),
            rrd_id=arguments.get("rrd_id", 0),
        ))

    # ── Реклама ───────────────────────────────────────────
    if name == "wb_advert_list":
        return _json(await c.advert_list(
            ids=arguments.get("ids"),
            statuses=arguments.get("statuses"),
            payment_type=arguments.get("payment_type"),
        ))
    if name == "wb_advert_create":
        return _json(await c.advert_create(
            arguments["name"], arguments["nm_ids"],
            bid_type=arguments.get("bid_type", "unified"),
            payment_type=arguments.get("payment_type", "cpm"),
            placement_types=arguments.get("placement_types"),
        ))
    if name == "wb_advert_stats":
        return _json(await c.advert_statistics(
            arguments["advert_ids"], arguments["date_from"], arguments["date_to"],
        ))
    if name == "wb_advert_balance":
        return _json(await c.advert_balance())
    if name == "wb_advert_budget":
        return _json(await c.advert_budget(arguments["advert_id"]))
    if name == "wb_advert_deposit":
        return _json(await c.advert_budget_deposit(
            arguments["advert_id"], arguments["amount"], source=arguments.get("source", 0),
        ))
    if name == "wb_advert_costs":
        return _json(await c.advert_costs_history(arguments["date_from"], arguments["date_to"]))
    if name == "wb_advert_pause":
        return _json(await c.advert_pause(arguments["advert_id"]))
    if name == "wb_advert_start":
        return _json(await c.advert_start(arguments["advert_id"]))
    if name == "wb_advert_stop":
        return _json(await c.advert_stop(arguments["advert_id"]))
    if name == "wb_advert_delete":
        return _json(await c.advert_delete(arguments["advert_id"]))
    if name == "wb_advert_bids_set":
        return _json(await c.advert_bids_set(arguments["bids"]))
    if name == "wb_advert_bids_recommendations":
        return _json(await c.advert_bids_recommendations(arguments["nm_id"], arguments["advert_id"]))
    if name == "wb_advert_clusters":
        return _json(await c.advert_clusters_list(arguments["advert_id"]))
    if name == "wb_advert_clusters_stats":
        return _json(await c.advert_clusters_stats(
            arguments["advert_id"], arguments["date_from"], arguments["date_to"],
            nm_ids=arguments.get("nm_ids"), daily=arguments.get("daily", False),
        ))
    if name == "wb_advert_cluster_bids":
        return _json(await c.advert_cluster_bids_set(arguments["bids"]))
    if name == "wb_advert_minus_phrases":
        if arguments.get("norm_queries") is not None:
            return _json(await c.advert_minus_phrases_set(
                arguments["advert_id"], arguments["nm_id"], arguments["norm_queries"],
            ))
        return _json(await c.advert_minus_phrases_get(arguments["advert_id"], nm_id=arguments.get("nm_id")))
    if name == "wb_advert_payments":
        return _json(await c.advert_payments(arguments["date_from"], arguments["date_to"]))
    if name == "wb_advert_rename":
        return _json(await c.advert_rename(arguments["advert_id"], arguments["name"]))
    if name == "wb_advert_subjects":
        return _json(await c.advert_subjects())
    if name == "wb_advert_available_nms":
        return _json(await c.advert_available_nms(arguments["subject_ids"]))

    # ── Контент: расширение ───────────────────────────────
    if name == "wb_cards_move_nm":
        return _json(await c.cards_move_nm(arguments["nm_ids"], target_imt=arguments.get("target_imt")))
    if name == "wb_card_add_nomenclature":
        return _json(await c.card_add_nomenclature(arguments["imt_id"], arguments["cards_to_add"]))
    if name == "wb_categories_parent":
        return _json(await c.categories_parent(locale=arguments.get("locale", "ru")))
    if name == "wb_media_upload_file":
        return _json(await c.media_upload_file(arguments["nm_id"], arguments["photo_number"], arguments["file_url"]))

    # ── FBS: маркировка, пропуска, короба ─────────────────
    if name == "wb_order_meta_get":
        return _json(await c.order_meta_get(arguments["order_id"]))
    if name == "wb_order_meta_set":
        return _json(await c.order_meta_set(arguments["order_id"], arguments["meta_type"], arguments["value"]))
    if name == "wb_order_meta_delete":
        return _json(await c.order_meta_delete(arguments["order_id"], arguments["key"]))
    if name == "wb_orders_status_history":
        return _json(await c.orders_status_history(arguments["order_ids"]))
    if name == "wb_orders_client_info":
        return _json(await c.orders_client_info(arguments["order_ids"]))
    if name == "wb_supplies_reshipment":
        return _json(await c.supplies_reshipment())
    if name == "wb_orders_external_stickers":
        return _json(await c.orders_external_stickers(arguments["order_ids"]))
    if name == "wb_passes_offices":
        return _json(await c.passes_offices())
    if name == "wb_passes_list":
        return _json(await c.passes_list())
    if name == "wb_pass_create":
        return _json(await c.pass_create(arguments["first_name"], arguments["last_name"],
                                         arguments["car_model"], arguments["car_number"], arguments["office_id"]))
    if name == "wb_pass_update":
        return _json(await c.pass_update(arguments["pass_id"], arguments["first_name"], arguments["last_name"],
                                         arguments["car_model"], arguments["car_number"], arguments["office_id"]))
    if name == "wb_pass_delete":
        return _json(await c.pass_delete(arguments["pass_id"]))
    if name == "wb_supply_trbx_list":
        return _json(await c.supply_trbx_list(arguments["supply_id"]))
    if name == "wb_supply_trbx_add":
        return _json(await c.supply_trbx_add(arguments["supply_id"], arguments["amount"]))
    if name == "wb_supply_trbx_delete":
        return _json(await c.supply_trbx_delete(arguments["supply_id"], arguments["trbx_ids"]))
    if name == "wb_supply_trbx_stickers":
        return _json(await c.supply_trbx_stickers(arguments["supply_id"], arguments["trbx_ids"],
                                                  sticker_type=arguments.get("sticker_type", "png")))

    # ── DBS: доставка силами продавца ─────────────────────
    if name == "wb_dbs_orders_new":
        return _json(await c.dbs_orders_new())
    if name == "wb_dbs_orders":
        return _json(await c.dbs_orders(arguments.get("limit", 100), arguments.get("next", 0),
                                        arguments["date_from"], arguments["date_to"]))
    if name == "wb_dbs_orders_status":
        return _json(await c.dbs_orders_status(arguments["order_ids"]))
    if name == "wb_dbs_orders_client":
        return _json(await c.dbs_orders_client(arguments["order_ids"]))
    if name == "wb_dbs_orders_delivery_date":
        return _json(await c.dbs_orders_delivery_date(arguments["order_ids"]))
    if name == "wb_dbs_groups_info":
        return _json(await c.dbs_groups_info(arguments["group_ids"]))
    if name == "wb_dbs_order_action":
        return _json(await c.dbs_order_action(arguments["order_id"], arguments["action"], code=arguments.get("code")))
    if name == "wb_dbs_order_meta_get":
        return _json(await c.dbs_order_meta_get(arguments["order_id"]))
    if name == "wb_dbs_order_meta_set":
        return _json(await c.dbs_order_meta_set(arguments["order_id"], arguments["meta_type"], arguments["value"]))
    if name == "wb_dbs_order_meta_delete":
        return _json(await c.dbs_order_meta_delete(arguments["order_id"], arguments["key"]))

    # ── Click-collect: самовывоз ──────────────────────────
    if name == "wb_cc_orders_new":
        return _json(await c.cc_orders_new())
    if name == "wb_cc_orders":
        return _json(await c.cc_orders(arguments.get("limit", 100), arguments.get("next", 0),
                                       arguments["date_from"], arguments["date_to"]))
    if name == "wb_cc_orders_status":
        return _json(await c.cc_orders_status(arguments["order_ids"]))
    if name == "wb_cc_orders_client":
        return _json(await c.cc_orders_client(arguments["order_ids"]))
    if name == "wb_cc_order_identity":
        return _json(await c.cc_order_identity(arguments["order_code"], arguments["passcode"]))
    if name == "wb_cc_order_action":
        return _json(await c.cc_order_action(arguments["order_id"], arguments["action"]))
    if name == "wb_cc_order_meta_get":
        return _json(await c.cc_order_meta_get(arguments["order_id"]))
    if name == "wb_cc_order_meta_set":
        return _json(await c.cc_order_meta_set(arguments["order_id"], arguments["meta_type"], arguments["value"]))
    if name == "wb_cc_order_meta_delete":
        return _json(await c.cc_order_meta_delete(arguments["order_id"], arguments["key"]))

    # ── Аналитика: расширение ─────────────────────────────
    if name == "wb_analytics_brand_share":
        return _json(await c.analytics_brand_share(arguments["parent_id"], arguments["brand"],
                                                   arguments["date_from"], arguments["date_to"]))
    if name == "wb_analytics_brand_share_brands":
        return _json(await c.analytics_brand_share_brands())
    if name == "wb_analytics_brand_share_parents":
        return _json(await c.analytics_brand_share_parents(arguments["brand"], arguments["date_from"],
                                                           arguments["date_to"], locale=arguments.get("locale", "ru")))
    if name == "wb_analytics_region_sale":
        return _json(await c.analytics_region_sale(arguments["date_from"], arguments["date_to"]))
    if name == "wb_analytics_goods_labeling":
        return _json(await c.analytics_goods_labeling(arguments["date_from"], arguments["date_to"]))
    if name == "wb_search_table_details":
        return _json(await c.search_table_details(arguments["body"]))
    if name == "wb_search_table_groups":
        return _json(await c.search_table_groups(arguments["body"]))
    if name == "wb_search_product_orders":
        return _json(await c.search_product_orders(arguments["nm_id"], arguments["search_texts"],
                                                   arguments["date_from"], arguments["date_to"]))

    # ── Отзывы/вопросы: расширение ────────────────────────
    if name == "wb_new_feedbacks_questions":
        return _json(await c.new_feedbacks_questions())
    if name == "wb_feedbacks_actions":
        return _json(await c.feedbacks_actions(arguments["feedback_id"],
                                               feedback_valuation=arguments.get("feedback_valuation"),
                                               product_valuation=arguments.get("product_valuation")))
    if name == "wb_question_get":
        return _json(await c.question_get(arguments["question_id"]))
    if name == "wb_feedback_order_return":
        return _json(await c.feedback_order_return(arguments["feedback_id"]))
    if name == "wb_feedbacks_count_period":
        return _json(await c.feedbacks_count_period(date_from=arguments.get("date_from"),
                                                    date_to=arguments.get("date_to"),
                                                    is_answered=arguments.get("is_answered")))
    if name == "wb_questions_count_period":
        return _json(await c.questions_count_period(date_from=arguments.get("date_from"),
                                                    date_to=arguments.get("date_to"),
                                                    is_answered=arguments.get("is_answered")))

    # ── Тарифы ────────────────────────────────────────────
    if name == "wb_tariffs_box":
        return _json(await c.tariffs_box(date=arguments.get("date")))
    if name == "wb_tariffs_pallet":
        return _json(await c.tariffs_pallet(date=arguments.get("date")))
    if name == "wb_tariffs_return":
        return _json(await c.tariffs_return(date=arguments.get("date")))
    if name == "wb_tariffs_commission":
        return _json(await c.tariffs_commission())

    # ── Платное хранение ──────────────────────────────────
    if name == "wb_paid_storage":
        return _json(await c.analytics_paid_storage(arguments["date_from"], arguments["date_to"]))

    # ── Аналитика ─────────────────────────────────────────
    if name == "wb_analytics_detail":
        return _json(await c.analytics_sales_funnel(
            arguments["date_from"], arguments["date_to"],
            nm_ids=arguments.get("nm_ids"),
            brand_names=arguments.get("brand_names"),
            limit=arguments.get("limit", 100),
        ))
    if name == "wb_analytics_history":
        return _json(await c.analytics_sales_funnel_history(
            arguments["nm_ids"], arguments["date_from"], arguments["date_to"],
        ))
    if name == "wb_analytics_stocks":
        return _json(await c.analytics_stocks_report(
            arguments["date_from"], arguments["date_to"],
            nm_ids=arguments.get("nm_ids"), limit=arguments.get("limit", 100),
        ))
    if name == "wb_warehouse_remains":
        return _json(await c.analytics_warehouse_remains())
    if name == "wb_analytics_antifraud":
        return _json(await c.analytics_antifraud(arguments["date"]))
    if name == "wb_analytics_acceptance":
        return _json(await c.analytics_acceptance_report(arguments["date_from"], arguments["date_to"]))
    if name == "wb_banned_products":
        return _json(await c.analytics_banned_products(shadowed=arguments.get("shadowed", False)))
    if name == "wb_deductions":
        return _json(await c.analytics_deductions(
            arguments["date_to"], date_from=arguments.get("date_from"),
            limit=arguments.get("limit", 100),
        ))
    if name == "wb_search_report":
        return _json(await c.search_report(
            arguments["date_from"], arguments["date_to"],
            nm_ids=arguments.get("nm_ids"), limit=arguments.get("limit", 30),
        ))
    if name == "wb_search_texts":
        return _json(await c.search_texts_by_product(
            arguments["nm_ids"], arguments["date_from"], arguments["date_to"],
            limit=arguments.get("limit", 30),
        ))

    # ── Финансы и инфо ────────────────────────────────────
    if name == "wb_finance_balance":
        return _json(await c.finance_balance())
    if name == "wb_seller_info":
        return _json(await c.seller_info())
    if name == "wb_seller_rating":
        return _json(await c.seller_rating())

    # ── Заказы ────────────────────────────────────────────
    if name == "wb_orders_new":
        return _json(await c.orders_new())
    if name == "wb_orders_list":
        return _json(await c.orders_list(
            arguments["date_from"],
            date_to=arguments.get("date_to"),
            limit=arguments.get("limit", 1000),
        ))
    if name == "wb_orders_status":
        return _json(await c.orders_status(arguments["order_ids"]))
    if name == "wb_order_cancel":
        return _json(await c.order_cancel(arguments["order_id"]))
    if name == "wb_orders_stickers":
        return _json(await c.orders_stickers(
            arguments["order_ids"],
            sticker_type=arguments.get("sticker_type", "png"),
            width=arguments.get("width", 58), height=arguments.get("height", 40),
        ))
    if name == "wb_supply_create":
        return _json(await c.supply_create(arguments["name"]))
    if name == "wb_supply_detail":
        return _json(await c.supply_detail(arguments["supply_id"]))
    if name == "wb_supply_add_orders":
        return _json(await c.supply_add_orders(arguments["supply_id"], arguments["order_ids"]))
    if name == "wb_supply_deliver":
        return _json(await c.supply_deliver(arguments["supply_id"]))
    if name == "wb_supply_barcode":
        return _json(await c.supply_barcode(arguments["supply_id"], barcode_type=arguments.get("barcode_type", "png")))
    if name == "wb_supply_delete":
        return _json(await c.supply_delete(arguments["supply_id"]))

    # ── Статистика ────────────────────────────────────────
    if name == "wb_stats_sales":
        return _json(await c.stats_sales(arguments["date_from"]))
    if name == "wb_stats_orders":
        return _json(await c.stats_orders(arguments["date_from"], flag=arguments.get("flag", 0)))
    if name == "wb_stats_stocks":
        return _json(await c.stats_stocks())

    # ── Отзывы ────────────────────────────────────────────
    if name == "wb_feedbacks_list":
        return _json(await c.feedbacks_list(
            is_answered=arguments.get("is_answered"),
            nm_id=arguments.get("nm_id"),
            take=arguments.get("take", 50),
        ))
    if name == "wb_feedbacks_count":
        return _json(await c.feedbacks_count())
    if name == "wb_feedback_reply":
        return _json(await c.feedback_reply(
            arguments["feedback_id"], arguments["text"],
            edit=arguments.get("edit", False),
        ))
    if name == "wb_questions_list":
        return _json(await c.questions_list(
            is_answered=arguments.get("is_answered"),
            nm_id=arguments.get("nm_id"),
            take=arguments.get("take", 50),
        ))
    if name == "wb_questions_count":
        return _json(await c.questions_count())
    if name == "wb_question_reply":
        return _json(await c.question_reply(
            arguments["question_id"], arguments["text"],
            reject=arguments.get("reject", False),
        ))

    # ── Возвраты ──────────────────────────────────────────
    if name == "wb_returns_list":
        return _json(await c.returns_claims(
            is_archive=arguments.get("is_archive", False),
            nm_id=arguments.get("nm_id"),
            limit=arguments.get("limit", 200),
        ))
    if name == "wb_return_answer":
        return _json(await c.returns_claim_answer(
            arguments["claim_id"], arguments["action"],
            comment=arguments.get("comment"),
        ))
    if name == "wb_goods_return_report":
        return _json(await c.analytics_goods_return(arguments["date_from"], arguments["date_to"]))

    # ── Склады ────────────────────────────────────────────
    if name == "wb_warehouses":
        return _json(await c.warehouses_list())
    if name == "wb_supplies_list":
        return _json(await c.supplies_list())
    if name == "wb_stocks_update":
        return _json(await c.stocks_update(arguments["warehouse_id"], arguments["stocks"]))
    if name == "wb_stocks_get":
        return _json(await c.stocks_get(arguments["warehouse_id"], arguments["skus"]))

    # ── Поставки FBW ──────────────────────────────────────
    if name == "wb_fbw_supplies":
        return _json(await c.fbw_supplies_list(
            limit=arguments.get("limit", 100), offset=arguments.get("offset", 0),
            status_ids=arguments.get("status_ids"),
        ))
    if name == "wb_fbw_supply_detail":
        return _json(await c.fbw_supply_detail(arguments["supply_id"]))
    if name == "wb_fbw_supply_goods":
        return _json(await c.fbw_supply_goods(arguments["supply_id"], limit=arguments.get("limit", 1000)))
    if name == "wb_fbw_acceptance_options":
        return _json(await c.fbw_acceptance_options(arguments["items"], warehouse_id=arguments.get("warehouse_id")))
    if name == "wb_fbw_warehouses":
        return _json(await c.fbw_warehouses())
    if name == "wb_acceptance_coefficients":
        return _json(await c.acceptance_coefficients(warehouse_ids=arguments.get("warehouse_ids")))

    # ── Обращения ─────────────────────────────────────────
    if name == "wb_buyer_chats":
        return _json(await c.buyer_chats_list())
    if name == "wb_chat_events":
        return _json(await c.buyer_chat_events(next_cursor=arguments.get("next_cursor")))
    if name == "wb_chat_send":
        return _json(await c.buyer_chat_send(arguments["reply_sign"], arguments["message"]))

    # ── Диагностика ───────────────────────────────────────
    if name == "wb_diagnostics":
        from wb_mcp import diagnostics as diag
        from wb_mcp.settings import get_shop_keys, load_shops
        shop = get_shop_keys(DATA_DIR, shop_id)
        result = await diag.full_diagnostics(
            shop_id, shop.get("name", shop_id), shop.get("wb_api_token", ""), c,
        )
        return _json(result)
    if name == "wb_token_info":
        from wb_mcp import diagnostics as diag
        from wb_mcp.settings import get_shop_keys
        shop = get_shop_keys(DATA_DIR, shop_id)
        return _json(diag.decode_token(shop.get("wb_api_token", "")))
    if name == "wb_api_news":
        from wb_mcp import diagnostics as diag
        from wb_mcp.settings import get_shop_keys
        shop = get_shop_keys(DATA_DIR, shop_id)
        return _json(await diag.fetch_api_news(
            shop.get("wb_api_token", ""), from_date=arguments.get("from_date"),
        ))

    # ── Документы ─────────────────────────────────────────
    if name == "wb_documents_categories":
        return _json(await c.documents_categories())
    if name == "wb_documents_list":
        return _json(await c.documents_list(
            date_from=arguments.get("date_from"),
            date_to=arguments.get("date_to"),
            category_id=arguments.get("category_id"),
            limit=arguments.get("limit", 100),
        ))
    if name == "wb_document_download":
        return _json(await c.document_download(arguments["document_id"]))

    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


# ─── Точка входа ──────────────────────────────────────────

def main():
    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
