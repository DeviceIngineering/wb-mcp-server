import pytest
from unittest.mock import AsyncMock, MagicMock

from wb_mcp.client import WBClient


@pytest.fixture
def mock_client():
    client = MagicMock(spec=WBClient)
    # Замокать все async-методы
    for attr in dir(WBClient):
        if attr.startswith("_") and attr != "_send":
            continue
        val = getattr(WBClient, attr, None)
        if callable(val) and not isinstance(val, property):
            mock_method = AsyncMock(return_value={})
            setattr(client, attr, mock_method)
    client._send = AsyncMock(return_value={"ok": True})
    return client


@pytest.fixture
def sample_shop_id():
    return "test_shop"
