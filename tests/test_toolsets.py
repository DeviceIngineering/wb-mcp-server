"""Профили инструментов: урезать каталог можно, прятать причину — нельзя."""

import pytest

from wb_mcp import toolsets
from wb_mcp.server import TOOLS, _enabled_tools, _visible_tools


def test_every_tool_belongs_to_a_profile():
    """Инструмент без профиля потерялся бы при любом WB_TOOLSETS."""
    unassigned = [t.name for t in TOOLS if toolsets.profile_of(t.name) not in toolsets.ALL_PROFILES]
    assert not unassigned, unassigned


def test_no_limit_by_default(monkeypatch):
    monkeypatch.delenv("WB_TOOLSETS", raising=False)
    assert toolsets.enabled_profiles() is None
    assert len(_enabled_tools(_visible_tools())) == len(TOOLS)


def test_profile_narrows_the_catalogue(monkeypatch):
    monkeypatch.setenv("WB_TOOLSETS", "pricing,ads")
    tools = _enabled_tools(_visible_tools())
    assert 0 < len(tools) < len(TOOLS)
    profiles = {toolsets.profile_of(t.name) for t in tools}
    assert profiles <= {"core", "pricing", "ads"}


def test_core_survives_any_profile(monkeypatch):
    """Диагностика нужна ровно тогда, когда что-то сломалось."""
    monkeypatch.setenv("WB_TOOLSETS", "pricing")
    names = {t.name for t in _enabled_tools(_visible_tools())}
    for required in ("wb_list_shops", "wb_diagnostics", "wb_degradations", "wb_token_info"):
        assert required in names, required


def test_disabled_profiles_are_named_in_list_shops(monkeypatch):
    monkeypatch.setenv("WB_TOOLSETS", "pricing")
    description = next(t.description for t in _enabled_tools(_visible_tools())
                       if t.name == "wb_list_shops")
    assert "WB_TOOLSETS" in description
    assert "finance" in description and "orders" in description


def test_unknown_profile_is_ignored(monkeypatch):
    monkeypatch.setenv("WB_TOOLSETS", "нет-такого-профиля")
    assert toolsets.enabled_profiles() is None


@pytest.mark.asyncio
async def test_disabled_tool_explains_itself(monkeypatch):
    """Отказ должен называть причину, иначе модель скажет «это невозможно»."""
    monkeypatch.setenv("WB_TOOLSETS", "pricing")
    from wb_mcp.server import _call_tool_impl

    blocks = await _call_tool_impl("wb_feedbacks_list", {"shop_id": "нет-такого"})
    text = blocks[0].text
    assert "feedback" in text and "WB_TOOLSETS" in text
