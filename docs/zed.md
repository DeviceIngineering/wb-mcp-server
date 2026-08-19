# Zed

**Удалённые MCP-серверы по URL поддерживаются, но слово «SSE» в документации Zed
не встречается**, и транспорт в конфиге не выбирается. Документированные примеры
используют эндпоинт `/mcp`, то есть Streamable HTTP. Будет ли Zed говорить
с SSE-эндпоинтом — **официально не подтверждено**.

Поэтому ниже два варианта: сначала прямой (попробуйте его), затем гарантированный
обходной путь через мост.

## Путь к файлу настроек

| ОС | Путь |
|---|---|
| macOS | `~/.config/zed/settings.json` |
| Linux | `~/.config/zed/settings.json` |
| Windows | официально не подтверждено (по аналогии с темами и раскладками — `%APPDATA%\Zed\`) |

Открыть из редактора: палитра команд → `zed: open settings file`.

Через интерфейс: **Settings → AI → MCP Servers**, либо команда `agent: open settings`
→ раздел **MCP Servers** → **Add Server** (local или remote).

## Вариант 1: напрямую по URL

Ключ верхнего уровня — `context_servers` (не `mcpServers`).

Без авторизации:

```json
{
  "context_servers": {
    "wildberries": {
      "url": "http://localhost:8001/sse"
    }
  }
}
```

С `MCP_AUTH_TOKEN`:

```json
{
  "context_servers": {
    "wildberries": {
      "url": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ВАШ_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

Если заголовка `Authorization` нет, Zed предложит пройти стандартный OAuth-флоу MCP —
наш сервер OAuth не поддерживает, поэтому либо задавайте заголовок, либо запускайте
сервер без `MCP_AUTH_TOKEN`.

## Вариант 2 (гарантированный): мост `mcp-remote`

Локальный stdio-сервер по документированной схеме `command` / `args`:

```json
{
  "context_servers": {
    "wildberries": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8001/sse",
        "--transport", "sse-only",
        "--allow-http"
      ],
      "env": {}
    }
  }
}
```

С токеном добавьте в `args` пару `"--header", "Authorization:${AUTH_HEADER}"`,
а в `env` — `{"AUTH_HEADER": "Bearer ВАШ_MCP_AUTH_TOKEN"}`.

## Проверка

Панель **MCP Servers** в настройках агента показывает статус сервера и его инструменты;
должны появиться `wb_*`. Отдельной процедуры проверки документация не описывает —
**не подтверждено**. Практический способ: спросить ассистента «покажи список моих
магазинов на Wildberries» и посмотреть, появился ли вызов на дашборде
<http://localhost:8001>.

## Оговорки

- Поля `"source": "custom"`, `enabled`/`disabled` в актуальной документации
  отсутствуют — **не подтверждены**.
- Все примеры в документации используют `https://`; работа с `http://localhost`
  явно не оговорена.

Источники: <https://zed.dev/docs/ai/mcp>, <https://zed.dev/faq>
