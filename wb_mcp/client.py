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

import asyncio
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

    # Статусы, при которых имеет смысл повторить запрос.
    _RETRY_STATUSES = {429, 500, 502, 503, 504}

    async def _send(self, method: str, client: httpx.AsyncClient, path: str, *,
                    params: dict | None = None, json_body: Any = None,
                    max_retries: int = 4) -> Any:
        """Единая точка отправки запросов с авто-throttle на 429/5xx.

        WB лимитирует часть API (напр. календарь акций — 10 запросов / 6 сек).
        При 429/5xx ждём Retry-After (или экспоненциальный backoff) и повторяем.
        """
        delay = 1.0
        for attempt in range(max_retries + 1):
            r = await client.request(method, path, params=params, json=json_body)
            if r.status_code in self._RETRY_STATUSES and attempt < max_retries:
                retry_after = r.headers.get("Retry-After", "")
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                await asyncio.sleep(min(wait, 15.0))
                delay = min(delay * 2, 15.0)
                continue
            r.raise_for_status()
            return r.json() if r.content else {}

    async def _post(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        return await self._send("POST", client, path, json_body=body if body is not None else {})

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
        return await self._send("GET", client, path, params=params)

    async def _put(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        return await self._send("PUT", client, path, json_body=body if body is not None else {})

    async def _patch(self, client: httpx.AsyncClient, path: str, body: dict | list | None = None) -> Any:
        return await self._send("PATCH", client, path, json_body=body if body is not None else {})

    async def _delete(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> Any:
        return await self._send("DELETE", client, path, params=params)

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

    async def tag_create(self, name: str, color: str = "#FF0000") -> dict:
        """POST /content/v2/tag — создать ярлык (тег). color: HEX-цвет."""
        return await self._post(self._content, "/content/v2/tag", {"name": name, "color": color})

    async def tag_update(self, tag_id: int, name: str, color: str) -> dict:
        """PATCH /content/v2/tag/{id} — обновить ярлык (название, цвет)."""
        return await self._patch(self._content, f"/content/v2/tag/{tag_id}", {"name": name, "color": color})

    async def tag_delete(self, tag_id: int) -> dict:
        """DELETE /content/v2/tag/{id} — удалить ярлык. ВНИМАНИЕ: ошибка если тег привязан к товарам."""
        return await self._delete(self._content, f"/content/v2/tag/{tag_id}")

    async def card_recommendations_get(self, nm_id: int) -> dict:
        """POST /api/content/v1/recommendations/list — рекомендованные товары к карточке."""
        return await self._post(self._content, "/api/content/v1/recommendations/list", {"nmId": nm_id})

    async def card_recommendations_set(self, nm_id: int, recommended_nm_ids: list[int]) -> dict:
        """POST /api/content/v1/recommendations/set — установить рекомендованные товары к карточке (≤10 nmID)."""
        return await self._post(self._content, "/api/content/v1/recommendations/set",
                                {"nmId": nm_id, "recommendedNmIds": recommended_nm_ids})

    async def brands_list(self, subject_id: int | None = None) -> dict:
        """GET /api/content/v1/brands — список брендов продавца по ID предмета."""
        params: dict[str, Any] = {}
        if subject_id:
            params["subjectId"] = subject_id
        return await self._get(self._content, "/api/content/v1/brands", params)

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

    async def prices_b2b_set(self, data: list[dict]) -> dict:
        """POST /api/discounts-prices/v1/upload/task/b2b/wholesale — оптовые B2B скидки.
        Каждый элемент: {"nmID": 123, "wholesaleDiscount": 10}
        """
        return await self._post(self._prices, "/api/discounts-prices/v1/upload/task/b2b/wholesale",
                                {"data": data})

    # ═══════════════════════════════════════════════════════════
    # PROMOTIONS — Календарь акций (dp-calendar-api)
    # ═══════════════════════════════════════════════════════════

    async def promotions_list(self, start: str, end: str, all_promo: bool = False,
                              limit: int = 1000, offset: int = 0,
                              promo_type: str | None = None) -> dict:
        """GET /api/v1/calendar/promotions — список акций WB за период.

        start/end: RFC3339 (2026-06-01T00:00:00Z). all_promo=False — только доступные для участия.
        promo_type: "auto" (автоакции — WB добавляет товары сам) | "regular" (обычные) | None (все).
                    Фильтрация на стороне клиента по полю type ответа WB.
        """
        resp = await self._get(self._calendar, "/api/v1/calendar/promotions", {
            "startDateTime": start, "endDateTime": end,
            "allPromo": str(all_promo).lower(),
            "limitPromotion": limit, "offsetPromotion": offset,
        })
        if promo_type in ("auto", "regular"):
            promos = (resp.get("data") or {}).get("promotions") or resp.get("promotions") or []
            filtered = [p for p in promos if p.get("type") == promo_type]
            return {"promotions": filtered, "total": len(filtered), "filteredBy": promo_type}
        return resp

    @staticmethod
    def _extract_promotions(resp: Any) -> list[dict]:
        """Достать список акций из разных форматов ответа WB."""
        if isinstance(resp, dict):
            data = resp.get("data")
            if isinstance(data, dict) and "promotions" in data:
                return data["promotions"] or []
            if "promotions" in resp:
                return resp["promotions"] or []
        return resp if isinstance(resp, list) else []

    @staticmethod
    def _extract_nomenclatures(resp: Any) -> list[dict]:
        """Достать список товаров акции из разных форматов ответа WB."""
        if isinstance(resp, dict):
            data = resp.get("data")
            if isinstance(data, dict) and "nomenclatures" in data:
                return data["nomenclatures"] or []
            if "nomenclatures" in resp:
                return resp["nomenclatures"] or []
        return resp if isinstance(resp, list) else []

    async def promotions_details(self, promotion_ids: list[int]) -> dict:
        """GET /api/v1/calendar/promotions/details — детали акций: даты, условия, бонусы за участие."""
        return await self._get(self._calendar, "/api/v1/calendar/promotions/details", {
            "promotionIDs": promotion_ids,
        })

    async def promotions_nomenclatures(self, promotion_id: int, in_action: bool | None = None,
                                       limit: int = 1000, offset: int = 0) -> dict:
        """GET /api/v1/calendar/promotions/nomenclatures — товары, подходящие для акции.

        in_action: True — уже участвуют, False — не участвуют.
        Ответ по товару: price/planPrice (цена сейчас → в акции), discount/planDiscount.
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

    # ── Композитные инструменты по акциям/автоакциям ──────────

    async def promotions_auto(self, start: str, end: str, limit: int = 1000, offset: int = 0) -> dict:
        """Только АВТОАКЦИИ (type=auto) за период — WB добавляет товары сам.

        Критичный мониторинг: проверяй регулярно, чтобы цены не упали без твоего ведома.
        """
        resp = await self.promotions_list(start, end, all_promo=True, limit=limit, offset=offset)
        autos = [p for p in self._extract_promotions(resp) if p.get("type") == "auto"]
        return {"autoPromotions": autos, "total": len(autos), "period": {"start": start, "end": end}}

    async def promotions_audit(self, start: str, end: str, only_auto: bool = False,
                               max_promotions: int = 25) -> dict:
        """Аудит участия: куда WB уже добавил мои товары и каков ценовой эффект.

        Проходит по акциям периода (по умолчанию только автоакции), для каждой берёт
        товары с inAction=true и считает падение цены (price→planPrice) и рост скидки.
        Авто-throttle учитывает лимит календаря (10 запросов / 6 сек).

        ВАЖНО: для АВТОАКЦИЙ (type=auto) WB не отдаёт состав товаров через API
        (эндпоинт nomenclatures возвращает 422) — состав формирует сам WB.
        Такие акции помечаются nomenclaturesAvailable=false; контроль цен — через
        wb_prices_list / wb_prices_quarantine и уведомления в ЛК.
        """
        resp = await self.promotions_list(start, end, all_promo=True)
        promos = self._extract_promotions(resp)
        if only_auto:
            promos = [p for p in promos if p.get("type") == "auto"]
        promos = promos[:max_promotions]

        result: list[dict] = []
        total_products = 0
        for p in promos:
            pid = p.get("id") or p.get("promotionID")
            if pid is None:
                continue
            await asyncio.sleep(0.7)  # держим лимит 10 req / 6 сек
            entry = {
                "promotionID": pid, "name": p.get("name"), "type": p.get("type"),
                "startDateTime": p.get("startDateTime"), "endDateTime": p.get("endDateTime"),
            }
            try:
                nom_resp = await self.promotions_nomenclatures(pid, in_action=True)
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                entry.update({
                    "nomenclaturesAvailable": False, "enrolledCount": None, "products": [],
                    "note": ("Состав автоакции недоступен через API (WB формирует сам)"
                             if code == 422 else f"Ошибка получения товаров: HTTP {code}"),
                })
                result.append(entry)
                continue
            items = self._extract_nomenclatures(nom_resp)
            products = []
            for it in items:
                price = it.get("price") or 0
                plan_price = it.get("planPrice") or 0
                drop_pct = round((price - plan_price) / price * 100, 1) if price and plan_price else None
                products.append({
                    "nmID": it.get("id") or it.get("nmID"),
                    "price": price, "planPrice": plan_price, "priceDropPct": drop_pct,
                    "discount": it.get("discount"), "planDiscount": it.get("planDiscount"),
                })
            total_products += len(products)
            entry.update({"nomenclaturesAvailable": True,
                          "enrolledCount": len(products), "products": products})
            result.append(entry)
        return {
            "period": {"start": start, "end": end},
            "onlyAuto": only_auto,
            "promotionsChecked": len(result),
            "enrolledProductsTotal": total_products,
            "promotions": result,
        }

    async def promotions_exit(self, data: list[dict]) -> dict:
        """Выйти из акции = восстановить цену/скидку (отдельного эндпоинта у WB нет).

        data: [{nmID, price, discount}, ...] — целевые (доакционные) значения.
        Под капотом POST /api/v2/upload/task (как prices_set).
        """
        res = await self.prices_upload(data)
        return {"note": "Выход из акции выполняется восстановлением цены/скидки через Prices API.",
                "uploadResult": res}

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
        return await self._send("POST", client, path, params=params, json_body=body)

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

    async def fbw_transit_tariffs(self) -> Any:
        """GET /api/v1/transit-tariffs — транзитные направления (для поставок FBW в регионы)."""
        return await self._get(self._supplies, "/api/v1/transit-tariffs")

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

    async def warehouse_create(self, name: str, address: str | None = None,
                                work_time: str | None = None) -> dict:
        """POST /api/v3/warehouses — создать склад продавца."""
        body: dict[str, Any] = {"name": name}
        if address:
            body["address"] = address
        if work_time:
            body["workTime"] = work_time
        return await self._post(self._marketplace, "/api/v3/warehouses", body)

    async def warehouse_update(self, warehouse_id: int, name: str | None = None,
                                address: str | None = None) -> dict:
        """PUT /api/v3/warehouses/{warehouseId} — обновить склад продавца."""
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if address:
            body["address"] = address
        return await self._put(self._marketplace, f"/api/v3/warehouses/{warehouse_id}", body)

    async def warehouse_delete(self, warehouse_id: int) -> Any:
        """DELETE /api/v3/warehouses/{warehouseId} — удалить склад продавца."""
        return await self._delete(self._marketplace, f"/api/v3/warehouses/{warehouse_id}")

    async def stocks_delete(self, warehouse_id: int, skus: list[str]) -> dict:
        """DELETE /api/v3/stocks/{warehouseId} — удалить записи об остатках по SKU."""
        return await self._send("DELETE", self._marketplace, f"/api/v3/stocks/{warehouse_id}",
                                json_body={"skus": skus})

    async def orders_archive(self, date_from: str, date_to: str | None = None,
                              limit: int = 1000, next_param: int = 0) -> dict:
        """GET /api/marketplace/v3/fbs/orders/archive — архивные FBS-заказы за период."""
        params: dict[str, Any] = {"limit": limit, "next": next_param, "dateFrom": date_from}
        if date_to:
            params["dateTo"] = date_to
        return await self._get(self._marketplace, "/api/marketplace/v3/fbs/orders/archive", params)

    async def supply_order_ids(self, supply_id: str) -> dict:
        """GET /api/marketplace/v3/supplies/{supplyId}/order/ids — ID заданий в поставке FBS."""
        return await self._get(self._marketplace, f"/api/marketplace/v3/supplies/{supply_id}/order/ids")

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

        ⛔ УДАЛЁН Wildberries 15.07.2026 — метод оставлен только на случай, если у
        кого-то ещё отвечает старый контур. Ничем в сервере не вызывается.
        Рабочая замена — finance_sales_report_detailed() (finance-api, нужна
        категория «Финансы» в токене).
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

    async def finance_sales_report_by_id(self, report_id: str,
                                          limit: int = 100000, rrd_id: int = 0) -> dict:
        """POST /api/finance/v1/sales-reports/detailed/{reportId} — детализация конкретного отчёта по ID."""
        return await self._post(self._finance, f"/api/finance/v1/sales-reports/detailed/{report_id}", {
            "limit": limit, "rrdId": rrd_id,
        })

    async def finance_acquiring_list(self, date_from: str, date_to: str,
                                      period: str = "weekly",
                                      limit: int = 100, offset: int = 0) -> dict:
        """POST /api/finance/v1/acquiring/list — список отчётов по издержкам эквайринга."""
        return await self._post(self._finance, "/api/finance/v1/acquiring/list", {
            "dateFrom": date_from, "dateTo": date_to, "period": period,
            "limit": limit, "offset": offset,
        })

    async def finance_acquiring_detailed(self, date_from: str, date_to: str,
                                          limit: int = 100000, rrd_id: int = 0) -> dict:
        """POST /api/finance/v1/acquiring/detailed — детализация издержек эквайринга за период."""
        return await self._post(self._finance, "/api/finance/v1/acquiring/detailed", {
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

    async def analytics_item_rating(self, nm_ids: list[int]) -> dict:
        """POST /api/analytics/v1/item/rating — рейтинг товаров: просмотры, добавления в корзину, заказы.
        [Джем] КРИТИЧНО: низкий рейтинг = проблема карточки или конкурент обошёл. Лимит ≤1000 nmID.
        """
        if len(nm_ids) > 1000:
            nm_ids = nm_ids[:1000]
        return await self._post(self._analytics, "/api/analytics/v1/item/rating", {"nmIds": nm_ids})

    async def analytics_measurement_penalties(self, date_from: str, date_to: str) -> dict:
        """GET /api/analytics/v1/measurement/penalties — удержания за несоответствие фактических габаритов.
        [Джем] КРИТИЧНО: прямые денежные удержания из выручки. YYYY-MM-DD.
        """
        return await self._get(self._analytics, "/api/analytics/v1/measurement/penalties",
                               {"dateFrom": date_from, "dateTo": date_to})

    async def analytics_warehouse_measurements(self, nm_ids: list[int] | None = None) -> dict:
        """GET /api/analytics/v1/warehouse/measurements — результаты замеров товаров на складе WB.
        Показывает как WB измерил товар — основа для удержаний за несоответствие.
        """
        params: dict[str, Any] = {}
        if nm_ids:
            params["nmIds"] = ",".join(str(x) for x in nm_ids)
        return await self._get(self._analytics, "/api/analytics/v1/warehouse/measurements", params)

    async def analytics_sales_funnel_grouped_history(
        self, nm_ids: list[int], date_from: str, date_to: str,
        aggregation_level: str = "day",
    ) -> dict:
        """POST /api/analytics/v3/sales-funnel/grouped/history — воронка продаж по группам/дням."""
        return await self._post(self._analytics, "/api/analytics/v3/sales-funnel/grouped/history", {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": nm_ids,
            "aggregationLevel": aggregation_level,
        })

    async def nm_report(self, nm_ids: list[int] | None = None,
                        date_from: str | None = None, date_to: str | None = None) -> Any:
        """POST /api/v2/nm-report/downloads — создать и скачать отчёт по номенклатуре (task-based).
        Содержит: выручка, заказы, возвраты, среднее в корзине, конверсии по каждому nmID.
        Ждёт готовности (до 3 минут). Отчёт хранится 3 дня.
        """
        body: dict[str, Any] = {}
        if nm_ids:
            body["nmIds"] = nm_ids
        if date_from and date_to:
            body["period"] = {"start": date_from, "end": date_to}
        # Создаём задание
        created = await self._post(self._analytics, "/api/v2/nm-report/downloads", body)
        report_id = (created.get("data") or {}).get("id") or created.get("id")
        if not report_id:
            return created
        # Ждём готовности
        import asyncio as _aio
        for _ in range(36):  # до 3 минут
            await _aio.sleep(5)
            reports = await self._get(self._analytics, "/api/v2/nm-report/downloads")
            items = (reports.get("data") or {}).get("reports") or reports.get("reports") or []
            found = next((r for r in items if r.get("id") == report_id), None)
            if found:
                status = found.get("status")
                if status == "done":
                    dl = await self._get(self._analytics, f"/api/v2/nm-report/downloads/file/{report_id}")
                    return dl
                if status in ("error", "canceled"):
                    return {"report_id": report_id, "status": status}
        return {"report_id": report_id, "status": "timeout",
                "hint": "Отчёт ещё готовится. Вызови позже."}

    async def stocks_report_sizes(self, nm_ids: list[int] | None = None,
                                   date_from: str | None = None, date_to: str | None = None,
                                   limit: int = 100, offset: int = 0) -> dict:
        """POST /api/v2/stocks-report/products/sizes — отчёт об остатках и оборачиваемости по размерам."""
        body: dict[str, Any] = {
            "skipDeletedNm": True,
            "orderBy": {"field": "avgOrders", "mode": "desc"},
            "limit": limit, "offset": offset,
        }
        if nm_ids:
            body["nmIDs"] = nm_ids
        if date_from and date_to:
            body["currentPeriod"] = {"start": date_from, "end": date_to}
        return await self._post(self._analytics, "/api/v2/stocks-report/products/sizes", body)

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

    # ── Доп. инструменты рекламы ─────────────────────────────

    async def advert_payments(self, date_from: str, date_to: str) -> Any:
        """GET /adv/v1/payments — история пополнений рекламного счёта за период (даты YYYY-MM-DD)."""
        return await self._get(self._advert, "/adv/v1/payments", {"from": date_from, "to": date_to})

    async def advert_rename(self, advert_id: int, name: str) -> Any:
        """POST /adv/v0/rename — переименовать кампанию."""
        return await self._post(self._advert, "/adv/v0/rename", {"advertId": advert_id, "name": name})

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

    async def feedbacks_pins_list(self) -> dict:
        """GET /api/feedbacks/v1/pins — закреплённые отзывы (до 3 на nmID)."""
        return await self._get(self._feedbacks, "/api/feedbacks/v1/pins")

    async def feedbacks_pins_count(self) -> dict:
        """GET /api/feedbacks/v1/pins/count — количество закреплённых отзывов."""
        return await self._get(self._feedbacks, "/api/feedbacks/v1/pins/count")

    async def feedbacks_pins_set(self, feedback_ids: list[str]) -> dict:
        """POST /api/feedbacks/v1/pins — закрепить отзывы (≤3 на nmID). Требует Джем."""
        return await self._post(self._feedbacks, "/api/feedbacks/v1/pins", {"feedbackIds": feedback_ids})

    async def feedbacks_pins_delete(self, feedback_ids: list[str]) -> dict:
        """DELETE /api/feedbacks/v1/pins — открепить отзывы."""
        return await self._send("DELETE", self._feedbacks, "/api/feedbacks/v1/pins",
                                json_body={"feedbackIds": feedback_ids})

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
        """Отчёт о реализации через finance-api.

        Содержит все финансовые данные:
        - retail_price, retail_amount — цена и сумма продажи
        - commission_percent — комиссия WB
        - delivery_rub — стоимость логистики
        - storage_fee — стоимость хранения
        - penalty — штрафы
        - additional_payment — доплаты
        - ppvz_for_pay — к оплате продавцу (чистый доход)

        Fallback на старый reportDetailByPeriod убран: WB удалил этот эндпоинт
        15.07.2026, и переход на него давал не «данные постарее», а невнятную
        ошибку вместо понятной причины отказа. Теперь при 401/403 сразу
        говорим, чего не хватает — категории «Финансы» в токене.
        """
        try:
            return await self.finance_sales_report_detailed(date_from, date_to, limit, rrd_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                raise RuntimeError(
                    "Отчёт о реализации недоступен: у токена нет категории «Финансы». "
                    "Выпустите новый токен в ЛК WB (Настройки → Доступ к API), отметив "
                    "категорию «Финансы». Старый эндпоинт reportDetailByPeriod, который "
                    "раньше служил запасным путём, удалён Wildberries 15.07.2026."
                ) from e
            raise

    # ═══════════════════════════════════════════════════════════
    # USERS API — Управление пользователями (common-api)
    # ═══════════════════════════════════════════════════════════

    async def users_list(self) -> dict:
        """GET /api/v1/users (common-api) — список пользователей/сотрудников продавца."""
        return await self._get(self._tariffs, "/api/v1/users")

    async def users_invite(self, email: str, role: str | None = None) -> dict:
        """POST /api/v1/invite (common-api) — создать приглашение пользователя.
        role: admin | manager | analyst (зависит от прав токена).
        """
        body: dict[str, Any] = {"email": email}
        if role:
            body["role"] = role
        return await self._post(self._tariffs, "/api/v1/invite", body)

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

    async def buyer_chat_download(self, file_id: str) -> dict:
        """GET /api/v1/seller/download/{id} — получить файл из чата покупателя."""
        return await self._get(self._buyer_chat, f"/api/v1/seller/download/{file_id}")

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

    async def documents_download_bulk(self, document_ids: list[str]) -> dict:
        """POST /api/v1/documents/download/all — скачать несколько документов одним запросом."""
        return await self._post(self._documents, "/api/v1/documents/download/all",
                                {"ids": document_ids})

    # ═══════════════════════════════════════════════════════════
    # CONTENT API — расширение (объединение карточек, медиафайл, категории)
    # ═══════════════════════════════════════════════════════════

    async def cards_move_nm(self, nm_ids: list[int], target_imt: int | None = None) -> dict:
        """POST /content/v2/cards/moveNm — объединить/разъединить карточки (≤30 nmID).

        target_imt задан → объединить в этот imtID; не задан → разъединить (новые imtID).
        """
        body: dict[str, Any] = {"nmIDs": nm_ids}
        if target_imt is not None:
            body["targetIMT"] = target_imt
        return await self._post(self._content, "/content/v2/cards/moveNm", body)

    async def card_add_nomenclature(self, imt_id: int, cards_to_add: list[dict]) -> dict:
        """POST /content/v2/cards/upload/add — добавить номенклатуру/размер в существующую карточку (imtID)."""
        return await self._post(self._content, "/content/v2/cards/upload/add",
                                {"imtID": imt_id, "cardsToAdd": cards_to_add})

    async def categories_parent(self, locale: str = "ru") -> dict:
        """GET /content/v2/object/parent/all — все родительские категории товаров."""
        return await self._get(self._content, "/content/v2/object/parent/all", {"locale": locale})

    async def media_upload_file(self, nm_id: int, photo_number: int, file_url: str) -> dict:
        """POST /content/v3/media/file — загрузить медиа ФАЙЛОМ (скачиваем по file_url и шлём multipart).

        photo_number: позиция (с 1). Для видео = 1. Чтобы добавить фото — номер больше числа уже загруженных.
        """
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0)) as dl:
            resp = await dl.get(file_url)
            resp.raise_for_status()
            content = resp.content
        headers = {"X-Nm-Id": str(nm_id), "X-Photo-Number": str(photo_number)}
        r = await self._content.post("/content/v3/media/file", headers=headers,
                                     files={"uploadfile": ("upload", content)})
        r.raise_for_status()
        return r.json() if r.content else {}

    # ═══════════════════════════════════════════════════════════
    # MARKETPLACE — маркировка заказов (КИЗ), пропуска, короба (trbx)
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _meta_body(meta_type: str, value: Any) -> dict:
        """Тело для установки метаданных заказа по типу."""
        if meta_type == "sgtin":
            return {"sgtins": value if isinstance(value, list) else [value]}
        return {meta_type: value}  # uin | imei | gtin | expiration

    async def order_meta_get(self, order_id: int) -> dict:
        """GET /api/v3/orders/{id}/meta — метаданные/маркировка заказа FBS (доступные ключи из requiredMeta)."""
        return await self._get(self._marketplace, f"/api/v3/orders/{order_id}/meta")

    async def order_meta_set(self, order_id: int, meta_type: str, value: Any) -> dict:
        """PUT /api/v3/orders/{id}/meta/{type} — задать маркировку: sgtin|uin|imei|gtin|expiration.

        Только для заказа в статусе confirm. sgtin — список Data Matrix; uin=16, imei=15, gtin=13 символов;
        expiration — дата dd.mm.yyyy (≥30 дней).
        """
        return await self._put(self._marketplace, f"/api/v3/orders/{order_id}/meta/{meta_type}",
                               self._meta_body(meta_type, value))

    async def order_meta_delete(self, order_id: int, key: str) -> Any:
        """DELETE /api/v3/orders/{id}/meta?key= — удалить метаданные по ключу (imei|uin|gtin|sgtin)."""
        return await self._delete(self._marketplace, f"/api/v3/orders/{order_id}/meta", {"key": key})

    async def orders_status_history(self, order_ids: list[int]) -> dict:
        """POST /api/v3/orders/status/history — история статусов (трансграничные заказы, ≤100)."""
        return await self._post(self._marketplace, "/api/v3/orders/status/history", {"orders": order_ids})

    async def orders_client_info(self, order_ids: list[int]) -> dict:
        """POST /api/v3/orders/client — данные покупателя (трансграничные заказы из Турции)."""
        return await self._post(self._marketplace, "/api/v3/orders/client", {"orders": order_ids})

    async def supplies_reshipment(self) -> dict:
        """GET /api/v3/supplies/orders/reshipment — заказы, требующие повторной отгрузки."""
        return await self._get(self._marketplace, "/api/v3/supplies/orders/reshipment")

    async def orders_external_stickers(self, order_ids: list[int]) -> dict:
        """POST /api/v3/files/orders/external-stickers — стикеры трансграничной доставки (≤100, статус complete)."""
        return await self._post(self._marketplace, "/api/v3/files/orders/external-stickers", {"orders": order_ids})

    # ── Пропуска на склад ─────────────────────────────────────
    async def passes_offices(self) -> Any:
        """GET /api/v3/passes/offices — офисы, требующие пропуск."""
        return await self._get(self._marketplace, "/api/v3/passes/offices")

    async def passes_list(self) -> Any:
        """GET /api/v3/passes — список действующих пропусков."""
        return await self._get(self._marketplace, "/api/v3/passes")

    async def pass_create(self, first_name: str, last_name: str, car_model: str,
                          car_number: str, office_id: int) -> dict:
        """POST /api/v3/passes — создать пропуск (действует 48 ч)."""
        return await self._post(self._marketplace, "/api/v3/passes", {
            "firstName": first_name, "lastName": last_name,
            "carModel": car_model, "carNumber": car_number, "officeId": office_id,
        })

    async def pass_update(self, pass_id: int, first_name: str, last_name: str, car_model: str,
                          car_number: str, office_id: int) -> Any:
        """PUT /api/v3/passes/{id} — обновить пропуск."""
        return await self._put(self._marketplace, f"/api/v3/passes/{pass_id}", {
            "firstName": first_name, "lastName": last_name,
            "carModel": car_model, "carNumber": car_number, "officeId": office_id,
        })

    async def pass_delete(self, pass_id: int) -> Any:
        """DELETE /api/v3/passes/{id} — удалить пропуск."""
        return await self._delete(self._marketplace, f"/api/v3/passes/{pass_id}")

    # ── Короба поставки FBS (trbx) ────────────────────────────
    async def supply_trbx_list(self, supply_id: str) -> dict:
        """GET /api/v3/supplies/{id}/trbx — короба поставки."""
        return await self._get(self._marketplace, f"/api/v3/supplies/{supply_id}/trbx")

    async def supply_trbx_add(self, supply_id: str, amount: int) -> dict:
        """POST /api/v3/supplies/{id}/trbx — добавить короба (amount 1..1000, только для ПВЗ при сборке)."""
        return await self._post(self._marketplace, f"/api/v3/supplies/{supply_id}/trbx", {"amount": amount})

    async def supply_trbx_delete(self, supply_id: str, trbx_ids: list[str]) -> Any:
        """DELETE /api/v3/supplies/{id}/trbx — удалить короба."""
        return await self._send("DELETE", self._marketplace, f"/api/v3/supplies/{supply_id}/trbx",
                                json_body={"trbxIds": trbx_ids})

    async def supply_trbx_stickers(self, supply_id: str, trbx_ids: list[str], sticker_type: str = "png") -> dict:
        """POST /api/v3/supplies/{id}/trbx/stickers?type= — QR-стикеры коробов (svg|zplv|zplh|png)."""
        return await self._post_with_params(self._marketplace, f"/api/v3/supplies/{supply_id}/trbx/stickers",
                                            params={"type": sticker_type}, body={"trbxIds": trbx_ids})

    # ═══════════════════════════════════════════════════════════
    # DBS — доставка силами продавца (marketplace-api)
    # ═══════════════════════════════════════════════════════════

    async def dbs_orders_new(self) -> dict:
        """GET /api/v3/dbs/orders/new — новые DBS-заказы."""
        return await self._get(self._marketplace, "/api/v3/dbs/orders/new")

    async def dbs_orders(self, limit: int, next_val: int, date_from: int, date_to: int) -> dict:
        """GET /api/v3/dbs/orders — завершённые DBS-заказы (Unix-таймстампы, ≤30 дней, курсор next)."""
        return await self._get(self._marketplace, "/api/v3/dbs/orders", {
            "limit": limit, "next": next_val, "dateFrom": date_from, "dateTo": date_to})

    async def dbs_orders_status(self, order_ids: list[int]) -> dict:
        """POST /api/v3/dbs/orders/status — статусы DBS-заказов (≤1000)."""
        return await self._post(self._marketplace, "/api/v3/dbs/orders/status", {"orders": order_ids})

    async def dbs_orders_client(self, order_ids: list[int]) -> dict:
        """POST /api/v3/dbs/orders/client — данные покупателя (после confirm)."""
        return await self._post(self._marketplace, "/api/v3/dbs/orders/client", {"orders": order_ids})

    async def dbs_orders_delivery_date(self, order_ids: list[int]) -> dict:
        """POST /api/v3/dbs/orders/delivery-date — выбранные покупателем дата/время доставки (≤1000)."""
        return await self._post(self._marketplace, "/api/v3/dbs/orders/delivery-date", {"orders": order_ids})

    async def dbs_groups_info(self, group_ids: list[str]) -> Any:
        """POST /api/v3/dbs/groups/info — стоимость платной доставки по groupId (≤1000)."""
        return await self._post(self._marketplace, "/api/v3/dbs/groups/info", {"groups": group_ids})

    async def dbs_order_action(self, order_id: int, action: str, code: str | None = None) -> Any:
        """PATCH /api/v3/dbs/orders/{id}/{action} — confirm|deliver|receive|reject|cancel.

        receive/reject требуют code (код подтверждения покупателя).
        """
        path = f"/api/v3/dbs/orders/{order_id}/{action}"
        body = {"code": code} if action in ("receive", "reject") and code is not None else None
        return await self._send("PATCH", self._marketplace, path, json_body=body)

    async def dbs_order_meta_get(self, order_id: int) -> dict:
        """GET /api/v3/dbs/orders/{id}/meta — метаданные DBS-заказа."""
        return await self._get(self._marketplace, f"/api/v3/dbs/orders/{order_id}/meta")

    async def dbs_order_meta_set(self, order_id: int, meta_type: str, value: Any) -> Any:
        """PUT /api/v3/dbs/orders/{id}/meta/{type} — sgtin|uin|imei|gtin (статус confirm)."""
        return await self._put(self._marketplace, f"/api/v3/dbs/orders/{order_id}/meta/{meta_type}",
                               self._meta_body(meta_type, value))

    async def dbs_order_meta_delete(self, order_id: int, key: str) -> Any:
        """DELETE /api/v3/dbs/orders/{id}/meta?key= — удалить метаданные."""
        return await self._delete(self._marketplace, f"/api/v3/dbs/orders/{order_id}/meta", {"key": key})

    # ═══════════════════════════════════════════════════════════
    # CLICK-COLLECT — самовывоз (marketplace-api)
    # ═══════════════════════════════════════════════════════════

    async def cc_orders_new(self) -> dict:
        """GET /api/v3/click-collect/orders/new — новые задания самовывоза."""
        return await self._get(self._marketplace, "/api/v3/click-collect/orders/new")

    async def cc_orders(self, limit: int, next_val: int, date_from: int, date_to: int) -> dict:
        """GET /api/v3/click-collect/orders — завершённые задания (Unix-таймстампы, ≤30 дней)."""
        return await self._get(self._marketplace, "/api/v3/click-collect/orders", {
            "limit": limit, "next": next_val, "dateFrom": date_from, "dateTo": date_to})

    async def cc_orders_status(self, order_ids: list[int]) -> dict:
        """POST /api/v3/click-collect/orders/status — статусы заданий."""
        return await self._post(self._marketplace, "/api/v3/click-collect/orders/status", {"orders": order_ids})

    async def cc_orders_client(self, order_ids: list[int]) -> dict:
        """POST /api/v3/click-collect/orders/client — данные покупателя (статусы confirm/prepare)."""
        return await self._post(self._marketplace, "/api/v3/click-collect/orders/client", {"orders": order_ids})

    async def cc_order_identity(self, order_code: str, passcode: str) -> dict:
        """POST /api/v3/click-collect/orders/client/identity — проверка кода покупателя при выдаче."""
        return await self._post(self._marketplace, "/api/v3/click-collect/orders/client/identity",
                                {"orderCode": order_code, "passcode": passcode})

    async def cc_order_action(self, order_id: int, action: str) -> Any:
        """PATCH /api/v3/click-collect/orders/{id}/{action} — confirm|prepare|receive|reject|cancel."""
        return await self._send("PATCH", self._marketplace,
                                f"/api/v3/click-collect/orders/{order_id}/{action}", json_body=None)

    async def cc_order_meta_get(self, order_id: int) -> dict:
        """GET /api/v3/click-collect/orders/{id}/meta — метаданные задания."""
        return await self._get(self._marketplace, f"/api/v3/click-collect/orders/{order_id}/meta")

    async def cc_order_meta_set(self, order_id: int, meta_type: str, value: Any) -> Any:
        """PUT /api/v3/click-collect/orders/{id}/meta/{type} — sgtin|uin|imei|gtin (статус confirm)."""
        return await self._put(self._marketplace, f"/api/v3/click-collect/orders/{order_id}/meta/{meta_type}",
                               self._meta_body(meta_type, value))

    async def cc_order_meta_delete(self, order_id: int, key: str) -> Any:
        """DELETE /api/v3/click-collect/orders/{id}/meta?key= — удалить метаданные."""
        return await self._delete(self._marketplace, f"/api/v3/click-collect/orders/{order_id}/meta", {"key": key})

    # ═══════════════════════════════════════════════════════════
    # ANALYTICS — расширение (доля бренда, регионы, маркировка, поиск)
    # ═══════════════════════════════════════════════════════════

    async def analytics_brand_share(self, parent_id: int, brand: str, date_from: str, date_to: str) -> dict:
        """GET /api/v1/analytics/brand-share — доля бренда в категории (≤365 дней, YYYY-MM-DD)."""
        return await self._get(self._analytics, "/api/v1/analytics/brand-share", {
            "parentId": parent_id, "brand": brand, "dateFrom": date_from, "dateTo": date_to})

    async def analytics_brand_share_brands(self) -> dict:
        """GET /api/v1/analytics/brand-share/brands — бренды продавца (продавались за 90 дней)."""
        return await self._get(self._analytics, "/api/v1/analytics/brand-share/brands")

    async def analytics_brand_share_parents(self, brand: str, date_from: str, date_to: str,
                                            locale: str = "ru") -> dict:
        """GET /api/v1/analytics/brand-share/parent-subjects — родительские категории бренда."""
        return await self._get(self._analytics, "/api/v1/analytics/brand-share/parent-subjects", {
            "brand": brand, "dateFrom": date_from, "dateTo": date_to, "locale": locale})

    async def analytics_region_sale(self, date_from: str, date_to: str) -> dict:
        """GET /api/v1/analytics/region-sale — продажи по регионам (≤31 дня, YYYY-MM-DD)."""
        return await self._get(self._analytics, "/api/v1/analytics/region-sale", {
            "dateFrom": date_from, "dateTo": date_to})

    async def analytics_goods_labeling(self, date_from: str, date_to: str) -> dict:
        """GET /api/v1/analytics/goods-labeling — удержания за отсутствие маркировки (≤31 дня, с фото)."""
        return await self._get(self._analytics, "/api/v1/analytics/goods-labeling", {
            "dateFrom": date_from, "dateTo": date_to})

    async def search_table_details(self, body: dict) -> dict:
        """POST /api/v2/search-report/table/details — поисковая аналитика по товарам (нужна подписка Джем).

        body: {currentPeriod{start,end}, pastPeriod?, orderBy{field,mode}, positionCluster, limit, offset, ...}
        """
        return await self._post(self._analytics, "/api/v2/search-report/table/details", body)

    async def search_table_groups(self, body: dict) -> dict:
        """POST /api/v2/search-report/table/groups — поисковая аналитика по группам (нужна подписка Джем)."""
        return await self._post(self._analytics, "/api/v2/search-report/table/groups", body)

    async def search_product_orders(self, nm_id: int, search_texts: list[str],
                                    date_from: str, date_to: str) -> dict:
        """POST /api/v2/search-report/product/orders — заказы/позиции по запросам для товара (≤7 дней, Джем)."""
        return await self._post(self._analytics, "/api/v2/search-report/product/orders", {
            "period": {"start": date_from, "end": date_to}, "nmId": nm_id, "searchTexts": search_texts})

    # ═══════════════════════════════════════════════════════════
    # FEEDBACKS/QUESTIONS — расширение
    # ═══════════════════════════════════════════════════════════

    async def new_feedbacks_questions(self) -> dict:
        """GET /api/v1/new-feedbacks-questions — флаги непросмотренных отзывов/вопросов."""
        return await self._get(self._feedbacks, "/api/v1/new-feedbacks-questions")

    async def feedbacks_actions(self, feedback_id: str, feedback_valuation: int | None = None,
                                product_valuation: int | None = None) -> Any:
        """POST /api/v1/feedbacks/actions — жалоба на отзыв / проблема с товаром (коды из supplier-valuations)."""
        body: dict[str, Any] = {"id": feedback_id}
        if feedback_valuation is not None:
            body["supplierFeedbackValuation"] = feedback_valuation
        if product_valuation is not None:
            body["supplierProductValuation"] = product_valuation
        return await self._post(self._feedbacks, "/api/v1/feedbacks/actions", body)

    async def question_get(self, question_id: str) -> dict:
        """GET /api/v1/question?id= — один вопрос покупателя по ID."""
        return await self._get(self._feedbacks, "/api/v1/question", {"id": question_id})

    async def feedback_order_return(self, feedback_id: str) -> dict:
        """POST /api/v1/feedbacks/order/return — запрос возврата товара по отзыву (isAbleReturnProductOrders=true)."""
        return await self._post(self._feedbacks, "/api/v1/feedbacks/order/return", {"feedbackId": feedback_id})

    async def feedbacks_count_period(self, date_from: int | None = None, date_to: int | None = None,
                                     is_answered: bool | None = None) -> dict:
        """GET /api/v1/feedbacks/count — число отзывов за период (Unix ts, фильтр isAnswered)."""
        params: dict[str, Any] = {}
        if date_from is not None: params["dateFrom"] = date_from
        if date_to is not None: params["dateTo"] = date_to
        if is_answered is not None: params["isAnswered"] = str(is_answered).lower()
        return await self._get(self._feedbacks, "/api/v1/feedbacks/count", params)

    async def questions_count_period(self, date_from: int | None = None, date_to: int | None = None,
                                     is_answered: bool | None = None) -> dict:
        """GET /api/v1/questions/count — число вопросов за период (Unix ts, фильтр isAnswered)."""
        params: dict[str, Any] = {}
        if date_from is not None: params["dateFrom"] = date_from
        if date_to is not None: params["dateTo"] = date_to
        if is_answered is not None: params["isAnswered"] = str(is_answered).lower()
        return await self._get(self._feedbacks, "/api/v1/questions/count", params)

    # ═══════════════════════════════════════════════════════════
    # ADVERT — расширение (предметы/товары для кампаний)
    # ═══════════════════════════════════════════════════════════

    async def advert_subjects(self) -> Any:
        """GET /adv/v1/supplier/subjects — предметы, доступные для рекламных кампаний."""
        return await self._get(self._advert, "/adv/v1/supplier/subjects")

    async def advert_available_nms(self, subject_ids: list[int]) -> Any:
        """POST /adv/v2/supplier/nms — товары (nm), доступные для кампаний, по ID предметов."""
        return await self._post(self._advert, "/adv/v2/supplier/nms", subject_ids)

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
