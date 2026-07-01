# CodeFuse Source Implementation Plan

Update 2026-07-01: this initial plan was superseded for the `cc` engine by the discovered CodeFuse project JSONL usage source. The implemented scanner now combines `cc/projects/**/*.jsonl` token usage with proxy-stats request telemetry.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add CodeFuse/cfuse as a first-class Tokei data source using local proxy stats request metrics.

**Architecture:** The Python collector adds a `scan_cfuse` path that reads `~/.codefuse/fuse/logs/proxy-stats/*.json`, aggregates request metrics into the existing range model, and emits a new `cfuse` JSON key. The Swift app decodes this into a non-token `CfuseStat`, displays a CodeFuse card, and merges it during multi-device sync without adding it to token or cost totals.

**Tech Stack:** Python 3 stdlib, JSON fixtures, `unittest`, Swift 5.9, SwiftUI.

---

### Task 1: Python cfuse scanner tests

**Files:**
- Create: `tests/test_cfuse_scan.py`

**Step 1: Write failing tests**

Create a unittest module that imports `usage.30s.py` with `importlib.util.spec_from_file_location`, writes temporary `cc-2026-06-30.json` and `other-2026-06-30.json` fixtures, points `module.CFUSE_PROXY_STATS_DIR` at the temp directory, and asserts:

- `scan_cfuse(bounds, {})` exists
- duplicate request ids count once
- `/count_tokens` does not count as a primary request
- missing `engine` falls back to the filename prefix
- returned `today` range contains request totals, sessions, request size, avg duration, avg TTFT, models, engines, and projects

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests/test_cfuse_scan.py -v
```

Expected: FAIL because `scan_cfuse` does not exist.

### Task 2: Python scanner implementation

**Files:**
- Modify: `usage.30s.py`

**Step 1: Add constants and empty model**

Add:

```python
CFUSE_PROXY_STATS_DIR = os.path.join(HOME, ".codefuse", "fuse", "logs", "proxy-stats")
```

Add `_empty_cfuse`, `_cfuse_bucket`, and formatting helpers.

**Step 2: Implement `scan_cfuse`**

Read `*.json` files, cache by file mtime and size, aggregate per day, and merge into `RANGE_KEYS`. Count only paths starting with `/v1/messages`.

**Step 3: Wire into `compute`**

Call `_safe_scan("cfuse", ...)`, format the ranges, and emit:

```python
"cfuse": {"ranges": cfranges}
```

**Step 4: Run Python tests**

Run:

```bash
python3 -m unittest tests/test_cfuse_scan.py -v
```

Expected: PASS.

### Task 3: Swift model and sync

**Files:**
- Modify: `Tokei/Sources/Tokei/Model.swift`
- Modify: `Tokei/Sources/Tokei/SyncManager.swift`
- Modify: `Tokei/Sources/Tokei/Design.swift`

**Step 1: Add cfuse Codable structs**

Add `CfuseModelStat`, `CfuseEngineStat`, `CfuseProjectStat`, `CfuseRange`, `CfuseRanges`, and `CfuseStat`.

**Step 2: Add `Usage.cfuse`**

Decode `cfuse` with a default empty value for backward compatibility.

**Step 3: Merge cfuse ranges**

Add `mergeRanges` overload for `CfuseRanges`. Sum counts and weighted-average latency fields by request count. Merge model, engine, and project arrays by name.

**Step 4: Add theme color**

Add `Theme.cfuse`.

### Task 4: Panel UI

**Files:**
- Modify: `Tokei/Sources/Tokei/PanelView.swift`

**Step 1: Add settings state**

Add `@AppStorage("showCfuse")`, include it in `visibleCount`, and add the settings row.

**Step 2: Add card**

Add a CodeFuse card after Codex. The card displays request count as the headline, then sessions, success, errors, request size, average duration, average TTFT, top engine, and top model.

**Step 3: Add sync debug awareness**

Add `cfuse` to the tool list used by the settings diagnostic output.

### Task 5: Docs

**Files:**
- Modify: `README.md`
- Modify: `CALCULATION.md`

**Step 1: Update supported source count and list**

Add CodeFuse/cfuse to supported tools.

**Step 2: Document metric limitations**

Explain that cfuse uses request metrics because proxy stats do not currently expose real token/cost fields.

### Task 6: Verification

**Files:**
- No source changes.

**Step 1: Run Python unit tests**

```bash
python3 -m unittest tests/test_cfuse_scan.py -v
```

**Step 2: Run collector JSON check**

```bash
python3 usage.30s.py --json | jq '.cfuse.ranges.today'
```

Expected: JSON contains cfuse request metrics.

**Step 3: Build Swift app**

```bash
cd Tokei && swift build
```

Expected: Build succeeds.

**Step 4: Inspect git diff**

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors and changes scoped to cfuse source support.
