# Cline

**SSE поддерживается нативно** — `"type": "sse"`. Мост не нужен.

## Способ 1: через интерфейс

Панель Cline → иконка **MCP Servers** в верхней панели → вкладка **Remote Servers** →
указать имя, URL `http://localhost:8001/sse` и тип транспорта → **Add Server**.
Форма сама запишет корректный JSON.

## Способ 2: правка файла конфигурации

Документация Cline даёт единый путь для всех операционных систем и всех продуктов
Cline (расширение VS Code, CLI, SDK):

| ОС | Путь |
|---|---|
| macOS | `~/.cline/data/settings/cline_mcp_settings.json` |
| Linux | `~/.cline/data/settings/cline_mcp_settings.json` |
| Windows | `C:\Users\<пользователь>\.cline\data\settings\cline_mcp_settings.json` |

Для Cline CLI упоминается также `~/.cline/mcp.json`.
Старый путь внутри `globalStorage/saoudrizwan.claude-dev` в актуальной документации
не упоминается — **не подтверждён**.

Через интерфейс: панель Cline → иконка **MCP Servers** в верхней панели →
вкладка **Remote Servers** → имя, URL, тип транспорта → **Add Server**.
Кнопка **Configure MCP Servers** открывает JSON.

## Конфигурация

Без авторизации:

```json
{
  "mcpServers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

С `MCP_AUTH_TOKEN`:

```json
{
  "mcpServers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ВАШ_MCP_AUTH_TOKEN"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Документация Cline советует держать секреты в переменных окружения, а не в конфиге.
Если это неудобно, сервер принимает токен и в URL: `http://localhost:8001/sse?token=…`.

## Проверка

После добавления убедитесь, что в списке появились инструменты `wb_*`, и вызовите
любой — например, спросите «покажи список моих магазинов на Wildberries».
Вызов появится на дашборде <http://localhost:8001>.

## Оговорки

- **Поле `type` указывать обязательно.** Если его не задать, Cline по умолчанию
  использует легаси-SSE — в нашем случае это как раз то, что нужно, но лучше
  не полагаться на умолчание.
- Документация Cline называет SSE легаси и рекомендует `streamableHttp`;
  наш сервер Streamable HTTP не умеет, поэтому остаётся `sse`.
- `autoApprove: []` означает, что каждый вызов инструмента нужно подтверждать вручную.
  Для инструментов, которые меняют данные (`wb_prices_set`, `wb_advert_*`,
  `wb_cards_update`), подтверждение стоит оставить.

Источники:
<https://docs.cline.bot/mcp/configuring-mcp-servers>,
<https://docs.cline.bot/mcp/connecting-to-a-remote-server>,
<https://docs.cline.bot/getting-started/config>
