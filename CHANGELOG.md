# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

Русская версия истории изменений живёт в README.ru.md и в заметках проекта.

## [2.6.0] — 2026-09-04

### Removed
- Five tools whose endpoints Wildberries deleted — verified against a live account,
  all four paths answer 404 «path not found» (not the «temporarily disabled» that the
  supply endpoints return): `wb_analytics_goods_labeling`,
  `wb_analytics_measurement_penalties`, `wb_analytics_warehouse_measurements`,
  `wb_users_list`, `wb_users_invite`. A tool that always fails costs tokens and a call
  to learn nothing. 202 tools → 197.

### Fixed
- `wb_deductions` never worked: `dateFrom` is required by WB even though the docs mark
  it optional, and the tool did not send it. Both dates are required now.

## [2.5.4] — 2026-09-04

### Fixed
- Wildberries switched three supply endpoints off on its own side — FBW warehouses,
  acceptance coefficients and transit tariffs answer 404 with «This method is
  temporarily disabled» (release notes 570). They used to surface as a raw HTTP
  error, which reads like a broken tool. The client now returns the explanation, the
  three tool descriptions say so, and diagnostics reports them separately from real
  failures: the server is fine, the vendor turned the method off.

## [2.5.3] — 2026-09-04

### Changed
- Short descriptions now say what the long ones already did: the GitHub repository
  description, the PyPI summary and `server.json` for the MCP Registry mention that
  response sizes are measured on a live account and trimmed (770k → 75k tokens). Those
  three strings are what directories, GitHub search and link previews actually show —
  the README sections were invisible to all of them.

## [2.5.2] — 2026-09-04

### Changed
- English README is now the default one; the Russian text moved to `README.ru.md`
  and the language switcher badges follow. The PyPI page and directory listings
  read the default README, so they are English now too.
- `Context budget` and `Design decisions` sections added in all three languages:
  what the measurements were, what `view`/truncation signal/size guard/profiles do,
  and why the notes are separate content blocks rather than a JSON field.
- Repository description translated to English with search keywords.

### Added
- `docs/social-preview.png` (1280×640) for link previews.
- `glama.json` declaring the maintainer for the Glama directory.

## [2.5.1] — 2026-09-03

### Fixed
- `docker compose up -d --build`, the first command in the README, failed on
  `pip install .`: `pyproject.toml` references `LICENSE` and the README, and the
  Dockerfile copied neither. Broken since the PyPI packaging landed on 21 August —
  the wheel built fine, so nothing surfaced it until someone built the image.

### Added
- `.github/workflows/ci.yml`: pytest on Python 3.11 and 3.12, a Docker build, and a
  check that the built image answers `initialize` and returns a non-empty tool list.
  Until now CI only ran on tags, for publishing.

## [2.5.0] — 2026-09-03

### Added
- Tool profiles (`wb_mcp/toolsets.py`, `WB_TOOLSETS`): a client without tool search
  pays for the whole catalogue on every request. `pricing,ads` keeps 49 tools and
  4 925 tokens instead of 202 and 18 011. The `core` profile — stores, diagnostics,
  degradations, token info — is always on. Disabled profiles are named in the
  `wb_list_shops` description, and calling a disabled tool answers which profile
  contains it, so the assistant states the reason instead of "this is not possible".

## [2.4.0] — 2026-09-03

### Added
- Response shaping (`wb_mcp/shaping.py`): `view: compact | full` presets for the seven
  heaviest tools, a truncation signal when exactly `limit` records come back, and a
  size guard that cuts server-side instead of letting the client truncate silently.
- `subject` filter for `wb_tariffs_commission` — the API returns all 7 408 categories
  in one payload, 621 802 tokens, 25× the client ceiling.
- `scripts/collect_corpus.py` and `scripts/measure_corpus.py`: snapshot real responses
  from a live account (PII masked before writing, corpus git-ignored) and measure what
  they cost. Corpus of 27 responses: 770 506 → 74 947 tokens.

### Notes
- Null-stripping was implemented, measured at 0.2% on real data — the API returns zeros
  as the string `"0"` — and dropped.
- `wb_analytics_detail` was left untouched: past, selected and comparison are equal in
  size and all three are needed for the conclusion.

## [2.3.1] — 2026-09-03

### Fixed
- `"default"` in the `limit` schemas still advertised the pre-2.3.0 values while the
  handlers had already been lowered. No error surfaced: the model read the schema,
  believed it had 1 000 records, received 100, and would have reported a conclusion
  about the whole catalogue. Twelve tools were affected.
- `test_limit_defaults_match_handlers` now compares each schema default with the
  handler source and fails on a mismatch.

## [2.3.0] — 2026-09-03

### Changed
- Definitions of 202 tools: 27 460 → 17 709 tokens with a single store configured.
  One-sentence descriptions (English wording plus Russian keywords for discovery),
  `shop_id` dropped from the schemas when only one store exists, empty schema fields
  no longer serialised, `[P1]`–`[P3]` prefixes removed and `[P0]` kept.
- Responses serialised without indentation; `ensure_ascii=False` retained, since
  escaping Cyrillic would add 32%.
- Default `limit` values lowered: 100 000 → 500 in financial reports, 1 000 → 100 in
  lists. The old defaults could not fit the client output ceiling.

## [2.2.x] and earlier

See the git history and GitHub releases.

[2.6.0]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.6.0
[2.5.4]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.5.4
[2.5.3]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.5.3
[2.5.2]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.5.2
[2.5.1]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.5.1
[2.5.0]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.5.0
[2.4.0]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.4.0
[2.3.1]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.3.1
[2.3.0]: https://github.com/DeviceIngineering/wb-mcp-server/releases/tag/v2.3.0
