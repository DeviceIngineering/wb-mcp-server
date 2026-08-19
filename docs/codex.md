# Codex CLI (OpenAI)

**SSE не поддерживается.** Codex знает ровно два вида MCP-серверов: локальные stdio
и Streamable HTTP. Поля `transport` или `type` в схеме конфигурации нет; при наличии
`command` запись считается stdio-сервером, при наличии `url` — Streamable HTTP.
Наш сервер отдаёт SSE, поэтому нужен мост **`mcp-remote`**, работающий как stdio-сервер.

## Путь к файлу конфигурации

| ОС | Путь |
|---|---|
| macOS | `~/.codex/config.toml` |
| Linux | `~/.codex/config.toml` |
| Windows | `%USERPROFILE%\.codex\config.toml` |

Каталог переопределяется переменной `CODEX_HOME`. Отдельной таблицы путей по ОС
в документации нет — **не подтверждено дословно**.

Формат — TOML, не JSON.

## Конфигурация

Без авторизации:

```toml
[mcp_servers.wildberries]
command = "npx"
args = ["-y", "mcp-remote", "http://localhost:8001/sse", "--transport", "sse-only", "--allow-http"]
```

С `MCP_AUTH_TOKEN` — токен передаётся через переменную окружения, чтобы не хранить
его в конфиге и не спотыкаться о пробел в значении заголовка:

```toml
[mcp_servers.wildberries]
command = "npx"
args = [
  "-y", "mcp-remote",
  "http://localhost:8001/sse",
  "--transport", "sse-only",
  "--allow-http",
  "--header", "Authorization:${AUTH_HEADER}",
]
env_vars = ["AUTH_HEADER"]
```

```bash
export AUTH_HEADER="Bearer ВАШ_MCP_AUTH_TOKEN"
```

Разбор флагов моста:

| Флаг | Зачем |
|---|---|
| `-y` | не спрашивать подтверждение установки пакета |
| `--transport sse-only` | по умолчанию мост сначала пробует Streamable HTTP, которого у нас нет |
| `--allow-http` | разрешить незашифрованный `http://` — для `localhost` обязателен |
| `--header` | заголовок авторизации; пробел после двоеточия опущен намеренно |

Нужен Node.js 18+.

## Если сервер когда-нибудь научится Streamable HTTP

Тогда мост не понадобится, и конфигурация станет такой (сейчас **не работает**):

```toml
[mcp_servers.wildberries]
url = "http://localhost:8001/mcp"
bearer_token_env_var = "WB_MCP_TOKEN"
```

Для Bearer-авторизации Codex документирует три способа: `bearer_token_env_var`,
статические `http_headers` и `env_http_headers`. Поле `bearer_token` в открытом
виде схемой **отвергается**.

## Проверка

```bash
codex mcp list
```

Затем спросите ассистента: «покажи список моих магазинов на Wildberries» —
и убедитесь, что вызов появился на дашборде <http://localhost:8001>.

Мост можно проверить и отдельно от Codex:

```bash
npx -p mcp-remote@latest mcp-remote-client http://localhost:8001/sse --allow-http
```

## Оговорки

- Вариант `experimental_use_rmcp_client = true` + `bearer_token = "..."`, который
  встречается в сторонних руководствах, текущей схемой конфигурации не подтверждается:
  такого флага в схеме нет, а `bearer_token` отвергается валидацией.
- Залипшие OAuth-данные моста удаляются вместе с каталогом `~/.mcp-auth`.
- Отладочный лог моста: добавьте `--debug`, лог пишется
  в `~/.mcp-auth/{хеш_сервера}_debug.log`.

Источники:
<https://developers.openai.com/codex/mcp>,
<https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json>,
<https://github.com/geelen/mcp-remote>
