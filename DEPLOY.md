# Деплой WB MCP Server на отдельный Mac mini

Сервер — самодостаточный Docker-сервис. Все данные (магазины, токены, статистика,
история диагностики) живут в Docker-томе `wb_data`.

## 1. Установка на новый Mac mini

Требования: Docker Desktop (или OrbStack).

```bash
# На старом маке: упаковать проект (без данных)
cd ~/Documents/myProjects/cowork/FBO
tar -czf wb-mcp-server.tar.gz --exclude='.git' --exclude='__pycache__' wb-mcp-server

# Передать на новый Mac mini
scp wb-mcp-server.tar.gz user@<новый-мак>:~/

# На новом Mac mini:
tar -xzf wb-mcp-server.tar.gz && cd wb-mcp-server
cp .env.example .env
# Сгенерировать токен авторизации и вписать в .env → MCP_AUTH_TOKEN
openssl rand -hex 32

docker compose up -d --build
```

Проверка: `curl http://localhost:8001/api/health` → `{"status": "ok", ...}`

## 2. Перенос магазинов со старого сервера

Токены хранятся зашифрованными, ключ шифрования — в том же томе,
поэтому переносим том целиком:

```bash
# На старом маке:
docker run --rm -v wb-mcp-server_wb_data:/data -v $(pwd):/backup alpine \
  tar -czf /backup/wb_data.tar.gz -C /data .
scp wb_data.tar.gz user@<новый-мак>:~/wb-mcp-server/

# На новом Mac mini (контейнер остановить на время восстановления):
docker compose down
docker run --rm -v wb-mcp-server_wb_data:/data -v $(pwd):/backup alpine \
  sh -c "cd /data && tar -xzf /backup/wb_data.tar.gz"
docker compose up -d
```

Либо просто заново добавить магазины через веб-UI: `http://<новый-мак>:8001/shops`.

## 3. Автозапуск после перезагрузки Mac mini

`restart: unless-stopped` в docker-compose уже поднимает контейнер при старте
Docker. Остаётся включить автозапуск Docker Desktop:
**Docker Desktop → Settings → General → Start Docker Desktop when you sign in**.

Также в macOS: **Системные настройки → Пользователи → Объекты входа** — Docker должен быть в списке.

## 4. Подключение OpenClaw

OpenClaw подключается к MCP по SSE. В конфигурации MCP-серверов OpenClaw
(например `~/.openclaw/mcporter.json` или раздел `mcpServers`):

```json
{
  "mcpServers": {
    "wildberries": {
      "type": "sse",
      "url": "http://<IP-мака-с-сервером>:8001/sse",
      "headers": {
        "Authorization": "Bearer <MCP_AUTH_TOKEN из .env>"
      }
    }
  }
}
```

Если клиент не умеет передавать заголовки — токен можно передать параметром:
`http://<IP>:8001/sse?token=<MCP_AUTH_TOKEN>`.

Подключение Claude Code с любой машины:

```bash
claude mcp add --transport sse wildberries "http://<IP>:8001/sse" \
  --header "Authorization: Bearer <MCP_AUTH_TOKEN>"
```

## 5. Сеть и безопасность

- В локальной сети достаточно `MCP_AUTH_TOKEN` + статический IP/имя хоста
  (Mac mini: Системные настройки → Сеть → зафиксировать IP, либо использовать
  `<имя-мака>.local`).
- **Не пробрасывайте порт 8001 в интернет напрямую.** Для доступа извне —
  Tailscale (рекомендуется: `tailscale up`, адрес вида `100.x.y.z`) или VPN.
- Веб-дашборд (`/`, `/shops`, `/diagnostics`) не закрыт токеном — он доступен
  всем, кто имеет сетевой доступ к порту. В доверенной сети это ок.

## 6. Диагностика

| Что | Где |
|-----|-----|
| Здоровье сервиса + сводка | `GET /api/health` |
| Страница диагностики (токены, ping, пробы, деградации) | `http://<IP>:8001/diagnostics` |
| Запустить проверку сейчас | кнопка на странице или `POST /api/diagnostics/run` |
| Полная диагностика магазина (JSON) | `GET /api/diagnostics/<shop_id>` |
| Из Claude/OpenClaw | инструменты `wb_diagnostics`, `wb_degradations`, `wb_token_info`, `wb_api_news` |

Фоновая проверка выполняется каждые `HEALTH_CHECK_INTERVAL_MIN` минут (по умолчанию 30):
ping всех 13 хостов WB API + лёгкие реальные запросы по категориям + срок действия токенов.
Результаты видны на дашборде; деградации инструментов (работал → стабильно падает)
подсвечиваются как возможное изменение WB API.

## 7. Обновление

```bash
cd ~/wb-mcp-server
# скопировать новые исходники поверх (или git pull, если репозиторий)
docker compose up -d --build
```

Данные в томе `wb_data` при пересборке сохраняются.
