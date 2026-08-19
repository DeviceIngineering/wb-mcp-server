# Claude Desktop

**Напрямую к `http://localhost:8001/sse` подключиться нельзя.** Причины две:

1. **Custom connectors** (Настройки → Connectors → Add custom connector) подключаются
   к серверу **из облака Anthropic**, а не с вашего компьютера. В документации прямо
   сказано: сервер должен быть доступен из интернета с IP-диапазонов Anthropic;
   сервер в локальной сети, за VPN или файрволом не подключится. Произвольных
   заголовков в этой форме нет — только OAuth Client ID / Secret.
2. **Локальный `claude_desktop_config.json`** официально документирован
   **только для stdio-серверов** (`command` / `args` / `env`). Записи вида
   `"type": "sse"` + `"url"` для пользовательского конфига официально не подтверждены.

Поэтому рабочих варианта два: мост `mcp-remote` (рекомендуется) или локальный stdio-режим.

## Путь к файлу конфигурации

| ОС | Путь |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | официально не указан — **не подтверждено** (Linux-сборка в бете) |

Через интерфейс: меню **Claude** в системной строке → **Settings…** → вкладка
**Developer** → **Edit Config**.

## Вариант 1 (рекомендуется): мост `mcp-remote`

Сохраняет всё, ради чего сервер и поднимается: мульти-магазин, шифрование токенов,
дашборд, диагностику. Нужен Node.js 18+.

Без авторизации:

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8001/sse",
        "--transport", "sse-only",
        "--allow-http"
      ]
    }
  }
}
```

С `MCP_AUTH_TOKEN`:

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://localhost:8001/sse",
        "--transport", "sse-only",
        "--allow-http",
        "--header", "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer ВАШ_MCP_AUTH_TOKEN"
      }
    }
  }
}
```

Почему `Authorization:${AUTH_HEADER}` без пробела: Claude Desktop под Windows ломает
аргументы с пробелами, поэтому README `mcp-remote` советует прятать пробел
внутрь переменной окружения.

Обходной путь через `mcp-remote` официальной документацией Anthropic не описан —
он опирается на документированную stdio-схему и на README самого моста.

## Вариант 2: локальный stdio-режим

Пакет содержит stdio-точку входа `wb-mcp`. Мульти-магазина, дашборда и шифрования
в этом режиме нет, токен WB лежит в конфиге открытым текстом — зато не нужны
ни Docker, ни Node.

```bash
git clone https://github.com/DeviceIngineering/wb-mcp-server.git
cd wb-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install .
which wb-mcp    # запомните полный путь
```

```json
{
  "mcpServers": {
    "wildberries": {
      "command": "/полный/путь/до/.venv/bin/wb-mcp",
      "env": {
        "WB_API_TOKEN": "ВАШ_ТОКЕН_WILDBERRIES"
      }
    }
  }
}
```

`command: "wb-mcp"` без пути сработает, только если каталог виртуального окружения
есть в `PATH` у процесса Claude Desktop, — надёжнее указать абсолютный путь.
Магазин в этом режиме один, с идентификатором `default`.

## Проверка

1. Полностью перезапустите приложение (закрыть, а не свернуть).
2. Кнопка **+** под полем ввода → **Connectors** → **Manage connectors** → должен
   появиться сервер и список его инструментов.
3. Спросите: «покажи список моих магазинов на Wildberries».

Логи:

```bash
# macOS
tail -n 20 -f ~/Library/Logs/Claude/mcp*.log
```

На Windows — `%APPDATA%\Claude\logs`.

## Оговорки

- Claude Code (CLI) и Claude Desktop читают разные файлы. На macOS/WSL есть импорт:
  `claude mcp add-from-claude-desktop`.
- Залипшие OAuth-данные `mcp-remote` лечатся удалением `~/.mcp-auth`.
- Сам `mcp-remote` его авторы называют экспериментальным и временным — до появления
  нативной поддержки удалённых серверов в клиентах.

Источники:
<https://modelcontextprotocol.io/docs/2026-07-28/develop/connect-local-servers>,
<https://support.claude.com/en/articles/11175166-getting-started-with-custom-connectors-using-remote-mcp>,
<https://github.com/geelen/mcp-remote>
