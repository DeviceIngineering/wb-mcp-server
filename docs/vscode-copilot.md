# VS Code (GitHub Copilot, agent mode)

**SSE поддерживается нативно** — тип `sse` есть в схеме конфигурации наряду
со `stdio` и `http`. Мост не нужен.

## Способ 1: через палитру команд

`Cmd/Ctrl+Shift+P` → **MCP: Add Server** — VS Code проведёт по шагам (тип сервера, URL,
имя, область видимости) и сам запишет корректный JSON. Это быстрее и надёжнее, чем
искать файл руками.

## Способ 2: правка файла конфигурации

| Область | Путь |
|---|---|
| Проект | `.vscode/mcp.json` в корне рабочей папки (одинаково на macOS, Linux, Windows) |
| Пользователь | файл `mcp.json` в каталоге профиля — открывается командой `MCP: Open User Configuration` |

Точные пути пользовательского `mcp.json` по операционным системам в документации
VS Code не приведены — **не подтверждено**, открывайте его командой из палитры.

Команды палитры (`Cmd/Ctrl+Shift+P`):
`MCP: Add Server`, `MCP: List Servers`, `MCP: Open Workspace Folder Configuration`,
`MCP: Open User Configuration`, `MCP: Show Output`.

## Конфигурация

Ключ верхнего уровня — `servers` (не `mcpServers`).

Без авторизации:

```json
{
  "servers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse"
    }
  }
}
```

С `MCP_AUTH_TOKEN` — документация прямо требует не хардкодить секреты, а спрашивать
их через `inputs`:

```json
{
  "servers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ${input:wb-mcp-token}"
      }
    }
  },
  "inputs": [
    {
      "type": "promptString",
      "id": "wb-mcp-token",
      "description": "MCP_AUTH_TOKEN сервера WB MCP",
      "password": true
    }
  ]
}
```

VS Code спросит токен при первом подключении и запомнит его в хранилище секретов.

## Проверка

1. `MCP: List Servers` → выбрать `wildberries`.
2. `MCP: Show Output` — там видно, поднялось ли соединение.
3. В agent mode откройте список инструментов — должны появиться `wb_*`.
4. Спросите: «покажи список моих магазинов на Wildberries».

## Оговорки

- Перед первым запуском сервер нужно **«доверить»** (trust) в подсказке VS Code.
- SSE в документации VS Code описан как легаси и фолбэк: сначала пробуется
  Streamable HTTP, при неудаче — SSE. Явно указанный `"type": "sse"` снимает вопрос.
- Sandboxing MCP-серверов недоступен на Windows.
- Файл `.vscode/mcp.json` попадает в репозиторий — не кладите в него токен,
  для этого и нужны `inputs`.

Источники:
<https://code.visualstudio.com/docs/agents/reference/mcp-configuration>,
<https://code.visualstudio.com/docs/copilot/customization/mcp-servers>
