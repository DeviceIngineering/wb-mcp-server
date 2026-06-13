# WB MCP Server v2.1

MCP-сервер для управления несколькими магазинами Wildberries через Claude / OpenClaw.
166 инструментов, мульти-магазин, веб-дашборд, встроенная диагностика WB API.

Эндпоинты приведены в соответствие с актуальной документацией dev.wildberries.ru
(июнь 2026): новая рекламная модель (seacat/normquery), воронка продаж v3,
finance-api, календарь акций, поставки FBW.

**Поддержка нескольких магазинов** — каждый вызов принимает `shop_id`, что позволяет работать с разными аккаунтами WB в одном диалоге.

## 166 инструментов

| Категория | Инструменты | Приоритет |
|-----------|------------|-----------|
| Магазины | wb_list_shops | — |
| Диагностика | wb_diagnostics, wb_token_info, wb_degradations, wb_api_news | P0 |
| Карточки | wb_card_errors, wb_cards_list, wb_card_detail, wb_cards_create, wb_cards_update, wb_cards_trash, wb_cards_limits, wb_barcodes_generate, wb_media_upload, wb_media_upload_file, wb_subjects_search, wb_subject_charcs, wb_categories_parent, wb_directory, wb_tags, wb_tag_link, wb_cards_move_nm, wb_card_add_nomenclature | P0-P2 |
| Цены | wb_prices_list, wb_prices_set, wb_prices_quarantine, wb_prices_club_discount, wb_prices_upload_status, wb_prices_size_list | P0-P2 |
| Акции и автоакции | wb_promotions_list (фильтр type=auto/regular), wb_promotions_auto (только автоакции), wb_promotions_audit (где WB уже добавил товары + ценовой эффект), wb_promotions_details, wb_promotions_products, wb_promotions_add_products, wb_promotion_exit | P0-P1 |
| Финансы | wb_finance_report, wb_finance_balance, wb_seller_info | P0 |
| Реклама | wb_advert_list, wb_advert_create, wb_advert_stats, wb_advert_balance, wb_advert_budget, wb_advert_deposit, wb_advert_costs, wb_advert_pause/start/stop/delete, wb_advert_bids_set, wb_advert_bids_recommendations, wb_advert_clusters, wb_advert_clusters_stats, wb_advert_cluster_bids, wb_advert_minus_phrases, wb_advert_payments, wb_advert_rename | P0-P2 |
| Тарифы | wb_tariffs_box, wb_tariffs_pallet, wb_tariffs_return, wb_tariffs_commission, wb_acceptance_coefficients | P0 |
| Хранение | wb_paid_storage, wb_warehouse_remains | P0-P1 |
| Аналитика | wb_analytics_detail (воронка v3), wb_analytics_history, wb_analytics_stocks, wb_analytics_antifraud, wb_analytics_acceptance, wb_banned_products, wb_deductions, wb_search_report, wb_search_texts, wb_analytics_brand_share(+brands/parents), wb_analytics_region_sale, wb_analytics_goods_labeling, wb_search_table_details, wb_search_table_groups, wb_search_product_orders | P0-P1 |
| Заказы FBS | wb_orders_new, wb_orders_list, wb_orders_status, wb_order_cancel, wb_orders_stickers, wb_supply_create/detail/add_orders/deliver/barcode/delete, wb_order_meta_get/set/delete (КИЗ), wb_passes_list/offices/create/update/delete, wb_supply_trbx_list/add/delete/stickers, wb_orders_status_history, wb_orders_client_info, wb_supplies_reshipment, wb_orders_external_stickers | P0-P2 |
| Заказы DBS (доставка продавцом) | wb_dbs_orders_new, wb_dbs_orders, wb_dbs_orders_status, wb_dbs_orders_client, wb_dbs_orders_delivery_date, wb_dbs_groups_info, wb_dbs_order_action (confirm/deliver/receive/reject/cancel), wb_dbs_order_meta_get/set/delete | P0-P2 |
| Самовывоз (click-collect) | wb_cc_orders_new, wb_cc_orders, wb_cc_orders_status, wb_cc_orders_client, wb_cc_order_identity, wb_cc_order_action (confirm/prepare/receive/reject/cancel), wb_cc_order_meta_get/set/delete | P0-P2 |
| Поставки FBW | wb_fbw_supplies, wb_fbw_supply_detail, wb_fbw_supply_goods, wb_fbw_acceptance_options, wb_fbw_warehouses | P1-P2 |
| Статистика | wb_stats_sales, wb_stats_orders, wb_stats_stocks | P0-P1 |
| Отзывы | wb_feedbacks_list, wb_feedbacks_count, wb_feedbacks_count_period, wb_feedback_reply, wb_seller_rating, wb_new_feedbacks_questions, wb_feedbacks_actions, wb_feedback_order_return | P1-P2 |
| Вопросы | wb_questions_list, wb_questions_count, wb_questions_count_period, wb_question_reply, wb_question_get | P1-P2 |
| Реклама (доп.) | wb_advert_subjects, wb_advert_available_nms | P2 |
| Возвраты | wb_returns_list, wb_return_answer, wb_goods_return_report | P1 |
| Склады | wb_warehouses, wb_supplies_list, wb_stocks_update, wb_stocks_get | P2 |
| Чаты | wb_buyer_chats, wb_chat_events, wb_chat_send | P1 |
| Документы | wb_documents_categories, wb_documents_list, wb_document_download | P1-P2 |

## Диагностика

Цель — мгновенно видеть, что сломалось: токен, конкретная категория API или WB изменил API.

- **Страница `/diagnostics`** — статус по каждому магазину: срок действия токена и его права,
  ping всех 13 хостов WB API, «пробы» (лёгкие реальные запросы по каждой категории),
  история проверок, кнопка «Проверить сейчас».
- **Фоновая автопроверка** каждые `HEALTH_CHECK_INTERVAL_MIN` минут (по умолчанию 30).
- **Детектор деградаций** — если инструмент раньше работал, а теперь стабильно падает,
  он подсвечивается на дашборде как возможное изменение WB API.
- **MCP-инструменты**: `wb_diagnostics` (полная проверка), `wb_token_info`,
  `wb_degradations`, `wb_api_news` (анонсы изменений WB).
- **`GET /api/health`** — JSON-сводка для мониторинга извне.

## Запуск через Docker

```bash
cp .env.example .env   # задать MCP_AUTH_TOKEN при внешнем доступе
docker compose up -d --build
```

После запуска:
- **Dashboard**: http://localhost:8001
- **Диагностика**: http://localhost:8001/diagnostics
- **Магазины**: http://localhost:8001/shops
- **Health**: http://localhost:8001/api/health
- **MCP SSE**: http://localhost:8001/sse

Деплой на отдельный Mac mini и подключение OpenClaw — см. **[DEPLOY.md](DEPLOY.md)**.

## Подключение клиентов

Claude Code:

```bash
claude mcp add --transport sse wildberries "http://<host>:8001/sse" \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8001/sse"]
    }
  }
}
```

OpenClaw / другие MCP-клиенты — SSE URL `http://<host>:8001/sse` + заголовок
`Authorization: Bearer <MCP_AUTH_TOKEN>` (или `?token=...`).

## Добавление магазинов

Открыть http://localhost:8001/shops → «Добавить магазин» → ввести WB API Token → «Проверить».

Ключи шифруются (Fernet) и хранятся в Docker volume `/data`.

Откуда взять токен: Портал продавца WB → **Настройки** → **Доступ к API** → Создать токен
(действителен 180 дней — срок виден на странице диагностики).

## Структура проекта

```
wb-mcp-server/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml          # порт 8001
├── DEPLOY.md                   # деплой на отдельный Mac mini + OpenClaw
└── wb_mcp/
    ├── server.py       # MCP-сервер (166 инструментов, мульти-магазин)
    ├── client.py       # HTTP-клиенты 14 API Wildberries
    ├── app.py          # FastAPI (SSE + веб-интерфейс + авторизация + health-loop)
    ├── diagnostics.py  # ping, JWT-декодер, пробы, новости API
    ├── settings.py     # Управление магазинами и ключами (Fernet)
    ├── stats.py        # Статистика вызовов + история проверок (SQLite)
    └── templates/      # PicoCSS: dashboard, diagnostics, shops
```

## API-разделы Wildberries

| API | Базовый URL |
|-----|-------------|
| Content | content-api.wildberries.ru |
| Marketplace (FBS/DBS/DBW) | marketplace-api.wildberries.ru |
| Supplies (FBW) | supplies-api.wildberries.ru |
| Statistics | statistics-api.wildberries.ru |
| Analytics | seller-analytics-api.wildberries.ru |
| Prices | discounts-prices-api.wildberries.ru |
| Promotions calendar | dp-calendar-api.wildberries.ru |
| Advert | advert-api.wildberries.ru |
| Finance | finance-api.wildberries.ru |
| Feedbacks + Questions | feedbacks-api.wildberries.ru |
| Returns | returns-api.wildberries.ru |
| Tariffs / News / Seller | common-api.wildberries.ru |
| Buyer Chat | buyer-chat-api.wildberries.ru |
| Documents | documents-api.wildberries.ru |

## Известные ограничения WB API (июнь 2026)

- `GET /adv/v3/fullstats` — лимит 3 запроса/мин, период ≤ 31 дня.
- Воронка продаж v3 — лимит 3 запроса/мин; история по дням — максимум за последнюю неделю.
- `/ping` — лимит 3 запроса за 30 сек на хост (фоновая диагностика учитывает).
- Любой ответ 4XX засчитывается WB как 10 запросов к лимиту (с 04.06.2026).
- `reportDetailByPeriod` удаляется 15.07.2026 — сервер уже использует finance-api с fallback.
- Создание поставок FBW через API невозможно (только ЛК) — API информационный.
