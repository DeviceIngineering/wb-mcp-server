# JetBrains AI Assistant (IDEA, PyCharm и другие IDE)

**SSE поддерживается** — документация JetBrains прямо говорит: «AI Assistant also
supports the SSE transport mechanism for legacy MCP servers». Мост не нужен.

## Где настраивается

**Settings → Tools → AI Assistant → Model Context Protocol (MCP)**,
либо в чате ввести `/` → **Add Command**.

В диалоге добавления есть варианты ручной настройки для **SSE**, **Stdio**
и **HTTP Stream**, а также поля «Working directory», «Server level» (global или project)
и переопределение переменных окружения для конкретного запуска.

**Путь к файлу конфигурации на диске в официальной документации не описан** —
конфигурация хранится в настройках IDE, JSON вводится в диалоге.
Пути вроде `.aiassistant/mcp.json` встречаются только в сторонних статьях —
**не подтверждено**.

## Конфигурация

Официальный пример для SSE — только поле `url`:

```json
{
  "mcpServers": {
    "wildberries": {
      "url": "http://localhost:8001/sse"
    }
  }
}
```

Эндпоинт `POST /messages` указывать не нужно: клиент получает его из первого
SSE-события.

### Если задан `MCP_AUTH_TOKEN`

**Поддержка произвольных заголовков (`headers`, `Authorization`) в AI Assistant
официальной документацией не подтверждена** — для серверов с `url` задокументировано
только поле `url`. Поэтому рабочий способ — передать токен параметром запроса,
это сервер умеет:

```json
{
  "mcpServers": {
    "wildberries": {
      "url": "http://localhost:8001/sse?token=ВАШ_MCP_AUTH_TOKEN"
    }
  }
}
```

Токен при этом хранится в настройках IDE открытым текстом и попадает в логи —
приемлемо в доверенной сети, нежелательно в общей.

Альтернатива, если такой способ не устраивает, — stdio-мост:

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8001/sse",
               "--transport", "sse-only", "--allow-http",
               "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer ВАШ_MCP_AUTH_TOKEN" }
    }
  }
}
```

## Junie CLI

У Junie отдельные файлы конфигурации:

| Область | Путь |
|---|---|
| Проект | `.junie/mcp/mcp.json` |
| Пользователь | `~/.junie/mcp/mcp.json` |

Junie документирует удалённые серверы как «connect to a hosted server via HTTP/HTTPS»
и **поддерживает `headers`**:

```json
{
  "mcpServers": {
    "wildberries": {
      "url": "http://localhost:8001/sse",
      "headers": { "Authorization": "Bearer ВАШ_MCP_AUTH_TOKEN" }
    }
  }
}
```

Разделения SSE и Streamable HTTP в документации Junie нет, поэтому **поддержка
именно SSE в Junie CLI не подтверждена**. Если не заработает — используйте мост
`mcp-remote` через `command`/`args`.

Проверка в Junie: команда `/mcp`.

## Проверка в AI Assistant

После сохранения нажмите иконку статуса сервера — откроется список предоставляемых
им инструментов. Есть список `wb_*` — соединение установлено.
Затем спросите ассистента: «покажи список моих магазинов на Wildberries».

## Оговорки

- Запрос на поддержку OAuth2-аутентификации MCP-подключений есть в трекере JetBrains
  (YouTrack LLM-25012); его статус не проверялся — **не подтверждено**.
- Документация относится к AI Assistant 2026.2; в более старых версиях набор
  транспортов может отличаться.

Источники:
<https://www.jetbrains.com/help/ai-assistant/mcp.html>,
<https://www.jetbrains.com/help/ai-assistant/configure-an-mcp-server.html>,
<https://junie.jetbrains.com/docs/junie-cli-mcp-configuration.html>
