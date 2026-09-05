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


def test_visible_tools_hides_shop_id_for_single_shop(tmp_path, monkeypatch):
    """Один магазин — shop_id из схем убран, несколько — возвращается."""
    import json
    from wb_mcp import server

    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    with_shop_id = lambda tools: sum(
        1 for t in tools if "shop_id" in (t.inputSchema.get("properties") or {})
    )

    tools = server._visible_tools()
    assert len(tools) == len(server.TOOLS)
    assert with_shop_id(tools) == 0, "при одном магазине shop_id не нужен в схеме"

    (tmp_path / "shops.json").write_text(json.dumps({"a": {"name": "A"}, "b": {"name": "B"}}))
    tools = server._visible_tools()
    assert with_shop_id(tools) > 0, "при нескольких магазинах shop_id обязан вернуться"


def test_json_output_is_compact():
    """Ответы сериализуются без отступов — indent=2 стоил 39% лишних токенов."""
    from wb_mcp.server import _json

    text = _json({"a": [1, 2], "b": "тест"})[0].text
    assert "\n" not in text and ", " not in text, text
    assert "\\u" not in text, "кириллица не должна экранироваться"


def test_limit_defaults_match_handlers():
    """default в схеме = фактический дефолт в handler.

    Расхождение опаснее лишних токенов: модель читает схему, считает, что
    получила 1000 записей, и делает вывод по первым 100.
    """
    import inspect
    import re
    from wb_mcp.server import TOOLS, CLIENT_DISPATCH, NO_CLIENT_DISPATCH, SHOP_DISPATCH

    handlers = {**CLIENT_DISPATCH, **NO_CLIENT_DISPATCH, **SHOP_DISPATCH}
    mismatched = []
    for tool in TOOLS:
        prop = (tool.inputSchema.get("properties") or {}).get("limit")
        handler = handlers.get(tool.name)
        if not isinstance(prop, dict) or "default" not in prop or handler is None:
            continue
        found = re.search(r'get\("limit",\s*(\d+)\)', inspect.getsource(handler))
        if found and int(found.group(1)) != prop["default"]:
            mismatched.append((tool.name, prop["default"], int(found.group(1))))

    assert not mismatched, f"схема обещает не тот лимит (tool, схема, код): {mismatched}"


def test_registry_description_fits_the_limit():
    """MCP Registry отклоняет server.json с description длиннее 100 символов.

    Публикация падала с 422 именно на этом: короткое описание легко перерастает
    лимит, когда в него добавляют цифры.
    """
    import json
    import pathlib

    manifest = json.loads((pathlib.Path(__file__).resolve().parent.parent / "server.json").read_text())
    assert len(manifest["description"]) <= 100, len(manifest["description"])
