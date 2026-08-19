# Gemini CLI

**SSE поддерживается нативно.** Мост не нужен.

В Gemini CLI транспорт выбирается полем: `url` — это SSE, `httpUrl` — Streamable HTTP.
Наш сервер умеет только SSE, значит нужно `url`.

## Одной командой

```bash
gemini mcp add --transport sse wildberries http://localhost:8001/sse
```

С авторизацией:

```bash
gemini mcp add --transport sse \
  --header "Authorization: Bearer ВАШ_MCP_AUTH_TOKEN" \
  wildberries http://localhost:8001/sse
```

## Путь к файлу конфигурации

| Область | Путь |
|---|---|
| Пользователь | `~/.gemini/settings.json` |
| Проект | `.gemini/settings.json` в корне проекта |

На Windows `~` — это `%USERPROFILE%`; отдельного Windows-пути документация
не приводит — **не подтверждено**.

## Конфигурация

Без авторизации:

```json
{
  "mcpServers": {
    "wildberries": {
      "url": "http://localhost:8001/sse",
      "timeout": 600000,
      "trust": false
    }
  }
}
```

С `MCP_AUTH_TOKEN`:

```json
{
  "mcpServers": {
    "wildberries": {
      "url": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ВАШ_MCP_AUTH_TOKEN"
      },
      "timeout": 600000,
      "trust": false
    }
  }
}
```

Поля, документированные для всех транспортов:

| Поле | Значение |
|---|---|
| `headers` | произвольные HTTP-заголовки |
| `env` | переменные окружения, поддерживается подстановка `$ИМЯ` |
| `timeout` | таймаут в миллисекундах, по умолчанию 600000 |
| `trust` | по умолчанию `false` — вызовы инструментов подтверждаются вручную |

`trust: false` стоит оставить: среди 202 инструментов есть меняющие данные
(`wb_prices_set`, `wb_cards_update`, `wb_advert_*`).

## Проверка

Команда `/mcp` в сессии — покажет список серверов, статус `CONNECTED`/`DISCONNECTED`,
найденные инструменты и стадию discovery. Затем спросите: «покажи список моих магазинов
на Wildberries».

## Оговорки

- Не указывайте `url` и `httpUrl` одновременно.
- Ограничений на `http://` без TLS документация не заявляет.
- Одновременно указывать `--transport sse` и передавать `httpUrl` смысла нет —
  сервер Streamable HTTP не поддерживает.

Источник:
<https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>
