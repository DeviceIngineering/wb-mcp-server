"""Диагностика работоспособности MCP и WB API.

Три уровня проверки:
  1. ping      — GET /ping на каждом хосте WB API (доступность + latency)
  2. token     — декодирование JWT: категории доступа, срок действия, sandbox/read-only
  3. probe     — лёгкие реальные запросы по каждой категории API (глубокая проверка)

Плюс: новости WB API (common-api /api/v1/news) и анализ деградаций —
если инструмент стабильно работал и начал стабильно падать, это сигнал
об изменении API.
"""

import base64
import json
import time
import asyncio
from typing import Any

import httpx

# ─── Хосты WB API: категория → base URL ─────────────────────
# Каждый хост поддерживает GET /ping (ответ: {"Status": "OK", "TS": ...})

API_HOSTS: dict[str, str] = {
    "Общее (тарифы, новости)": "https://common-api.wildberries.ru",
    "Контент (карточки)": "https://content-api.wildberries.ru",
    "Цены и скидки": "https://discounts-prices-api.wildberries.ru",
    "Маркетплейс (FBS)": "https://marketplace-api.wildberries.ru",
    "Статистика": "https://statistics-api.wildberries.ru",
    "Аналитика": "https://seller-analytics-api.wildberries.ru",
    "Продвижение (реклама)": "https://advert-api.wildberries.ru",
    "Отзывы и вопросы": "https://feedbacks-api.wildberries.ru",
    "Чат с покупателями": "https://buyer-chat-api.wildberries.ru",
    "Возвраты": "https://returns-api.wildberries.ru",
    "Документы": "https://documents-api.wildberries.ru",
    "Поставки (FBW)": "https://supplies-api.wildberries.ru",
    "Финансы": "https://finance-api.wildberries.ru",
}

# Маска категорий доступа в JWT-токене WB (поле "s", битовая маска).
# Бит N → категория. Источник: dev.wildberries.ru → Общее описание → Авторизация.
TOKEN_SCOPE_BITS: dict[int, str] = {
    1: "Контент",
    2: "Аналитика",
    3: "Цены и скидки",
    4: "Маркетплейс",
    5: "Статистика",
    6: "Продвижение",
    7: "Вопросы и отзывы",
    9: "Чат с покупателями",
    10: "Поставки",
    11: "Возвраты покупателями",
    12: "Документы",
    13: "Финансы",
    16: "Управление пользователями",
}

READ_ONLY_BIT = 30

# Поле acc в JWT — тип токена
TOKEN_ACC_TYPES = {1: "базовый", 2: "тестовый", 3: "персональный", 4: "сервисный"}


# ─── Декодирование токена ────────────────────────────────────

def decode_token(api_token: str) -> dict[str, Any]:
    """Декодировать JWT-токен WB без проверки подписи.

    Возвращает: категории доступа, дату истечения, флаги sandbox/read-only.
    """
    try:
        parts = api_token.split(".")
        if len(parts) != 3:
            return {"valid_format": False, "error": "Не JWT-формат (ожидается 3 части)"}
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as e:
        return {"valid_format": False, "error": f"Ошибка декодирования: {e}"}

    mask = payload.get("s", 0)
    scopes = [name for bit, name in TOKEN_SCOPE_BITS.items() if mask & (1 << bit)]
    read_only = bool(mask & (1 << READ_ONLY_BIT))

    exp = payload.get("exp")
    expires_at = None
    days_left = None
    if exp:
        expires_at = time.strftime("%Y-%m-%d %H:%M", time.localtime(exp))
        days_left = round((exp - time.time()) / 86400, 1)

    return {
        "valid_format": True,
        "seller_id": payload.get("sid", ""),
        "token_type": TOKEN_ACC_TYPES.get(payload.get("acc"), f"неизвестный ({payload.get('acc')})"),
        "scopes": scopes,
        "scope_mask": mask,
        "read_only": read_only,
        "sandbox": bool(payload.get("t", False)),
        "expires_at": expires_at,
        "days_left": days_left,
        "expired": days_left is not None and days_left <= 0,
        "expiring_soon": days_left is not None and 0 < days_left <= 30,
    }


# ─── Ping хостов ─────────────────────────────────────────────

async def ping_host(name: str, base_url: str, api_token: str | None = None) -> dict[str, Any]:
    """GET /ping одного хоста. Возвращает статус и latency."""
    headers = {"Authorization": api_token} if api_token else {}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            r = await client.get(f"{base_url}/ping")
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        body: Any = None
        try:
            body = r.json()
        except Exception:
            body = r.text[:200]
        return {
            "category": name,
            "host": base_url,
            "ok": r.status_code == 200,
            "status_code": r.status_code,
            "latency_ms": latency_ms,
            "response": body,
        }
    except Exception as e:
        return {
            "category": name,
            "host": base_url,
            "ok": False,
            "status_code": None,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "error": f"{type(e).__name__}: {e}",
        }


async def ping_all_hosts(api_token: str | None = None) -> list[dict[str, Any]]:
    """Параллельный ping всех хостов WB API."""
    tasks = [ping_host(name, url, api_token) for name, url in API_HOSTS.items()]
    return list(await asyncio.gather(*tasks))


# ─── Глубокие пробы (реальные лёгкие запросы) ────────────────
# Каждая проба: (категория, описание, корутина-фабрика по клиенту)

def build_probes(client) -> list[tuple[str, str, Any]]:
    """Лёгкие реальные запросы по каждой категории API для проверки токена в бою."""
    return [
        ("Контент", "GET /content/v2/cards/limits", lambda: client.cards_limits()),
        ("Цены и скидки", "GET /api/v2/list/goods/filter (limit=1)", lambda: client.prices_list(limit=1)),
        ("Маркетплейс", "GET /api/v3/warehouses", lambda: client.warehouses_list()),
        ("Статистика", "GET /api/v1/supplier/orders (сегодня)", lambda: client.stats_orders(_today())),
        ("Аналитика", "POST stocks-report/wb-warehouses (limit=1)", lambda: client.analytics_stocks_wb(limit=1)),
        ("Продвижение", "GET /adv/v1/balance", lambda: client.advert_balance()),
        ("Отзывы", "GET /api/v1/feedbacks/count-unanswered", lambda: client.feedbacks_count()),
        ("Вопросы", "GET /api/v1/questions/count-unanswered", lambda: client.questions_count()),
        ("Тарифы", "GET /api/v1/tariffs/box", lambda: client.tariffs_box()),
        ("Документы", "GET /api/v1/documents/categories", lambda: client.documents_categories()),
        ("Финансы", "GET /api/v1/account/balance", lambda: client.finance_balance()),
        ("Поставки FBW", "GET /api/v1/warehouses", lambda: client.fbw_warehouses()),
    ]


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _yesterday() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))


async def run_probes(client) -> list[dict[str, Any]]:
    """Выполнить все пробы параллельно. Возвращает результат по каждой категории."""

    async def _run(category: str, endpoint: str, factory) -> dict[str, Any]:
        start = time.monotonic()
        try:
            await factory()
            return {
                "category": category, "endpoint": endpoint, "ok": True,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
            }
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 429:
                # Лимит запросов — API доступен, токен работает. Не считаем ошибкой.
                return {
                    "category": category, "endpoint": endpoint, "ok": True,
                    "rate_limited": True, "status_code": 429,
                    "latency_ms": round((time.monotonic() - start) * 1000, 1),
                    "note": "429: лимит запросов — API доступен",
                }
            hint = {
                401: "Токен не действует или нет доступа к категории",
                403: "Доступ запрещён (проверьте права токена)",
                404: "Эндпоинт не найден — возможно, WB изменил API!",
            }.get(code, "")
            return {
                "category": category, "endpoint": endpoint, "ok": False,
                "status_code": code, "hint": hint,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": e.response.text[:300],
            }
        except Exception as e:
            return {
                "category": category, "endpoint": endpoint, "ok": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": f"{type(e).__name__}: {e}",
            }

    probes = build_probes(client)
    return list(await asyncio.gather(*[_run(c, e, f) for c, e, f in probes]))


# ─── Новости WB API ──────────────────────────────────────────

async def fetch_api_news(api_token: str, from_date: str | None = None) -> Any:
    """GET /api/communications/v2/news — новости портала WB для продавцов.

    Содержит анонсы изменений API. Используется для раннего обнаружения
    изменений, ломающих интеграцию.
    """
    # Параметр from обязателен — по умолчанию последние 30 дней
    if not from_date:
        from_date = time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400))
    params: dict[str, Any] = {"from": from_date}
    async with httpx.AsyncClient(
        timeout=15.0, headers={"Authorization": api_token},
        base_url=API_HOSTS["Общее (тарифы, новости)"],
    ) as client:
        # v2 — актуальная версия; при 404 пробуем v1 (обратная совместимость)
        for path in ("/api/communications/v2/news", "/api/communications/v1/news"):
            try:
                r = await client.get(path, params=params)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise
        return {"error": "Эндпоинт новостей не найден (404 на v1 и v2)"}


# ─── Полная самодиагностика магазина ─────────────────────────

async def full_diagnostics(shop_id: str, shop_name: str, api_token: str, client) -> dict[str, Any]:
    """Полная диагностика: токен + ping + пробы. Для MCP-инструмента и дашборда."""
    token_info = decode_token(api_token)
    pings, probes = await asyncio.gather(
        ping_all_hosts(api_token),
        run_probes(client),
    )

    ping_fail = [p for p in pings if not p["ok"]]
    probe_fail = [p for p in probes if not p["ok"]]

    warnings = []
    if token_info.get("expired"):
        warnings.append("⛔ ТОКЕН ИСТЁК — все запросы будут падать!")
    elif token_info.get("expiring_soon"):
        warnings.append(f"⚠️ Токен истекает через {token_info['days_left']} дн. — создайте новый заранее")
    if token_info.get("sandbox"):
        warnings.append("⚠️ Токен ПЕСОЧНИЦЫ — данные тестовые")
    if token_info.get("read_only"):
        warnings.append("ℹ️ Токен только на чтение — запись (цены, ответы) недоступна")
    for p in probe_fail:
        if p.get("status_code") == 404:
            warnings.append(f"⛔ {p['category']}: 404 на {p['endpoint']} — возможно, WB изменил API")
        elif p.get("status_code") in (401, 403):
            warnings.append(f"⚠️ {p['category']}: нет доступа ({p['status_code']}) — проверьте права токена")
        else:
            warnings.append(f"⛔ {p['category']}: {p.get('status_code') or p.get('error', 'ошибка')}")
    for p in ping_fail:
        warnings.append(f"⛔ ping {p['category']}: {p.get('status_code') or p.get('error', 'недоступен')}")

    healthy = not ping_fail and not probe_fail and not token_info.get("expired")

    return {
        "shop_id": shop_id,
        "shop_name": shop_name,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "healthy": healthy,
        "warnings": warnings,
        "token": token_info,
        "ping": pings,
        "probes": probes,
    }
