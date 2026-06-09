FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY wb_mcp/ wb_mcp/

RUN pip install --no-cache-dir .

EXPOSE 8001

ENV DATA_DIR=/data
VOLUME /data

CMD ["uvicorn", "wb_mcp.app:fastapi_app", "--host", "0.0.0.0", "--port", "8001"]
