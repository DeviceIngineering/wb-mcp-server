# Подключение MCP-клиентов

WB MCP Server отдаёт MCP по транспорту **SSE**:

| | |
|---|---|
| Поток событий | `GET http://<host>:8001/sse` |
| Сообщения клиента | `POST http://<host>:8001/messages` (адрес клиент получает сам из первого SSE-события) |
| Авторизация | заголовок `Authorization: Bearer <MCP_AUTH_TOKEN>` **или** `?token=<MCP_AUTH_TOKEN>` |
| Без `MCP_AUTH_TOKEN` | авторизация не требуется |

В конфиге клиента указывается **только** URL `/sse`. Путь `/messages` прописывать никуда
не нужно: по спецификации SSE-транспорта сервер сам сообщает его первым событием.

Перед настройкой любого клиента убедитесь, что сервер поднят:

```bash
curl -s http://localhost:8001/api/health
# {"status":"ok","auth_enabled":false,...}
curl -sN --max-time 3 http://localhost:8001/sse | head -2
# event: endpoint
# data: /messages?session_id=...
```

Если `auth_enabled: true`, а токен не передан, `GET /sse` вернёт `401 Unauthorized`.

## Сначала команда, потом файл

Если у клиента есть команда, которая настраивает подключение сама, в инструкции она идёт
первой, а правка JSON — вторым способом. Одну строку в терминале доводят до конца чаще,
чем поиск файла конфигурации на трёх операционных системах.

| Клиент | Команда |
|---|---|
| Claude Code | `claude mcp add --transport sse wildberries http://localhost:8001/sse` |
| Gemini CLI | `gemini mcp add --transport sse wildberries http://localhost:8001/sse` |
| Codex CLI | `codex mcp add wildberries -- npx -y mcp-remote http://localhost:8001/sse --transport sse-only --allow-http` |
| VS Code | палитра команд → `MCP: Add Server` |
| Cursor, Cline, Windsurf, Zed, JetBrains | форма добавления сервера в интерфейсе |
| Continue.dev, Claude Desktop | только файл конфигурации |

## Совместимость

| Клиент | Как подключается | Заголовок `Authorization` | Инструкция |
|---|---|---|---|
| Claude Code | нативно, `--transport sse` | да | [claude-code.md](claude-code.md) |
| Cursor | нативно, `url` в `mcp.json` | да | [cursor.md](cursor.md) |
| Windsurf | нативно, `serverUrl` | да | [windsurf.md](windsurf.md) |
| VS Code (Copilot) | нативно, `"type": "sse"` | да | [vscode-copilot.md](vscode-copilot.md) |
| Cline | нативно, `"type": "sse"` | да | [cline.md](cline.md) |
| Continue.dev | нативно, `type: sse` | да, через `requestOptions.headers` | [continue.md](continue.md) |
| Gemini CLI | нативно, `url` | да | [gemini-cli.md](gemini-cli.md) |
| JetBrains AI Assistant | нативно, SSE как legacy | не документирован → `?token=` | [jetbrains.md](jetbrains.md) |
| Zed | по `url`; SSE официально не заявлен | да | [zed.md](zed.md) |
| Claude Desktop | только stdio → мост `mcp-remote` | через мост | [claude-desktop.md](claude-desktop.md) |
| Codex CLI | SSE не поддерживает → мост `mcp-remote` | через мост | [codex.md](codex.md) |

Формулировки «нативно» и «не поддерживает» взяты из официальной документации клиентов;
там, где документация молчит, это отмечено прямо в соответствующем файле.

## Мост `mcp-remote`

Клиентам, которые умеют только stdio, нужен мост
[`mcp-remote`](https://github.com/geelen/mcp-remote) — он превращает удалённый
SSE-сервер в локальный stdio-процесс. Нужен Node.js 18+.

```bash
npx -y mcp-remote http://localhost:8001/sse --transport sse-only --allow-http
```

- `--transport sse-only` — по умолчанию мост пробует Streamable HTTP первым;
  наш сервер его не умеет, поэтому лишнюю попытку лучше отключить.
- `--allow-http` — разрешить незашифрованный `http://`; для `localhost` обязателен.
- `--header "Authorization:${AUTH_HEADER}"` — заголовок авторизации. Пробел после
  двоеточия опущен намеренно: часть клиентов ломает аргументы с пробелами, поэтому
  пробел прячут внутрь переменной окружения (`AUTH_HEADER=Bearer <токен>`).

Проверить мост отдельно от клиента:

```bash
npx -p mcp-remote@latest mcp-remote-client http://localhost:8001/sse --allow-http
```

## Как понять, что подключение работает

1. В списке инструментов клиента появились `wb_*` (их 202).
2. Спросите ассистента: «покажи список моих магазинов на Wildberries» — должен
   вызваться `wb_list_shops`.
3. Откройте дашборд <http://localhost:8001> — вызов появится в таблице «Последние вызовы».

Если инструменты не появились, смотрите логи сервера (`docker compose logs -f`)
и логи MCP у самого клиента — они указаны в каждой инструкции.

## Что даёт удалённый сервер вместо локального stdio

Сервер можно запустить и как stdio-процесс (`wb-mcp`), но тогда теряются
мульти-магазин через веб-интерфейс, шифрование токенов в томе, дашборд и фоновая
диагностика, а токен WB приходится класть в конфиг клиента открытым текстом.
Вариант со stdio описан в [claude-desktop.md](claude-desktop.md) как запасной.
