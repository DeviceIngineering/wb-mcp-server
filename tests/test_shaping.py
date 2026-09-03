"""Формирование ответа: пресеты, сигнал усечения, предохранитель размера.

Проверяется главное свойство: урезать данные можно, молчать об этом — нельзя.
"""

import json

import pytest

from wb_mcp import shaping


def _cards(n=3):
    return {"cards": [{"nmID": 100 + i, "vendorCode": f"ART-{i}", "title": "Ящик 30 л",
                       "brand": "FabPlast", "subjectName": "Ящики", "subjectID": 1,
                       "imtID": 7, "sizes": [], "dimensions": {}, "needKiz": False,
                       "updatedAt": "2026-09-01T10:00:00Z",
                       "photos": [{"big": "https://example.test/a.jpg"}] * 10,
                       "description": "Очень длинное описание. " * 40,
                       "characteristics": [{"id": 1, "name": "Цвет", "value": ["синий"]}]}
                      for i in range(n)]}


def test_compact_drops_heavy_fields_and_says_so():
    data, notes = shaping.shape("wb_cards_list", {}, _cards())
    card = data["cards"][0]
    assert "photos" not in card and "description" not in card
    assert card["nmID"] == 100 and card["title"] == "Ящик 30 л"
    assert notes and "view=" in notes[0] and "photos" in notes[0]


def test_full_view_keeps_everything_and_stays_silent():
    data, notes = shaping.shape("wb_cards_list", {"view": "full"}, _cards())
    assert "photos" in data["cards"][0]
    assert notes == []


def test_unknown_tool_passes_through():
    payload = {"anything": [1, 2, 3]}
    data, notes = shaping.shape("wb_some_other_tool", {}, payload)
    assert data == payload and notes == []


def test_truncation_is_announced_when_page_is_full():
    _, notes = shaping.shape("wb_cards_list", {"limit": 3}, _cards(3))
    assert any("ровно 3" in n for n in notes), notes


def test_no_truncation_note_when_page_is_short():
    _, notes = shaping.shape("wb_cards_list", {"limit": 50}, _cards(3))
    assert not any("ровно" in n for n in notes), notes


def test_guard_cuts_oversized_array_and_reports_the_cut():
    huge = {"report": [{"subjectName": f"Категория {i}", "kgvpMarketplace": 25.5,
                        "parentName": "Дом", "subjectID": i} for i in range(5000)]}
    data, note = shaping.guard_size(huge, max_chars=20_000)
    kept = len(data["report"])
    assert 0 < kept < 5000
    assert note and str(kept) in note and "5000" in note
    assert len(json.dumps(data, ensure_ascii=False)) <= 40_000


def test_guard_keeps_small_responses_untouched():
    small = {"data": [1, 2, 3]}
    data, note = shaping.guard_size(small, max_chars=20_000)
    assert data == small and note is None


@pytest.mark.asyncio
async def test_commission_filter_narrows_the_reference():
    from wb_mcp.server import _h_tariffs_commission

    class FakeClient:
        async def tariffs_commission(self):
            return {"report": [{"subjectName": "Ящики для хранения", "parentName": "Дом"},
                               {"subjectName": "Ноутбуки", "parentName": "Электроника"}]}

    filtered = await _h_tariffs_commission(FakeClient(), {"subject": "ящик"})
    assert len(filtered["report"]) == 1
    assert filtered["totalCategories"] == 2

    whole = await _h_tariffs_commission(FakeClient(), {})
    assert len(whole["report"]) == 2
