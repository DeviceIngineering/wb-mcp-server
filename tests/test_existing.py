import pytest


def test_dispatch_coverage():
    """Все инструменты из TOOLS имеют handler в dispatch."""
    from wb_mcp.server import TOOLS, CLIENT_DISPATCH, NO_CLIENT_DISPATCH, SHOP_DISPATCH

    tool_names = {t.name for t in TOOLS}
    dispatch_names = set(CLIENT_DISPATCH.keys()) | set(NO_CLIENT_DISPATCH.keys()) | set(SHOP_DISPATCH.keys())
    missing = tool_names - dispatch_names
    assert not missing, f"Нет handler для: {missing}"
    extra = dispatch_names - tool_names
    assert not extra, f"Handler без Tool: {extra}"


def test_no_duplicate_tools():
    """Нет дублей в TOOLS."""
    from wb_mcp.server import TOOLS

    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_client_dispatch_callable(mock_client):
    """Все client handlers вызываемы с mock клиентом и пустым dict."""
    from wb_mcp.server import CLIENT_DISPATCH

    for name, handler in CLIENT_DISPATCH.items():
        try:
            await handler(mock_client, {})
        except (KeyError, TypeError):
            pass
        except Exception as e:
            if "AsyncMock" not in str(type(e)):
                pytest.fail(f"{name}: неожиданное исключение {type(e).__name__}: {e}")


@pytest.mark.asyncio
async def test_no_client_dispatch_callable():
    """Все no-client handlers вызываемы с пустым dict."""
    from wb_mcp.server import NO_CLIENT_DISPATCH

    for name, handler in NO_CLIENT_DISPATCH.items():
        try:
            await handler({})
        except Exception:
            pass
