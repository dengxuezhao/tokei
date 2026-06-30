# CodeFuse Source Design

## Context

Tokei currently reads each supported AI tool from its own local data source and normalizes the result into fixed time ranges. Token-aware tools expose real usage fields, while tools such as Grok, QoderWork, and OpenClaw fall back to locally verifiable activity metrics when token data is missing.

CodeFuse/cfuse stores the most reliable request-level usage data under:

```text
~/.codefuse/fuse/logs/proxy-stats/*.json
```

The current files are named `cc-YYYY-MM-DD.json` and contain `engine`, `totalRequests`, and `recentRequests`. Each request has fields such as `model`, `path`, `startTime`, `statusCode`, `requestSize`, `sessionId`, `cwd`, `duration`, and `ttftMs`. A full scan of the observed local files found no real token, usage, or cost fields. `requestSize` is request payload size, not tokenizer output.

## Decision

Add CodeFuse as an independent `cfuse` source. It will be request-metric based, not token/cost based.

The Python collector will scan all proxy stats files, not only `cc-*`, and derive the engine from `entry.engine` first, then the filename prefix. This keeps the design ready for future cfuse engines while supporting the current Claude Code-compatible `cc` engine.

## Data Model

Each cfuse range will expose:

- `requests`
- `success`
- `errors`
- `sessions`
- `request_size`
- `response_size`
- `avg_duration`
- `avg_ttft`
- `models`: request counts by model
- `engines`: nested request counts by engine and model
- `projects`: top cwd counts

The collector will count only `/v1/messages` requests for primary cfuse usage. It will de-duplicate requests by request id, falling back to file path plus timestamp and turn id when id is absent.

## UI

The Swift app will add `CfuseStat`, `CfuseRange`, `CfuseModelStat`, and `CfuseEngineStat`. The panel gets a CodeFuse card with request count, success/error counts, sessions, request size, average duration, average TTFT, top engine, and top model. It will not be included in total token or cost charts.

Settings will gain a CodeFuse visibility toggle. Multi-device sync will merge cfuse ranges just like other non-token activity sources.

## Testing

Python scanner behavior is covered with `unittest` fixtures:

- missing cfuse directory returns empty ranges
- proxy stats are aggregated by range
- duplicate request ids are ignored
- non-message paths are ignored
- engines are derived from JSON or filename
- models, projects, success/error, request size, duration, and TTFT are accumulated correctly

Swift is verified by `swift build` because the package currently has no test target.

## Non-Goals

- Do not estimate cfuse token usage from `requestSize`.
- Do not estimate cfuse cost.
- Do not merge cfuse into Claude Code statistics.
