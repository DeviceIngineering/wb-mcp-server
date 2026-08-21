"""Wildberries MCP Server — инструменты для управления бизнесом на WB.

Разделы: Магазины, Товары, Цены, Заказы, Финансы, Реклама, Аналитика,
         Отзывы, Вопросы, Возвраты, Тарифы, Обращения.
Поддержка нескольких магазинов через параметр shop_id.

Приоритеты инструментов (по критичности для бизнеса):
  P0 — прямые финансовые потери (блокировки, убыточные цены/реклама)
  P1 — операционные метрики (заказы, продажи, остатки, отзывы)
  P2 — справочные данные (склады, лимиты, категории)
  P3 — администрирование (пользователи, доступы)

v2.2.0 — диспетчеризация инструментов через словари NO_CLIENT_DISPATCH /
         CLIENT_DISPATCH вместо if/elif цепочки + 39 новых инструментов.
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

app = Server("wb-mcp-server", version="2.2.0")

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
    _tool("wb_tag_create",
          "[P2] Создать ярлык (тег) для группировки карточек. color: HEX-цвет.",
          {"name": {"type": "string"}, "color": {"type": "string", "default": "#FF0000"}},
          ["name"]),
    _tool("wb_tag_update",
          "[P2] Обновить ярлык (название, цвет).",
          {"tag_id": {"type": "integer"}, "name": {"type": "string"}, "color": {"type": "string"}},
          ["tag_id", "name", "color"]),
    _tool("wb_tag_delete",
          "[P2] Удалить ярлык. ВНИМАНИЕ: ошибка если тег привязан к товарам — сначала открепи через wb_tag_link.",
          {"tag_id": {"type": "integer"}},
          ["tag_id"]),
    _tool("wb_card_recommendations_get",
          "[P2] Рекомендованные товары к карточке (перекрёстные продажи).",
          {"nm_id": {"type": "integer"}},
          ["nm_id"]),
    _tool("wb_card_recommendations_set",
          "[P2] Установить рекомендованные товары к карточке (≤10 nmID). Используй для увеличения среднего чека.",
          {"nm_id": {"type": "integer"}, "recommended_nm_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_id", "recommended_nm_ids"]),
    _tool("wb_brands_list",
          "[P2] Список брендов продавца. subject_id для фильтрации по категории.",
          {"subject_id": {"type": "integer", "description": "Фильтр по категории (опц.)"}}),

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
    _tool("wb_prices_b2b_set",
          "[P2] Установить оптовые B2B скидки. Каждый элемент: {nmID, wholesaleDiscount}.",
          {"data": {"type": "array", "items": {"type": "object"}, "description": "[{nmID, wholesaleDiscount}, ...]"}},
          ["data"]),

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
          "[P0] Детальный отчёт по реализации за период (новый finance-api с fallback на старый эндпоинт). Содержит ВСЕ: комиссии, логистику, хранение, штрафы, к оплате. КРИТИЧНО: единственный способ увидеть реальную прибыль. Для детального контроля используй wb_finance_reports_list + wb_finance_report_detailed.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "limit": {"type": "integer", "default": 100000}, "rrd_id": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_reports_list",
          "[P0] Список отчётов реализации (finance-api v1). Используй для навигации по периодам — затем вызови wb_finance_report_detailed с нужным reportId. Данные с 01.01.2025.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "period": {"type": "string", "enum": ["weekly", "monthly"], "default": "weekly"},
           "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_report_detailed",
          "[P0] Детализация отчёта реализации по ID (finance-api v1). Вызывай после wb_finance_reports_list. Содержит: комиссии, логистика, хранение, штрафы, к оплате. Пагинация через rrd_id.",
          {"report_id": {"type": "string"}, "limit": {"type": "integer", "default": 100000},
           "rrd_id": {"type": "integer", "default": 0}},
          ["report_id"]),
    _tool("wb_finance_acquiring_list",
          "[P1] Список отчётов по издержкам эквайринга (комиссии за оплату картой).",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"},
           "period": {"type": "string", "default": "weekly"},
           "limit": {"type": "integer", "default": 100}, "offset": {"type": "integer", "default": 0}},
          ["date_from", "date_to"]),
    _tool("wb_finance_acquiring_detailed",
          "[P1] Детализация издержек эквайринга за период.",
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
    _tool("wb_advert_count",
          "[P1] Количество рекламных кампаний по типам и статусам. Используй для получения ID всех кампаний без фильтра."),
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
    _tool("wb_orders_archive",
          "[P2] Архивные FBS-заказы за период (завершённые/отменённые).",
          {"date_from": {"type": "string", "description": "RFC3339"},
           "date_to": {"type": "string", "description": "RFC3339 (опц.)"},
           "limit": {"type": "integer", "default": 1000}},
          ["date_from"]),
    _tool("wb_supply_order_ids",
          "[P2] Список ID сборочных заданий в поставке FBS.",
          {"supply_id": {"type": "string"}}, ["supply_id"]),
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
    _tool("wb_analytics_excise",
          "[P1] Отчёт по маркировке Честный знак (КиЗ). Лимит: 10 запросов за 5 часов.",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_item_rating",
          "[P1] Рейтинг товаров: просмотры карточки, добавления в корзину, заказы, конверсии. [Джем] КРИТИЧНО: используй чтобы найти товары с низкой конверсией — это сигнал проблемы с карточкой или ценой. Лимит ≤1000 nmID.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}}},
          ["nm_ids"]),
    _tool("wb_analytics_measurement_penalties",
          "[P1] Удержания за несоответствие фактических габаритов заявленным. [Джем] КРИТИЧНО: прямые денежные удержания из выручки — проверяй регулярно!",
          {"date_from": {"type": "string", "description": "YYYY-MM-DD"}, "date_to": {"type": "string"}},
          ["date_from", "date_to"]),
    _tool("wb_analytics_warehouse_measurements",
          "[P2] Результаты замеров товаров на складе WB — как WB измерил габариты. Сравни с заявленными чтобы выявить причину удержаний (wb_analytics_measurement_penalties).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"}}),
    _tool("wb_analytics_grouped_history",
          "[P1] Воронка продаж по группам товаров по дням (сравнение периодов).",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}},
           "date_from": {"type": "string"}, "date_to": {"type": "string"},
           "aggregation_level": {"type": "string", "default": "day"}},
          ["nm_ids", "date_from", "date_to"]),
    _tool("wb_nm_report",
          "[P1] Отчёт по номенклатуре: выручка, заказы, возвраты, конверсии по каждому nmID (task-based, ждёт до 3 мин). Отчёт хранится 3 дня.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "date_from": {"type": "string", "description": "YYYY-MM-DD (опц.)"},
           "date_to": {"type": "string", "description": "(опц.)"}}),
    _tool("wb_analytics_stocks_sizes",
          "[P1] Отчёт по остаткам и оборачиваемости с разбивкой по размерам — выявляй неликвиды по конкретным размерам.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр (опц.)"},
           "date_from": {"type": "string", "description": "(опц.)"}, "date_to": {"type": "string", "description": "(опц.)"},
           "limit": {"type": "integer", "default": 100}}),
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
    _tool("wb_feedbacks_archive",
          "[P2] Архивные отзывы (is_answered=true ранее). Отличие от wb_feedbacks_list: архив содержит отвеченные старые отзывы.",
          {"take": {"type": "integer", "default": 50}, "skip": {"type": "integer", "default": 0},
           "nm_id": {"type": "integer", "description": "Фильтр по nmID (опц.)"}}),
    _tool("wb_feedbacks_pins",
          "[P2] Закреплённые отзывы — показываются первыми на карточке. Используй лучшие отзывы для увеличения конверсии."),
    _tool("wb_feedbacks_pins_count",
          "[P2] Количество закреплённых отзывов (лимит 3 на nmID)."),
    _tool("wb_feedbacks_pins_set",
          "[P1] Закрепить отзывы (≤3 на nmID). Выбирай самые подробные позитивные отзывы.",
          {"feedback_ids": {"type": "array", "items": {"type": "string"}}},
          ["feedback_ids"]),
    _tool("wb_feedbacks_pins_delete",
          "[P2] Открепить закреплённые отзывы.",
          {"feedback_ids": {"type": "array", "items": {"type": "string"}}},
          ["feedback_ids"]),
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

    # === ДЖЕМ: подписка ===
    _tool("wb_jam_subscription",
          "[P2] Информация о подписке WB Джем (активна/истекает). Используй для проверки доступности Джем-инструментов."),

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
    _tool("wb_fbw_transit_tariffs",
          "[P2] Транзитные направления для поставок FBW в регионы."),

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
          "[P0] Текущие остатки на ВСЕХ складах WB (аналитический отчёт, лимит 1000). nm_ids — фильтр по конкретным артикулам. КРИТИЧНО: товары с остатками но без продаж = переплата за хранение.",
          {"nm_ids": {"type": "array", "items": {"type": "integer"}, "description": "Фильтр по артикулам (опц.)"},
           "limit": {"type": "integer", "default": 1000}}),

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
    _tool("wb_warehouse_create",
          "[P2] Создать склад продавца (для FBS).",
          {"name": {"type": "string"}, "address": {"type": "string", "description": "(опц.)"}},
          ["name"]),
    _tool("wb_warehouse_update",
          "[P2] Обновить склад продавца.",
          {"warehouse_id": {"type": "integer"}, "name": {"type": "string", "description": "(опц.)"},
           "address": {"type": "string", "description": "(опц.)"}},
          ["warehouse_id"]),
    _tool("wb_warehouse_delete",
          "[P2] Удалить склад продавца.",
          {"warehouse_id": {"type": "integer"}},
          ["warehouse_id"]),
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
    _tool("wb_stocks_delete",
          "[P2] Удалить записи об остатках на складе FBS (обнулить) по SKU.",
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
    _tool("wb_chat_download",
          "[P2] Скачать файл из чата покупателя. file_id — из события чата.",
          {"file_id": {"type": "string"}},
          ["file_id"]),

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
    _tool("wb_documents_download_bulk",
          "[P2] Скачать несколько документов одним запросом по их ID.",
          {"document_ids": {"type": "array", "items": {"type": "string"}}},
          ["document_ids"]),

    # === P3: ПОЛЬЗОВАТЕЛИ ===
    _tool("wb_users_list",
          "[P3] Список пользователей/сотрудников продавца."),
    _tool("wb_users_invite",
          "[P3] Пригласить пользователя (сотрудника). role: admin|manager|analyst.",
          {"email": {"type": "string"}, "role": {"type": "string", "description": "admin|manager|analyst (опц.)"}},
          ["email"]),

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
    limit=a.get("limit", 1000), offset=a.get("offset", 0), filter_nm_id=a.get("filter_nm_id"))
async def _h_prices_set(c, a): return await c.prices_set(a["data"])
async def _h_prices_quarantine(c, a): return await c.prices_quarantine_list(
    limit=a.get("limit", 1000), offset=a.get("offset", 0))
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
    limit=a.get("limit", 1000), offset=a.get("offset", 0), promo_type=a.get("promo_type"))
async def _h_promotions_auto(c, a): return await c.promotions_auto(a["start"], a["end"])
async def _h_promotions_audit(c, a): return await c.promotions_audit(
    a["start"], a["end"], only_auto=a.get("only_auto", False), max_promotions=a.get("max_promotions", 25))
async def _h_promotions_details(c, a): return await c.promotions_details(a["promotion_ids"])
async def _h_promotions_products(c, a): return await c.promotions_nomenclatures(
    a["promotion_id"], in_action=a.get("in_action"), limit=a.get("limit", 1000), offset=a.get("offset", 0))
async def _h_promotions_add_products(c, a): return await c.promotions_upload(
    a["promotion_id"], a["nm_ids"], upload_now=a.get("upload_now", True))
async def _h_promotion_exit(c, a): return await c.promotions_exit(a["data"])

# ── Финансы ──
async def _h_finance_report(c, a): return await c.finance_realization_report(
    a["date_from"], a["date_to"], limit=a.get("limit", 100000), rrd_id=a.get("rrd_id", 0))
async def _h_finance_reports_list(c, a): return await c.finance_sales_reports_list(
    a["date_from"], a["date_to"], period=a.get("period", "weekly"),
    limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_finance_report_detailed(c, a): return await c.finance_sales_report_by_id(
    a["report_id"], limit=a.get("limit", 100000), rrd_id=a.get("rrd_id", 0))
async def _h_finance_acquiring_list(c, a): return await c.finance_acquiring_list(
    a["date_from"], a["date_to"], period=a.get("period", "weekly"),
    limit=a.get("limit", 100), offset=a.get("offset", 0))
async def _h_finance_acquiring_detailed(c, a): return await c.finance_acquiring_detailed(
    a["date_from"], a["date_to"], limit=a.get("limit", 100000), rrd_id=a.get("rrd_id", 0))

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
async def _h_orders_archive(c, a): return await c.orders_archive(a["date_from"], date_to=a.get("date_to"), limit=a.get("limit", 1000))
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
async def _h_analytics_goods_labeling(c, a): return await c.analytics_goods_labeling(a["date_from"], a["date_to"])
async def _h_analytics_excise(c, a): return await c.analytics_excise_report(a["date_from"], a["date_to"])
async def _h_analytics_item_rating(c, a): return await c.analytics_item_rating(a["nm_ids"])
async def _h_analytics_measurement_penalties(c, a): return await c.analytics_measurement_penalties(a["date_from"], a["date_to"])
async def _h_analytics_warehouse_measurements(c, a): return await c.analytics_warehouse_measurements(nm_ids=a.get("nm_ids"))
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
async def _h_tariffs_commission(c, a): return await c.tariffs_commission()
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
async def _h_deductions(c, a): return await c.analytics_deductions(a["date_to"], date_from=a.get("date_from"), limit=a.get("limit", 100))
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
async def _h_orders_list(c, a): return await c.orders_list(a["date_from"], date_to=a.get("date_to"), limit=a.get("limit", 1000))
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
async def _h_stats_stocks(c, a): return await c.analytics_stocks_wb(nm_ids=a.get("nm_ids"), limit=a.get("limit", 1000))

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
async def _h_fbw_supply_goods(c, a): return await c.fbw_supply_goods(a["supply_id"], limit=a.get("limit", 1000))
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
async def _h_users_list(c, a): return await c.users_list()
async def _h_users_invite(c, a): return await c.users_invite(a["email"], role=a.get("role"))


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
    "wb_analytics_goods_labeling": _h_analytics_goods_labeling,
    "wb_analytics_excise": _h_analytics_excise,
    "wb_analytics_item_rating": _h_analytics_item_rating,
    "wb_analytics_measurement_penalties": _h_analytics_measurement_penalties,
    "wb_analytics_warehouse_measurements": _h_analytics_warehouse_measurements,
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
    "wb_users_list": _h_users_list,
    "wb_users_invite": _h_users_invite,
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
    if name in NO_CLIENT_DISPATCH:
        return _json(await NO_CLIENT_DISPATCH[name](arguments))

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
        return _json(await CLIENT_DISPATCH[name](c, arguments))

    if name in SHOP_DISPATCH:
        return _json(await SHOP_DISPATCH[name](c, arguments, shop_id))

    return [TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


# ─── Точка входа ──────────────────────────────────────────

def main():
    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
