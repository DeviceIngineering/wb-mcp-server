# Continue.dev

**SSE поддерживается нативно** — `type: sse`. Мост не нужен.

## Путь к файлу конфигурации

| Область | Путь |
|---|---|
| Проект | `.continue/mcpServers/*.yaml` в корне проекта (можно и `.continue/mcpServers/mcp.json`) |
| Пользователь | `~/.continue/config.yaml` |

Различий по операционным системам документация не описывает; отдельный Windows-путь
**не подтверждён** (каталог тот же — `~/.continue`, то есть `%USERPROFILE%\.continue`).

Удобнее всего создать отдельный файл `.continue/mcpServers/wildberries.yaml`.

## Конфигурация

Без авторизации:

```yaml
mcpServers:
  - name: wildberries
    type: sse
    url: http://localhost:8001/sse
```

С `MCP_AUTH_TOKEN`:

```yaml
mcpServers:
  - name: wildberries
    type: sse
    url: http://localhost:8001/sse
    requestOptions:
      headers:
        Authorization: Bearer ВАШ_MCP_AUTH_TOKEN
```

Секреты в Continue подставляются синтаксисом `${{ secrets.ИМЯ }}`:

```yaml
    requestOptions:
      headers:
        Authorization: Bearer ${{ secrets.WB_MCP_TOKEN }}
```

`requestOptions` официально описан как «опции запроса для серверов `sse`
и `streamable-http`, в том же формате, что и `requestOptions` у моделей»,
а внутри него документировано поле `headers`. Готового примера именно
для `mcpServers` в документации нет — конфигурация выше собрана из двух
документированных мест, **проверьте её у себя перед тем, как полагаться**.

Запасной вариант, если заголовок не проходит, — токен в URL:

```yaml
    url: http://localhost:8001/sse?token=ВАШ_MCP_AUTH_TOKEN
```

## Проверка

Инструменты MCP видны в **agent mode** и в выпадающем списке **Tools**.
Найдите там `wb_list_shops` и спросите ассистента: «покажи список моих магазинов
на Wildberries».

## Оговорки

- **MCP работает только в agent mode.** В режимах chat и edit инструменты недоступны —
  это самая частая причина «не вижу инструменты».
- В примерах Continue для SSE-серверов встречается поле `apiKey`; как именно оно
  превращается в заголовок, документация не объясняет — **не подтверждено**.
- SSE в документации Continue помечен как легаси в пользу `streamable-http`.

Источники:
<https://docs.continue.dev/customize/deep-dives/mcp>,
<https://docs.continue.dev/customize/deep-dives/mcp-examples>,
<https://docs.continue.dev/reference>
