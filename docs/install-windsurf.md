# Windsurf (Cascade)

**SSE в списке поддерживаемых транспортов есть.** Мост не нужен.

Официальная страница документации Windsurf теперь редиректит на документацию
Devin Desktop — это то же приложение и тот же формат конфигурации.

## Путь к файлу конфигурации

| ОС | Путь |
|---|---|
| macOS | `~/.codeium/windsurf/mcp_config.json` |
| Linux | `~/.codeium/windsurf/mcp_config.json` |
| Windows | `~/.codeium/windsurf/mcp_config.json` (отдельного Windows-варианта документация не приводит) |

Через интерфейс: **Settings → Cascade → MCP Servers**, либо иконка **MCPs**
в правом верхнем углу панели Cascade.

## Конфигурация

Для удалённого сервера нужно поле `serverUrl` (допустимо и `url`).

Без авторизации:

```json
{
  "mcpServers": {
    "wildberries": {
      "serverUrl": "http://localhost:8001/sse"
    }
  }
}
```

С `MCP_AUTH_TOKEN` — Windsurf раскрывает `${env:ИМЯ}` и `${file:/путь}`:

```json
{
  "mcpServers": {
    "wildberries": {
      "serverUrl": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ${env:WB_MCP_TOKEN}"
      }
    }
  }
}
```

Вариант без переменных окружения — токен в URL (сервер принимает `?token=`):

```json
{
  "mcpServers": {
    "wildberries": {
      "serverUrl": "http://localhost:8001/sse?token=ВАШ_MCP_AUTH_TOKEN"
    }
  }
}
```

## Проверка

**Settings → Cascade → MCP Servers** — у сервера должен появиться список инструментов.
Затем спросите ассистента: «покажи список моих магазинов на Wildberries»; вызов
отобразится на дашборде <http://localhost:8001>.

## Оговорки

- **Лимит 100 инструментов** на все активные MCP-серверы в Cascade. У WB MCP Server
  их 202 — часть будет отброшена. Это самое важное ограничение для данного клиента:
  заранее отключите остальные MCP-серверы, а список инструментов сузьте средствами
  Cascade, если такая настройка доступна в вашей версии.
- Документация перечисляет SSE среди поддерживаемых транспортов, но **как явно выбрать
  SSE вместо Streamable HTTP (поле `type`/`transport`), не описано — не подтверждено**.
  Если клиент попытается говорить Streamable HTTP, подключение не поднимется;
  запасной вариант — мост:

  ```json
  {
    "mcpServers": {
      "wildberries": {
        "command": "npx",
        "args": ["-y", "mcp-remote", "http://localhost:8001/sse",
                 "--transport", "sse-only", "--allow-http"]
      }
    }
  }
  ```

- Корпоративным пользователям MCP нужно включать вручную в настройках.

Источник: <https://docs.devin.ai/desktop/cascade/mcp>
(редирект с <https://docs.windsurf.com/windsurf/cascade/mcp>)
