"""HTTP-клиенты для Wildberries API.

Разделы:
  - Content API    (content-api.wildberries.ru)   — карточки товаров
  - Marketplace API (marketplace-api.wildberries.ru) — заказы, поставки, склады
  - Statistics API  (statistics-api.wildberries.ru) — продажи, заказы, склады, отчёты
  - Analytics API   (seller-analytics-api.wildberries.ru) — аналитика продавца
  - Prices API      (discounts-prices-api.wildberries.ru) — цены и скидки
  - Advert API      (advert-api.wildberries.ru) — рекламные кампании
  - Feedbacks API   (feedbacks-api.wildberries.ru) — отзывы
  - Questions API   (questions-api.wildberries.ru) — вопросы покупателей
  - Returns API     (returns-api.wildberries.ru) — возвраты
  - Tariffs API     (common-api.wildberries.ru) — тарифы логистики/хранения
  - Buyer Comms API (buyer-chat-api.wildberries.ru) — обращения покупателей
  - Documents API   (documents-api.wildberries.ru) — акты, УПД, счета-фактуры
"""

import httpx
from typing import Any
from datetime import datetime, timedelta


# ─── Базовые URL ─────────────────────────────────────────────

CONTENT_BASE = "https://content-api.wildberries.ru"
MARKETPLACE_BASE = "https://marketplace-api.wildberries.ru"
STATISTICS_BASE = "https://statistics-api.wildberries.ru"
ANALYTICS_BASE = "https://seller-analytics-api.wildberries.ru"
PRICES_BASE = "https://discounts-prices-api.wildberries.ru"
ADVERT_BASE = "https://advert-api.wildberries.ru"
FEEDBACKS_BASE = "https://feedbacks-api.wildberries.ru"
# Отдельного questions-хоста НЕ существует — вопросы на feedbacks-api
QUESTIONS_BASE = FEEDBACKS_BASE
RETURNS_BASE = "https://returns-api.wildberries.ru"
TARIFFS_BASE = "https://common-api.wildberries.ru"
BUYER_CHAT_BASE = "https://buyer-chat-api.wildberries.ru"
DOCUMENTS_BASE = "https://documents-api.wildberries.ru"
SUPPLIES_BASE = "https://supplies-api.wildberries.ru"
DP_CALENDAR_BASE = "https://dp-calendar-api.wildberries.ru"
FINANCE_BASE = "https://finance-api.wildberries.ru"


class WBClient:
    """Единый клиент для всех API Wildberries.

    Авторизация: заголовок Authorization с токеном продавца.
    """

    def __init__(self, api_token: str):
        self.api_token = api_token
        # Content-Type не задаём глобально: httpx сам ставит application/json
        # для json=-тел и multipart/form-data для files= (чат, медиа).
        headers = {"Authorization": api_token}
        timeout = httpx.Timeout(30.0, read=60.0)
        self._content = httpx.AsyncClient(base_url=CONTENT_BASE, headers=headers, timeout=timeout)
        self._marketplace = httpx.AsyncClient(base_url=MARKETPLACE_BASE, headers=headers, timeout=timeout)
        self._statistics = httpx.AsyncClient(base_url=STATISTICS_BASE, headers=headers, timeout=timeout)
        self._analytics = httpx.AsyncClient(base_url=ANALYTICS_BASE, headers=headers, timeout=timeout)
        self._prices = httpx.AsyncClient(base_url=PRICES_BASE, headers=headers, timeout=timeout)
        self._advert = httpx.AsyncClient(base_url=ADVERT_BASE, headers=headers, timeout=timeout)
        self._feedbacks = httpx.AsyncClient(base_url=FEEDBACKS_BASE, headers=headers, timeout=timeout)
        self._questions = httpx.AsyncClient(base_url=QUESTIONS_BASE, headers=headers, timeout=timeout)
        self._returns = httpx.AsyncClient(base_url=RETURNS_BASE, headers=headers, timeout=timeout)
        self._tariffs = httpx.AsyncClient(base_url=TARIFFS_BASE, headers=headers, timeout=timeout)
        self._buyer_chat = httpx.AsyncClient(base_url=BUYER_CHAT_BASE, headers=headers, timeout=timeout)
        self._documents = httpx.AsyncClient(base_url=DOCUMENTS_BASE, headers=headers, timeout=timeout)
        self._supplies = httpx.AsyncClient(base_url=SUPPLIES_BASE, headers=headers, timeout=timeout)
        self._calendar = httpx.AsyncClient(base_url=DP_CALENDAR_BASE, headers=headers, timeout=timeout)
        self._finance = httpx.AsyncClient(base_url=FINANCE_BASE, headers=headers, timeout=timeout)

    # ─── Низкоуровневые хелперы ──────────────────────────────

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        r = await client.post(path, json=body if body is not None else {})
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
        r = await client.get(path, params=params)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _put(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        r = await client.put(path, json=body if body is not None else {})
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _patch(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        r = await client.patch(path, json=body if body is not None else {})
        r.raise_for_status()
        return r.json() if r.content else {}

    async def _delete(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
        r = await client.delete(path, params=params)
        r.raise_for_status()
        return r.json() if r.content else {}

    # ═══════════════════════════════════════════════════════════
    # CONTENT API — Карточки товаров
    # ═══════════════════════════════════════════════════════════

    async def cards_cursor_list(
        self, limit: int = 100, cursor: dict | None = None,
        filter_params: dict | None = None,
    ) -> dict:
        """POST /content/v2/get/cards/list — список карточек товаров (курсорная пагинация)."""
        body: dict[str, Any] = {
            "settings": {
                "cursor": cursor or {"limit": limit},
                "filter": filter_params or {"withPhoto": -1},
            }
        }
        return await self._post(self._content, "/content/v2/get/cards/list", body)

    async def card_detail(self, nm_ids: list[int]) -> dict:
        """POST /content/v2/get/cards/detail — подробная информация по карточкам (по nmID)."""
        # Новый API endpoint для получения детальной инфо
        return await self._post(self._content, "/content/v2/get/cards/list", {
            "settings": {
                "cursor": {"limit": len(nm_ids)},
                "filter": {"textSearch": "", "withPhoto": -1},
            },
            "nmIDs": nm_ids,
        })

    async def cards_update(self, cards: list[dict]) -> dict:
        """POST /content/v2/cards/update — обновить карточки (описание, SEO, характеристики)."""
        return await self._post(self._content, "/content/v2/cards/update", cards)

    async def card_errors_list(self, limit: int = 100) -> dict:
        """POST /content/v2/cards/error/list — карточки с ошибками (несозданные/отклонённые).
        КРИТИЧНО: показывает заблокированные карточки в т.ч. по обращениям правообладателей!
        """
        return await self._post(self._content, "/content/v2/cards/error/list", {})

    async def cards_create(self, cards: list[dict]) -> dict:
        """POST /content/v2/cards/upload — создание карточек (асинхронно, синхронизация до 30 мин)."""
        return await self._post(self._content, "/content/v2/cards/upload", cards)

    async def barcodes_generate(self, count: int = 1) -> dict:
        """POST /content/v2/barcodes — генерация баркодов."""
        return await self._post(self._content, "/content/v2/barcodes", {"count": count})

    async def cards_trash_list(self, limit: int = 100, cursor: dict | None = None) -> dict:
        """POST /content/v2/get/cards/trash — карточки в корзине."""
        return await self._post(self._content, "/content/v2/get/cards/trash", {
            "settings": {"cursor": cursor or {"limit": limit}}
        })

    async def media_save_by_links(self, nm_id: int, links: list[str]) -> dict:
        """POST /content/v3/media/save — загрузить медиа по ссылкам.
        ВНИМАНИЕ: полностью ЗАМЕНЯЕТ существующие фото/видео карточки!
        """
        return await self._post(self._content, "/content/v3/media/save", {"nmId": nm_id, "data": links})

    async def subjects_list(self, name: str | None = None, parent_id: int | None = None,
                            limit: int = 100, offset: int = 0) -> dict:
        """GET /content/v2/object/all — список предметов (категорий) для создания карточек."""
        params: dict[str, Any] = {"limit": limit, "offset": offset, "locale": "ru"}
        if name:
            params["name"] = name
        if parent_id:
            params["parentID"] = parent_id
        return await self._get(self._content, "/content/v2/object/all", params)

    async def subject_charcs(self, subject_id: int) -> dict:
        """GET /content/v2/object/charcs/{subjectId} — характеристики предмета (для заполнения карточек)."""
        return await self._get(self._content, f"/content/v2/object/charcs/{subject_id}", {"locale": "ru"})

    async def directory_get(self, directory: str, subject_id: int | None = None, search: str | None = None) -> Any:
        """GET /content/v2/directory/{name} — справочники: colors, kinds, countries, seasons, vat, tnved."""
        params: dict[str, Any] = {"locale": "ru"}
        if directory == "tnved":
            if subject_id:
                params["subjectID"] = subject_id
            if search:
                params["search"] = search
        return await self._get(self._content, f"/content/v2/directory/{directory}", params)

    async def tags_list(self) -> dict:
        """GET /content/v2/tags — список ярлыков продавца."""
        return await self._get(self._content, "/content/v2/tags")

    async def tag_nomenclature_link(self, nm_id: int, tag_ids: list[int]) -> dict:
        """POST /content/v2/tag/nomenclature/link — привязать/снять ярлыки с карточки."""
        return await self._post(self._content, "/content/v2/tag/nomenclature/link", {"nmID": nm_id, "tagsIDs": tag_ids})

    async def cards_move_to_trash(self, nm_ids: list[int]) -> dict:
        """POST /content/v2/cards/delete/trash — переместить карточки в корзину."""
        return await self._post(self._content, "/content/v2/cards/delete/trash", {"nmIDs": nm_ids})

    async def cards_recover_from_trash(self, nm_ids: list[int]) -> dict:
        """POST /content/v2/cards/recover — восстановить карточки из корзины."""
        r = await self._content.post("/content/v2/cards/recover", json={"nmIDs": nm_ids})
        return {"status": r.status_code, "body": r.text}

    async def cards_limits(self) -> dict:
        """GET /content/v2/cards/limits — лимиты на создание карточек."""
        return await self._get(self._content, "/content/v2/cards/limits")

    async def object_charcs(self, object_name: str) -> dict:
        """GET /content/v2/object/charcs/{objectName} — характеристики для категории (для SEO)."""
        return await self._get(self._content, f"/content/v2/object/charcs/{object_name}")

    # ═══════════════════════════════════════════════════════════
    # PRICES API — Цены и скидки
    # ═══════════════════════════════════════════════════════════

    async def prices_list(self, limit: int = 1000, offset: int = 0, filter_nm_id: int | None = None) -> dict:
        """GET /api/v2/list/goods/filter — получить текущие цены и скидки.
        КРИТИЧНО: мониторинг цен для контроля маржинальности.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter_nm_id:
            params["filterNmID"] = filter_nm_id
        return await self._get(self._prices, "/api/v2/list/goods/filter", params)

    async def prices_set(self, data: list[dict]) -> dict:
        """POST /api/v2/upload/task — установить цены и скидки.

        Каждый элемент: {"nmID": 123, "price": 1000, "discount": 15}
        """
        return await self._post(self._prices, "/api/v2/upload/task", {"data": data})

    async def prices_sizes_set(self, data: list[dict]) -> dict:
        """POST /api/v2/upload/task/size — установить цены по размерам.

        Каждый элемент: {"nmID": 123, "sizeID": 456, "price": 1000}
        """
        return await self._post(self._prices, "/api/v2/upload/task/size", {"data": data})

    async def prices_quarantine_list(self, limit: int = 1000, offset: int = 0) -> dict:
        """GET /api/v2/quarantine/goods — товары в карантине цен (цена упала ≥3x).
        КРИТИЧНО: карантин = цена была снижена слишком сильно, новая цена не применяется.
        """
        return await self._get(self._prices, "/api/v2/quarantine/goods", {"limit": limit, "offset": offset})

    async def prices_club_discount_set(self, data: list[dict]) -> dict:
        """POST /api/v2/upload/task/club-discount — установить скидки WB Клуба (≤1000).

        Каждый элемент: {"nmID": 123, "clubDiscount": 5}
        """
        return await self._post(self._prices, "/api/v2/upload/task/club-discount", {"data": data})

    async def prices_upload_status(self, upload_id: int, buffer: bool = False) -> dict:
        """GET /api/v2/history/tasks | /api/v2/buffer/tasks — состояние загрузки цен.

        buffer=True — необработанные загрузки (например, скидки к будущей акции).
        """
        path = "/api/v2/buffer/tasks" if buffer else "/api/v2/history/tasks"
        return await self._get(self._prices, path, {"uploadID": upload_id})

    async def prices_upload_details(self, upload_id: int, buffer: bool = False,
                                    limit: int = 1000, offset: int = 0) -> dict:
        """GET /api/v2/history/goods/task | /api/v2/buffer/goods/task — детализация загрузки цен (товары + ошибки)."""
        path = "/api/v2/buffer/goods/task" if buffer else "/api/v2/history/goods/task"
        return await self._get(self._prices, path, {"uploadID": upload_id, "limit": limit, "offset": offset})

    async def prices_size_list(self, nm_id: int, limit: int = 100, offset: int = 0) -> dict:
        """GET /api/v2/list/goods/size/nm — размеры товара с ценами."""
        return await self._get(self._prices, "/api/v2/list/goods/size/nm", {"nmID": nm_id, "limit": limit, "offset": offset})

    # ═══════════════════════════════════════════════════════════
    # PROMOTIONS — Календарь акций (dp-calendar-api)
    # ═══════════════════════════════════════════════════════════

    async def promotions_list(self, start: str, end: str, all_promo: bool = False,
                              limit: int = 100, offset: int = 0) -> dict:
        """GET /api/v1/calendar/promotions — список акций WB за период.

        start/end: RFC3339 (2026-06-01T00:00:00Z). all_promo=False — только доступные для участия.
        """
        return await self._get(self._calendar, "/api/v1/calendar/promotions", {
            "startDateTime": start, "endDateTime": end,
            "allPromo": str(all_promo).lower(),
            "limitPromotion": limit, "offsetPromotion": offset,
        })

    async def promotions_details(self, promotion_ids: list[int]) -> dict:
        """GET /api/v1/calendar/promotions/details — детали акций: даты, условия, бонусы за участие."""
        return await self._get(self._calendar, "/api/v1/calendar/promotions/details", {
            "promotionIDs": promotion_ids,
        })

    async def promotions_nomenclatures(self, promotion_id: int, in_action: bool | None = None,
                                       limit: int = 100, offset: int = 0) -> dict:
        """GET /api/v1/calendar/promotions/nomenclatures — товары, подходящие для акции.

        in_action: True — уже участвуют, False — не участвуют.
        """
        params: dict[str, Any] = {"promotionID": promotion_id, "limitNomenclature": limit, "offsetNomenclature": offset}
        if in_action is not None:
            params["inAction"] = str(in_action).lower()
        return await self._get(self._calendar, "/api/v1/calendar/promotions/nomenclatures", params)

    async def promotions_upload(self, promotion_id: int, nm_ids: list[int], upload_now: bool = True) -> dict:
        """POST /api/v1/calendar/promotions/upload — добавить товары в акцию.

        upload_now=True — сразу; False — в буфер, скидки применятся при старте акции.
        ВЫХОД из акции — через установку цены/скидки (prices_set), отдельного эндпоинта нет.
        """
        return await self._post(self._calendar, "/api/v1/calendar/promotions/upload", {
            "data": {"promotionID": promotion_id, "uploadNow": upload_now, "nomenclatures": nm_ids},
        })

    # ═══════════════════════════════════════════════════════════
    # MARKETPLACE API — Заказы, поставки, склады
    # ═══════════════════════════════════════════════════════════

    async def orders_new(self) -> list:
        """GET /api/v3/orders/new — новые заказы FBS (ожидают сборки)."""
        return await self._get(self._marketplace, "/api/v3/orders/new")

    async def orders_list(
        self, date_from: str, date_to: str | None = None,
        limit: int = 1000, next_param: int = 0,
    ) -> dict:
        """GET /api/v3/orders — все заказы за период.

        date_from/date_to: RFC3339 (2024-01-01T00:00:00Z)
        """
        params: dict[str, Any] = {"limit": limit, "next": next_param, "dateFrom": date_from}
        if date_to:
            params["dateTo"] = date_to
        return await self._get(self._marketplace, "/api/v3/orders", params)

    async def orders_status(self, order_ids: list[int]) -> dict:
        """POST /api/v3/orders/status — статусы заказов."""
        return await self._post(self._marketplace, "/api/v3/orders/status", {"orders": order_ids})

    async def order_cancel(self, order_id: int) -> dict:
        """PATCH /api/v3/orders/{orderId}/cancel — отменить сборочное задание FBS."""
        return await self._patch(self._marketplace, f"/api/v3/orders/{order_id}/cancel")

    async def orders_stickers(self, order_ids: list[int], sticker_type: str = "png",
                              width: int = 58, height: int = 40) -> dict:
        """POST /api/v3/orders/stickers — стикеры для сборочных заданий (≤100).

        sticker_type: svg, zplv, zplh, png. Размеры: 58x40 или 40x30.
        """
        return await self._post_with_params(
            self._marketplace, "/api/v3/orders/stickers",
            params={"type": sticker_type, "width": width, "height": height},
            body={"orders": order_ids},
        )

    async def _post_with_params(self, client: httpx.AsyncClient, path: str,
                                params: dict, body: dict | list) -> Any:
        r = await client.post(path, params=params, json=body)
        r.raise_for_status()
        return r.json() if r.content else {}

    async def supplies_list(self, limit: int = 1000, next_param: int = 0) -> dict:
        """GET /api/v3/supplies — список поставок FBS."""
        return await self._get(self._marketplace, "/api/v3/supplies", {"limit": limit, "next": next_param})

    async def supply_create(self, name: str) -> dict:
        """POST /api/v3/supplies — создать поставку FBS."""
        return await self._post(self._marketplace, "/api/v3/supplies", {"name": name})

    async def supply_detail(self, supply_id: str) -> dict:
        """GET /api/v3/supplies/{supplyId} — информация о поставке FBS."""
        return await self._get(self._marketplace, f"/api/v3/supplies/{supply_id}")

    async def supply_delete(self, supply_id: str) -> dict:
        """DELETE /api/v3/supplies/{supplyId} — удалить пустую активную поставку."""
        return await self._delete(self._marketplace, f"/api/v3/supplies/{supply_id}")

    async def supply_add_orders(self, supply_id: str, order_ids: list[int]) -> dict:
        """PATCH /api/marketplace/v3/supplies/{supplyId}/orders — добавить задания в поставку (≤100)."""
        return await self._patch(self._marketplace, f"/api/marketplace/v3/supplies/{supply_id}/orders",
                                 {"orders": order_ids})

    async def supply_deliver(self, supply_id: str) -> dict:
        """PATCH /api/v3/supplies/{supplyId}/deliver — закрыть поставку и передать в доставку."""
        return await self._patch(self._marketplace, f"/api/v3/supplies/{supply_id}/deliver")

    async def supply_barcode(self, supply_id: str, barcode_type: str = "png") -> dict:
        """GET /api/v3/supplies/{supplyId}/barcode — QR-код поставки (svg/zplv/zplh/png)."""
        return await self._get(self._marketplace, f"/api/v3/supplies/{supply_id}/barcode", {"type": barcode_type})

    # ═══════════════════════════════════════════════════════════
    # SUPPLIES API (FBW) — Поставки на склады WB
    # ═══════════════════════════════════════════════════════════

    async def fbw_supplies_list(self, limit: int = 100, offset: int = 0, status_ids: list[int] | None = None) -> Any:
        """POST /api/v1/supplies — список поставок FBW (информационно, создание — только в ЛК)."""
        body: dict[str, Any] = {}
        if status_ids:
            body["statusIDs"] = status_ids
        return await self._post_with_params(self._supplies, "/api/v1/supplies",
                                            params={"limit": limit, "offset": offset}, body=body)

    async def fbw_supply_detail(self, supply_id: int) -> dict:
        """GET /api/v1/supplies/{ID} — детали поставки FBW."""
        return await self._get(self._supplies, f"/api/v1/supplies/{supply_id}")

    async def fbw_supply_goods(self, supply_id: int, limit: int = 1000, offset: int = 0) -> Any:
        """GET /api/v1/supplies/{ID}/goods — товары поставки FBW."""
        return await self._get(self._supplies, f"/api/v1/supplies/{supply_id}/goods", {"limit": limit, "offset": offset})

    async def fbw_acceptance_options(self, items: list[dict], warehouse_id: int | None = None) -> Any:
        """POST /api/v1/acceptance/options — доступные склады и типы упаковки для поставки FBW.

        items: [{"barcode": "...", "quantity": 10}]
        """
        params = {"warehouseID": warehouse_id} if warehouse_id else {}
        return await self._post_with_params(self._supplies, "/api/v1/acceptance/options", params=params, body=items)

    async def fbw_warehouses(self) -> Any:
        """GET /api/v1/warehouses — список складов WB (для поставок FBW)."""
        return await self._get(self._supplies, "/api/v1/warehouses")

    async def acceptance_coefficients(self, warehouse_ids: list[int] | None = None) -> Any:
        """GET /api/tariffs/v1/acceptance/coefficients (common-api) — коэффициенты приёмки складов на 14 дней.

        Приёмка доступна при coefficient 0 или 1 и allowUnload=true.
        КРИТИЧНО для планирования поставок FBW.
        """
        params = {}
        if warehouse_ids:
            params["warehouseIDs"] = ",".join(str(w) for w in warehouse_ids)
        return await self._get(self._tariffs, "/api/tariffs/v1/acceptance/coefficients", params)

    async def warehouses_list(self) -> list:
        """GET /api/v3/warehouses — список складов продавца."""
        return await self._get(self._marketplace, "/api/v3/warehouses")

    async def stocks_update(self, warehouse_id: int, stocks: list[dict]) -> dict:
        """PUT /api/v3/stocks/{warehouseId} — обновить остатки на складе FBS.

        Каждый элемент stocks: {"sku": "123456", "amount": 10}
        """
        return await self._put(self._marketplace, f"/api/v3/stocks/{warehouse_id}", {"stocks": stocks})

    async def stocks_get(self, warehouse_id: int, skus: list[str]) -> dict:
        """POST /api/v3/stocks/{warehouseId} — получить остатки на складе FBS."""
        return await self._post(self._marketplace, f"/api/v3/stocks/{warehouse_id}", {"skus": skus})

    # ═══════════════════════════════════════════════════════════
    # STATISTICS API — Продажи, заказы, склады
    # ═══════════════════════════════════════════════════════════

    async def stats_orders(self, date_from: str, flag: int = 0) -> list:
        """GET /api/v1/supplier/orders — заказы (статистика).

        date_from: RFC3339. flag=1 — вернуть только обновлённые.
        КРИТИЧНО: отслеживание отмен и возвратов.
        """
        return await self._get(self._statistics, "/api/v1/supplier/orders", {"dateFrom": date_from, "flag": flag})

    async def stats_sales(self, date_from: str, flag: int = 0) -> list:
        """GET /api/v1/supplier/sales — продажи.

        КРИТИЧНО: мониторинг продаж для выявления товаров, прекративших продаваться.
        """
        return await self._get(self._statistics, "/api/v1/supplier/sales", {"dateFrom": date_from, "flag": flag})

    async def stats_stocks(self) -> Any:
        """Текущие остатки на складах WB.

        ⚠️ Старый GET /api/v1/supplier/stocks удаляется 23.06.2026 —
        используем замену: analytics stocks-report/wb-warehouses.
        КРИТИЧНО: товары с нулевыми продажами но остатками на складе = переплата за хранение.
        """
        return await self.analytics_stocks_wb()

    async def stats_report_detail(self, date_from: str, date_to: str, limit: int = 100000, rrd_id: int = 0) -> Any:
        """GET /api/v5/supplier/reportDetailByPeriod — детальный отчёт по реализации.

        ⚠️ DEPRECATED, удаление 15.07.2026. Замена — finance_sales_report_detailed().
        """
        return await self._get(self._statistics, "/api/v5/supplier/reportDetailByPeriod", {
            "dateFrom": date_from, "dateTo": date_to, "limit": limit, "rrdid": rrd_id,
        })

    # ═══════════════════════════════════════════════════════════
    # FINANCE API — Баланс и отчёты реализации (finance-api)
    # ═══════════════════════════════════════════════════════════

    async def finance_balance(self) -> dict:
        """GET /api/v1/account/balance (finance-api) — баланс продавца. Лимит 1/мин."""
        return await self._get(self._finance, "/api/v1/account/balance")

    async def finance_sales_reports_list(self, date_from: str, date_to: str,
                                         period: str = "weekly",
                                         limit: int = 100, offset: int = 0) -> dict:
        """POST /api/finance/v1/sales-reports/list — список отчётов реализации (данные с 01.01.2025)."""
        return await self._post(self._finance, "/api/finance/v1/sales-reports/list", {
            "dateFrom": date_from, "dateTo": date_to, "period": period,
            "limit": limit, "offset": offset,
        })

    async def finance_sales_report_detailed(self, date_from: str, date_to: str,
                                            limit: int = 100000, rrd_id: int = 0) -> dict:
        """POST /api/finance/v1/sales-reports/detailed — детализация реализации за период.

        Замена устаревшего reportDetailByPeriod. Данные с 29.01.2024. Лимит 1/мин.
        Содержит ВСЕ: комиссии, логистику, хранение, штрафы, к оплате.
        """
        return await self._post(self._finance, "/api/finance/v1/sales-reports/detailed", {
            "dateFrom": date_from, "dateTo": date_to, "limit": limit, "rrdId": rrd_id,
        })

    # ═══════════════════════════════════════════════════════════
    # ANALYTICS API — Аналитика продавца
    # ═══════════════════════════════════════════════════════════

    # nm-report detail/grouped УДАЛЕНЫ из WB API (миграция завершена 12.2025).
    # Замена — воронка продаж v3 (sales-funnel). Лимит: 3 запроса/мин.

    async def analytics_sales_funnel(
        self, date_from: str, date_to: str,
        nm_ids: list[int] | None = None,
        brand_names: list[str] | None = None,
        subject_ids: list[int] | None = None,
        limit: int = 100, offset: int = 0,
    ) -> dict:
        """POST /api/analytics/v3/sales-funnel/products — воронка продаж по карточкам.

        Метрики: просмотры, клики, корзина, заказы, выручка, конверсии (+ сравнение периодов).
        КРИТИЧНО: падение конверсий = проблема SEO или конкурент обошёл. Лимит 3/мин.
        """
        body: dict[str, Any] = {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "orderBy": {"field": "openCard", "mode": "desc"},
            "limit": limit, "offset": offset,
        }
        if nm_ids:
            body["nmIds"] = nm_ids
        if brand_names:
            body["brandNames"] = brand_names
        if subject_ids:
            body["subjectIds"] = subject_ids
        return await self._post(self._analytics, "/api/analytics/v3/sales-funnel/products", body)

    async def analytics_sales_funnel_history(
        self, nm_ids: list[int], date_from: str, date_to: str,
        aggregation_level: str = "day",
    ) -> dict:
        """POST /api/analytics/v3/sales-funnel/products/history — воронка по дням (максимум последняя неделя)."""
        return await self._post(self._analytics, "/api/analytics/v3/sales-funnel/products/history", {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": nm_ids,
            "aggregationLevel": aggregation_level,
        })

    async def _task_report_flow(self, create_path: str, params: dict, task_prefix: str) -> Any:
        """Общий flow асинхронных отчётов: создать задание → дождаться → скачать."""
        import asyncio as _aio
        created = await self._get(self._analytics, create_path, params)
        task_id = (created.get("data") or {}).get("taskId") or created.get("taskId")
        if not task_id:
            return created
        for _ in range(24):  # до ~2 минут ожидания
            await _aio.sleep(5)
            status = await self._get(self._analytics, f"{task_prefix}/tasks/{task_id}/status")
            st = (status.get("data") or {}).get("status") or status.get("status")
            if st == "done":
                return await self._get(self._analytics, f"{task_prefix}/tasks/{task_id}/download")
            if st in ("canceled", "purged", "error"):
                return {"task_id": task_id, "status": st, "error": "Задание не выполнено"}
        return {"task_id": task_id, "status": "timeout",
                "hint": f"Отчёт ещё готовится. Скачать позже: GET {task_prefix}/tasks/{task_id}/download"}

    async def analytics_paid_storage(self, date_from: str, date_to: str) -> Any:
        """GET /api/v1/paid_storage (task-based) — отчёт по платному хранению.

        КРИТИЧНО: товары с нулевыми продажами и высокой стоимостью хранения = прямые убытки.
        """
        return await self._task_report_flow(
            "/api/v1/paid_storage", {"dateFrom": date_from, "dateTo": date_to}, "/api/v1/paid_storage",
        )

    async def analytics_warehouse_remains(self, group_by_nm: bool = True) -> Any:
        """GET /api/v1/warehouse_remains (task-based) — отчёт об остатках на складах WB."""
        params = {"groupByNm": str(group_by_nm).lower(), "groupBySize": "false"}
        return await self._task_report_flow(
            "/api/v1/warehouse_remains", params, "/api/v1/warehouse_remains",
        )

    async def analytics_antifraud(self, date: str) -> dict:
        """GET /api/v1/analytics/antifraud-details — удержания за самовыкупы (отчёт по средам)."""
        return await self._get(self._analytics, "/api/v1/analytics/antifraud-details", {"date": date})

    async def analytics_stocks_wb(self, nm_ids: list[int] | None = None,
                                  limit: int = 1000, offset: int = 0) -> dict:
        """POST /api/analytics/v1/stocks-report/wb-warehouses — ТЕКУЩИЕ остатки на складах WB.

        Замена устаревшего statistics /api/v1/supplier/stocks (удаляется 23.06.2026).
        Обновление раз в 30 мин. Лимит 3/мин.
        """
        body: dict[str, Any] = {"limit": limit, "offset": offset}
        if nm_ids:
            body["nmIds"] = nm_ids
        return await self._post(self._analytics, "/api/analytics/v1/stocks-report/wb-warehouses", body)

    async def analytics_stocks_report(self, date_from: str, date_to: str,
                                      nm_ids: list[int] | None = None,
                                      limit: int = 100, offset: int = 0) -> dict:
        """POST /api/v2/stocks-report/products/products — интерактивный отчёт по остаткам и оборачиваемости."""
        body: dict[str, Any] = {
            "currentPeriod": {"start": date_from, "end": date_to},
            "stockType": "", "skipDeletedNm": True,
            "orderBy": {"field": "avgOrders", "mode": "desc"},
            "availabilityFilters": ["actual", "balanced", "deficient", "nonActual", "nonLiquid", "invisible"],
            "limit": limit, "offset": offset,
        }
        if nm_ids:
            body["nmIDs"] = nm_ids
        return await self._post(self._analytics, "/api/v2/stocks-report/products/products", body)

    async def analytics_excise_report(self, date_from: str, date_to: str) -> dict:
        """POST /api/v1/analytics/excise-report — отчёт по маркировке (Честный знак). Лимит 10 за 5 ч."""
        return await self._post_with_params(self._analytics, "/api/v1/analytics/excise-report",
                                            params={"dateFrom": date_from, "dateTo": date_to}, body={})

    async def analytics_acceptance_report(self, date_from: str, date_to: str) -> Any:
        """GET /api/v1/acceptance_report (task-based) — отчёт по платной приёмке."""
        return await self._task_report_flow(
            "/api/v1/acceptance_report", {"dateFrom": date_from, "dateTo": date_to}, "/api/v1/acceptance_report",
        )

    async def analytics_banned_products(self, shadowed: bool = False) -> dict:
        """GET /api/v1/analytics/banned-products/{blocked|shadowed} — заблокированные/скрытые карточки.

        КРИТИЧНО: заблокированные и скрытые из каталога товары = потерянные продажи.
        """
        path = "shadowed" if shadowed else "blocked"
        return await self._get(self._analytics, f"/api/v1/analytics/banned-products/{path}",
                               {"sort": "nmId", "order": "asc"})

    async def analytics_goods_return(self, date_from: str, date_to: str) -> dict:
        """GET /api/v1/analytics/goods-return — возвраты товаров продавцу (макс. 31 день)."""
        return await self._get(self._analytics, "/api/v1/analytics/goods-return",
                               {"dateFrom": date_from, "dateTo": date_to})

    async def analytics_deductions(self, date_to: str, date_from: str | None = None,
                                   limit: int = 100, offset: int = 0) -> dict:
        """GET /api/analytics/v1/deductions — удержания за подмены и неверные вложения."""
        params: dict[str, Any] = {"dateTo": date_to, "limit": limit, "offset": offset}
        if date_from:
            params["dateFrom"] = date_from
        return await self._get(self._analytics, "/api/analytics/v1/deductions", params)

    async def search_report(self, date_from: str, date_to: str,
                            nm_ids: list[int] | None = None,
                            limit: int = 30, offset: int = 0) -> dict:
        """POST /api/v2/search-report/report — отчёт по поисковым запросам (Джем).

        КРИТИЧНО: видимость в поиске = продажи. Лимит 3/мин.
        """
        body: dict[str, Any] = {
            "currentPeriod": {"start": date_from, "end": date_to},
            "positionCluster": "all",
            "includeSearchTexts": True, "includeSubstitutedSKUs": False,
            "orderBy": {"field": "openCard", "mode": "desc"},
            "limit": limit, "offset": offset,
        }
        if nm_ids:
            body["nmIds"] = nm_ids
        return await self._post(self._analytics, "/api/v2/search-report/report", body)

    async def search_texts_by_product(self, nm_ids: list[int], date_from: str, date_to: str,
                                      limit: int = 30) -> dict:
        """POST /api/v2/search-report/product/search-texts — топ поисковых запросов по товарам (≤30)."""
        return await self._post(self._analytics, "/api/v2/search-report/product/search-texts", {
            "currentPeriod": {"start": date_from, "end": date_to},
            "nmIds": nm_ids,
            "topOrderBy": "openCard",
            "orderBy": {"field": "avgPosition", "mode": "asc"},
            "limit": limit,
        })

    # ═══════════════════════════════════════════════════════════
    # ADVERT API — Рекламные кампании
    # ═══════════════════════════════════════════════════════════

    # Со 2 февраля 2026 WB отключил старую модель кампаний (тип 8) и старые
    # эндпоинты (/adv/v1/promotion/adverts, /adv/v2/fullstats, CPM, set-plus).
    # Актуальная модель: кампании типа 9 (seacat), ставки manual/unified,
    # ключевые фразы заменены поисковыми кластерами (normquery).

    async def advert_count(self) -> dict:
        """GET /adv/v1/promotion/count — списки ID кампаний по типам и статусам."""
        return await self._get(self._advert, "/adv/v1/promotion/count")

    async def advert_list(self, ids: list[int] | None = None, statuses: list[int] | None = None,
                          payment_type: str | None = None) -> Any:
        """GET /api/advert/v2/adverts — информация о кампаниях.

        statuses: -1 удалена, 4 готова, 7 завершена, 8 отменена, 9 активна, 11 пауза.
        payment_type: cpm | cpc.
        """
        params: dict[str, Any] = {}
        if ids:
            params["ids"] = ",".join(str(i) for i in ids)
        if statuses:
            params["statuses"] = ",".join(str(s) for s in statuses)
        if payment_type:
            params["payment_type"] = payment_type
        return await self._get(self._advert, "/api/advert/v2/adverts", params)

    async def advert_create(self, name: str, nm_ids: list[int], bid_type: str = "unified",
                            payment_type: str = "cpm", placement_types: list[str] | None = None) -> Any:
        """POST /adv/v2/seacat/save-ad — создать кампанию (единственный способ с 2026).

        bid_type: manual | unified. payment_type: cpm | cpc.
        placement_types (только для manual): search, recommendations.
        """
        body: dict[str, Any] = {"name": name, "nms": nm_ids, "bid_type": bid_type, "payment_type": payment_type}
        if placement_types and bid_type == "manual":
            body["placement_types"] = placement_types
        return await self._post(self._advert, "/adv/v2/seacat/save-ad", body)

    async def advert_statistics(self, advert_ids: list[int], date_from: str, date_to: str) -> Any:
        """GET /adv/v3/fullstats — статистика кампаний (вкл. дневную детализацию в days[]).

        Лимит: 3 запроса/мин! Период ≤ 31 дня. Даты: YYYY-MM-DD.
        КРИТИЧНО: если расход/выручка > 20% — ДРР слишком высокий, кампания убыточна!
        """
        return await self._get(self._advert, "/adv/v3/fullstats", {
            "ids": ",".join(str(i) for i in advert_ids),
            "beginDate": date_from, "endDate": date_to,
        })

    async def advert_balance(self) -> dict:
        """GET /adv/v1/balance — баланс рекламного кабинета."""
        return await self._get(self._advert, "/adv/v1/balance")

    async def advert_budget(self, advert_id: int) -> dict:
        """GET /adv/v1/budget — бюджет конкретной кампании."""
        return await self._get(self._advert, "/adv/v1/budget", {"id": advert_id})

    async def advert_budget_deposit(self, advert_id: int, amount: int, source: int = 0) -> dict:
        """POST /adv/v1/budget/deposit?id= — пополнить бюджет кампании.

        source: 0 = счёт, 1 = баланс, 3 = бонусы.
        """
        return await self._post_with_params(self._advert, "/adv/v1/budget/deposit",
                                            params={"id": advert_id},
                                            body={"sum": amount, "type": source, "return": True})

    async def advert_costs_history(self, date_from: str, date_to: str) -> Any:
        """GET /adv/v1/upd — история затрат на рекламу за период."""
        return await self._get(self._advert, "/adv/v1/upd", {"from": date_from, "to": date_to})

    async def advert_start(self, advert_id: int) -> Any:
        """GET /adv/v0/start — запустить рекламную кампанию."""
        return await self._get(self._advert, "/adv/v0/start", {"id": advert_id})

    async def advert_pause(self, advert_id: int) -> Any:
        """GET /adv/v0/pause — приостановить кампанию. КРИТИЧНО: экстренная остановка убыточной кампании."""
        return await self._get(self._advert, "/adv/v0/pause", {"id": advert_id})

    async def advert_stop(self, advert_id: int) -> Any:
        """GET /adv/v0/stop — завершить кампанию."""
        return await self._get(self._advert, "/adv/v0/stop", {"id": advert_id})

    async def advert_delete(self, advert_id: int) -> Any:
        """GET /adv/v0/delete — удалить кампанию (необратимо, ~10 мин)."""
        return await self._get(self._advert, "/adv/v0/delete", {"id": advert_id})

    async def advert_bids_set(self, bids: list[dict]) -> Any:
        """PATCH /api/advert/v1/bids — изменить ставки CPM/CPC.

        bids: [{advert_id, nm_bids: [{nm_id, bid_kopecks, placement: search|recommendations|combined}]}]
        Ставки в КОПЕЙКАХ. combined — для unified-кампаний.
        """
        return await self._patch(self._advert, "/api/advert/v1/bids", {"bids": bids})

    async def advert_bids_recommendations(self, nm_id: int, advert_id: int) -> Any:
        """GET /api/advert/v0/bids/recommendations — рекомендуемые ставки для карточки."""
        return await self._get(self._advert, "/api/advert/v0/bids/recommendations",
                               {"nmId": nm_id, "advertId": advert_id})

    # ── Поисковые кластеры (бывшие «ключевые фразы») ─────────

    async def advert_clusters_list(self, advert_id: int) -> Any:
        """POST /adv/v0/normquery/list — активные/неактивные поисковые кластеры кампании.

        КРИТИЧНО: мониторинг поисковых запросов для SEO-позиций.
        """
        return await self._post(self._advert, "/adv/v0/normquery/list", {"advert_id": advert_id})

    async def advert_clusters_stats(self, advert_id: int, date_from: str, date_to: str,
                                    nm_ids: list[int] | None = None, daily: bool = False) -> Any:
        """POST /adv/v0|v1/normquery/stats — статистика по поисковым кластерам (v1 — по дням)."""
        body: dict[str, Any] = {"advert_id": advert_id, "begin": date_from, "end": date_to}
        if nm_ids:
            body["nm_ids"] = nm_ids
        path = "/adv/v1/normquery/stats" if daily else "/adv/v0/normquery/stats"
        return await self._post(self._advert, path, body)

    async def advert_cluster_bids_set(self, bids: list[dict]) -> Any:
        """POST /adv/v0/normquery/bids — ставки на конкретные кластеры.

        bids: [{advert_id, nm_id, norm_query, bid}] — bid в РУБЛЯХ за 1000 показов.
        """
        return await self._post(self._advert, "/adv/v0/normquery/bids", {"bids": bids})

    async def advert_minus_phrases_get(self, advert_id: int, nm_id: int | None = None) -> Any:
        """POST /adv/v0/normquery/get-minus — минус-фразы кампании."""
        body: dict[str, Any] = {"advert_id": advert_id}
        if nm_id:
            body["nm_id"] = nm_id
        return await self._post(self._advert, "/adv/v0/normquery/get-minus", body)

    async def advert_minus_phrases_set(self, advert_id: int, nm_id: int, norm_queries: list[str]) -> Any:
        """POST /adv/v0/normquery/set-minus — установить минус-фразы (плюс-фраз с 2026 нет)."""
        return await self._post(self._advert, "/adv/v0/normquery/set-minus",
                                {"advert_id": advert_id, "nm_id": nm_id, "norm_queries": norm_queries})

    # ═══════════════════════════════════════════════════════════
    # FEEDBACKS API — Отзывы
    # ═══════════════════════════════════════════════════════════

    async def feedbacks_list(
        self, is_answered: bool | None = None, take: int = 50, skip: int = 0,
        order: str = "dateDesc", nm_id: int | None = None,
    ) -> dict:
        """GET /api/v1/feedbacks — список отзывов.

        КРИТИЧНО: негативные отзывы без ответа снижают рейтинг и конверсию.
        """
        params: dict[str, Any] = {"take": take, "skip": skip, "order": order}
        if is_answered is not None:
            params["isAnswered"] = is_answered
        if nm_id is not None:
            params["nmId"] = nm_id
        return await self._get(self._feedbacks, "/api/v1/feedbacks", params)

    async def feedback_reply(self, feedback_id: str, text: str, edit: bool = False) -> dict:
        """POST|PATCH /api/v1/feedbacks/answer — ответить на отзыв / отредактировать ответ.

        Старый PATCH /api/v1/feedbacks удалён из WB API.
        """
        method = self._patch if edit else self._post
        return await method(self._feedbacks, "/api/v1/feedbacks/answer", {"id": feedback_id, "text": text})

    async def feedbacks_count(self) -> dict:
        """GET /api/v1/feedbacks/count-unanswered — количество неотвеченных отзывов."""
        return await self._get(self._feedbacks, "/api/v1/feedbacks/count-unanswered")

    async def feedbacks_archive(self, take: int = 50, skip: int = 0, nm_id: int | None = None) -> dict:
        """GET /api/v1/feedbacks/archive — архивные отзывы."""
        params: dict[str, Any] = {"take": take, "skip": skip}
        if nm_id:
            params["nmId"] = nm_id
        return await self._get(self._feedbacks, "/api/v1/feedbacks/archive", params)

    # ═══════════════════════════════════════════════════════════
    # QUESTIONS API — Вопросы покупателей
    # ═══════════════════════════════════════════════════════════

    async def questions_list(
        self, is_answered: bool | None = None, take: int = 50, skip: int = 0,
        order: str = "dateDesc", nm_id: int | None = None,
    ) -> dict:
        """GET /api/v1/questions — список вопросов от покупателей."""
        params: dict[str, Any] = {"take": take, "skip": skip, "order": order}
        if is_answered is not None:
            params["isAnswered"] = is_answered
        if nm_id is not None:
            params["nmId"] = nm_id
        return await self._get(self._questions, "/api/v1/questions", params)

    async def question_reply(self, question_id: str, text: str, reject: bool = False) -> dict:
        """PATCH /api/v1/questions — ответить на вопрос (state=wbRu) или отклонить (state=none)."""
        return await self._patch(self._questions, "/api/v1/questions", {
            "id": question_id,
            "answer": {"text": text},
            "state": "none" if reject else "wbRu",
        })

    async def questions_count(self) -> dict:
        """GET /api/v1/questions/count-unanswered — количество неотвеченных вопросов."""
        return await self._get(self._questions, "/api/v1/questions/count-unanswered")

    # ═══════════════════════════════════════════════════════════
    # RETURNS API — Возвраты
    # ═══════════════════════════════════════════════════════════

    async def returns_claims(
        self, is_archive: bool = False, nm_id: int | None = None,
        claim_id: str | None = None, limit: int = 200, offset: int = 0,
    ) -> dict:
        """GET /api/v1/claims — заявки покупателей на возврат.

        is_archive=False — на рассмотрении, True — архив.
        В ответе actions[] — допустимые действия по заявке.
        КРИТИЧНО: массовые возвраты конкретного товара могут указывать на проблему качества.
        """
        params: dict[str, Any] = {"is_archive": str(is_archive).lower(), "limit": limit, "offset": offset}
        if nm_id:
            params["nm_id"] = nm_id
        if claim_id:
            params["id"] = claim_id
        return await self._get(self._returns, "/api/v1/claims", params)

    async def returns_claim_answer(self, claim_id: str, action: str, comment: str | None = None) -> dict:
        """PATCH /api/v1/claim — ответ на заявку возврата.

        action — строго из массива actions заявки: approve1 (проверка брака на складе WB),
        approve2 (забрать товар себе), autorefund1 (без возврата товара),
        reject1/reject2/reject3 (шаблоны WB), rejectcustom (свой комментарий — comment обязателен).
        """
        body: dict[str, Any] = {"id": claim_id, "action": action}
        if comment:
            body["comment"] = comment
        return await self._patch(self._returns, "/api/v1/claim", body)

    # ═══════════════════════════════════════════════════════════
    # TARIFFS API — Тарифы логистики и хранения
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _date_or_today(date: str | None) -> str:
        if date:
            return date
        from datetime import date as _d
        return _d.today().isoformat()

    async def tariffs_box(self, date: str | None = None) -> dict:
        """GET /api/v1/tariffs/box — тарифы на логистику коробов (date обязателен, по умолчанию сегодня).

        КРИТИЧНО: рост тарифов = рост расходов. Мониторинг для контроля себестоимости.
        """
        return await self._get(self._tariffs, "/api/v1/tariffs/box", {"date": self._date_or_today(date)})

    async def tariffs_pallet(self, date: str | None = None) -> dict:
        """GET /api/v1/tariffs/pallet — тарифы на логистику палет (FBW)."""
        return await self._get(self._tariffs, "/api/v1/tariffs/pallet", {"date": self._date_or_today(date)})

    async def tariffs_return(self, date: str | None = None) -> dict:
        """GET /api/v1/tariffs/return — тарифы на возвраты (обратная логистика).

        КРИТИЧНО: обратная логистика — скрытые расходы. Высокий процент возвратов + высокий тариф = убытки.
        """
        return await self._get(self._tariffs, "/api/v1/tariffs/return", {"date": self._date_or_today(date)})

    async def seller_info(self) -> dict:
        """GET /api/v1/seller-info (common-api) — имя продавца и ID. Работает с любым токеном."""
        return await self._get(self._tariffs, "/api/v1/seller-info")

    async def seller_rating(self) -> dict:
        """GET /api/common/v1/rating (feedbacks-api) — рейтинг продавца."""
        return await self._get(self._feedbacks, "/api/common/v1/rating")

    async def jam_subscription(self) -> dict:
        """GET /api/common/v1/subscriptions (common-api) — информация о подписке Джем."""
        return await self._get(self._tariffs, "/api/common/v1/subscriptions")

    async def tariffs_commission(self) -> dict:
        """GET /api/v1/tariffs/commission — комиссии WB по категориям.

        Показывает комиссию FBO, FBS, DBS и другие удержания по категориям товаров.
        """
        return await self._get(self._tariffs, "/api/v1/tariffs/commission")

    # ═══════════════════════════════════════════════════════════
    # FINANCE — Финансовые отчёты (через Statistics API)
    # ═══════════════════════════════════════════════════════════

    async def finance_realization_report(
        self, date_from: str, date_to: str, limit: int = 100000, rrd_id: int = 0,
    ) -> Any:
        """Отчёт о реализации: новый finance-api, при недоступности (нет категории
        «Финансы» в токене) — fallback на старый reportDetailByPeriod (живёт до 15.07.2026).

        Содержит все финансовые данные:
        - retail_price, retail_amount — цена и сумма продажи
        - commission_percent — комиссия WB
        - delivery_rub — стоимость логистики
        - storage_fee — стоимость хранения
        - penalty — штрафы
        - additional_payment — доплаты
        - ppvz_for_pay — к оплате продавцу (чистый доход)
        """
        try:
            return await self.finance_sales_report_detailed(date_from, date_to, limit, rrd_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 404):
                # Токен без категории «Финансы» — старый эндпоинт (до 15.07.2026)
                return await self.stats_report_detail(date_from, date_to, limit, rrd_id)
            raise

    # ═══════════════════════════════════════════════════════════
    # BUYER COMMUNICATION — Обращения и чаты
    # ═══════════════════════════════════════════════════════════

    async def buyer_chats_list(self) -> dict:
        """GET /api/v1/seller/chats — список чатов с покупателями (содержит replySign для ответа).

        КРИТИЧНО: может содержать жалобы и обращения правообладателей.
        """
        return await self._get(self._buyer_chat, "/api/v1/seller/chats")

    async def buyer_chat_events(self, next_cursor: int | None = None) -> dict:
        """GET /api/v1/seller/events — события чатов (сообщения). Курсорная пагинация через next."""
        params: dict[str, Any] = {}
        if next_cursor is not None:
            params["next"] = next_cursor
        return await self._get(self._buyer_chat, "/api/v1/seller/events", params)

    async def buyer_chat_send(self, reply_sign: str, message: str) -> dict:
        """POST /api/v1/seller/message — отправить сообщение в чат (multipart, ≤1000 символов).

        reply_sign — из объекта чата (buyer_chats_list).
        """
        # files с (None, value) заставляет httpx собрать multipart/form-data
        r = await self._buyer_chat.post(
            "/api/v1/seller/message",
            files={"replySign": (None, reply_sign), "message": (None, message)},
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    # ═══════════════════════════════════════════════════════════
    # DOCUMENTS API — Акты, УПД, счета-фактуры
    # ═══════════════════════════════════════════════════════════

    async def documents_categories(self) -> dict:
        """GET /api/v1/documents/categories — категории документов.

        Возвращает список доступных типов документов (акты сверки, УПД, счета и т.д.).
        """
        return await self._get(self._documents, "/api/v1/documents/categories")

    async def documents_list(
        self, date_from: str | None = None, date_to: str | None = None,
        category_id: int | None = None, limit: int = 100, offset: int = 0,
    ) -> dict:
        """GET /api/v1/documents/list — список документов продавца.

        КРИТИЧНО: содержит акты сверки, УПД, уведомления о выкупе и другие
        финансовые документы. Необходимо для бухгалтерии и контроля.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if date_from:
            params["dateFrom"] = date_from
        if date_to:
            params["dateTo"] = date_to
        if category_id is not None:
            params["categoryID"] = category_id
        return await self._get(self._documents, "/api/v1/documents/list", params)

    async def document_download(self, document_id: str) -> dict:
        """GET /api/v1/documents/download — скачать конкретный документ.

        Возвращает ссылку на скачивание документа (PDF/XML).
        """
        return await self._get(self._documents, "/api/v1/documents/download", {"id": document_id})

    # ═══════════════════════════════════════════════════════════
    # Закрытие
    # ═══════════════════════════════════════════════════════════

    async def close(self):
        """Закрыть все HTTP-клиенты."""
        for client in [
            self._content, self._marketplace, self._statistics, self._analytics,
            self._prices, self._advert, self._feedbacks, self._questions,
            self._returns, self._tariffs, self._buyer_chat, self._documents,
            self._supplies, self._calendar, self._finance,
        ]:
            await client.aclose()
