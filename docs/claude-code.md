# Claude Code

**SSE поддерживается нативно.** Мост не нужен.

## Одной командой

```bash
claude mcp add --transport sse wildberries http://localhost:8001/sse
```

С авторизацией (если в `.env` задан `MCP_AUTH_TOKEN`):

```bash
claude mcp add --transport sse wildberries http://localhost:8001/sse \
  --header "Authorization: Bearer ВАШ_MCP_AUTH_TOKEN"
```

Сервер на другой машине — подставьте её адрес: `http://192.168.1.50:8001/sse`
или `http://имя-мака.local:8001/sse`.

Короткие формы флагов: `-t` вместо `--transport`, `-H` вместо `--header`.

## Через файл конфигурации

| Область | Где хранится | Кто видит |
|---|---|---|
| `local` (по умолчанию) | `~/.claude.json` | только текущий проект |
| `project` | `.mcp.json` в корне проекта | все, кто клонирует репозиторий |
| `user` | `~/.claude.json` | все проекты |

Пути одинаковы на macOS и Linux. Отдельные пути для Windows в документации Claude Code
не приведены — **не подтверждено**.

Без авторизации:

```json
{
  "mcpServers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse"
    }
  }
}
```

С авторизацией — токен лучше не хранить в файле, а подставлять из окружения
(Claude Code раскрывает `${VAR}` в полях `command`, `args`, `env`, `url`, `headers`):

```json
{
  "mcpServers": {
    "wildberries": {
      "type": "sse",
      "url": "http://localhost:8001/sse",
      "headers": {
        "Authorization": "Bearer ${WB_MCP_TOKEN}"
      }
    }
  }
}
```

```bash
export WB_MCP_TOKEN=ВАШ_MCP_AUTH_TOKEN
```

## Проверка

```bash
claude mcp list          # ожидается: wildberries ... ✔ Connected
claude mcp get wildberries
```

В интерактивной сессии — команда `/mcp`. Затем спросите: «покажи список моих магазинов
на Wildberries» — должен сработать `wb_list_shops`, а вызов появится
на дашборде <http://localhost:8001>.

## Оговорки

- Запись с `url`, но без `type`, считается ошибкой конфигурации, и сервер молча
  пропускается. Поле `"type": "sse"` обязательно.
- Пробелы и переводы строки в значении заголовка не обрезаются — Claude Code выдаст
  предупреждение `Leading or trailing whitespace in: headers.Authorization`.
- Серверы из проектного `.mcp.json` требуют интерактивного подтверждения при первом
  запуске (`⏸ Pending approval`). Сбросить решения: `claude mcp reset-project-choices`.
- Для SSE/HTTP-серверов действует таймаут 60 секунд до первого байта ответа. Тяжёлые
  отчёты WB (воронка продаж, `fullstats`) в него иногда не укладываются — сужайте период.
- Транспорт SSE в документации Claude Code помечен как устаревший в пользу Streamable HTTP.
  Наш сервер Streamable HTTP не умеет, поэтому используем SSE.

Источник: <https://code.claude.com/docs/en/mcp>
