# AGENTS.md

## Project Explanation
`vaer.nvim` is a Neovim plugin prototype for inline coding assistance with two modes:
- `HAND`: normal editing mode, no VAER request dispatch.
- `VAER`: changed lines become "in-progress", and requests are dispatched to an external adapter that returns structured line edits.

The plugin is safety‑first: it can reason broadly, but write operations are constrained to the active file and editable line regions.

## General Knowledge (Read This First)
- Runtime behavior is driven by Lua modules in `lua/vaer/`.
- `scripts/vaer_adapter.py` is the external request adapter (OpenCode/Inception).
- Root Python modules (`agent.py`, `request_manager.py`, etc.) are prototype/reference code and may not be the live Neovim runtime path.
- Cache and logs are project‑local in `tmp/vaer/`.
- Line numbering in payloads/edits is 1‑based absolute line numbers.
- Line status model:
  - `complete`: default/immutable by apply safety.
  - `progress`: user‑touched, eligible for model edits.
  - `working`: currently being processed.

## Architecture
### Entry + Orchestration
- `plugin/vaer.lua`: defines user commands and calls setup.
- `lua/vaer/init.lua`: central orchestrator for setup, keymaps, buffer attach, dispatch, apply, render, and persistence.
- `lua/vaer/state.lua`: global mutable plugin state + per‑buffer state.

### Request Pipeline
- `lua/vaer/request.lua`:
  - queued request launcher with parallel cap.
  - supersede semantics by key (usually per‑buffer).
  - process timeout, cancellation, and pending replay logic.
  - Adapter command defaults to `python3 scripts/vaer_adapter.py`.

### Apply + Safety
- `lua/vaer/apply.lua`:
  - validates each proposed edit.
  - blocks cross‑file writes.
  - requires overlap with `progress_ranges`.
  - blocks edits to `complete` lines.
  - rejects destructive/blank/no‑op edits.
  - applies bottom‑up to avoid line‑shift issues.

### State + Persistence + UI
- `lua/vaer/line_state.lua`: source of truth for per‑line status.
- `lua/vaer/persistence.lua`: sparse status map persisted to `tmp/vaer/state_<hash>.json`.
- `lua/vaer/ui.lua`: highlights, optional spinner, optional task window.
- `lua/vaer/log.lua`: `vim.notify` + append log file.

### Adapter Layer
- `scripts/vaer_adapter.py`:
  - reads JSON payload on stdin.
  - calls provider (`opencode` or `inception`).
  - enforces JSON‑only structured output.
  - supports session‑id caching under `tmp/vaer/`.
  - can auto‑route web‑research style tasks from Inception → OpenCode.

## Non‑Negotiable Safety Invariants
- Never allow writes to files other than `target_file`.
- Never apply edits that do not intersect the current `progress_ranges`.
- Never edit `complete` lines.
- Never accept empty destructive replacements.
- Keep apply order descending by start line.
- Fail closed: if validation/parsing fails, skip or fail with diagnostics.

## Style and Implementation Rules
### Lua Style
- Use module‑table pattern (`local M = {}` + `return M`).
- Prefer small local helper functions and guard clauses.
- Keep hot callbacks lightweight (`on_lines`, render path, queue launch path).
- Use debouncing/scheduling (`vim.defer_fn`, `vim.schedule`) for UI responsiveness.
- Avoid blocking editor loop with long synchronous work.

### Python Adapter Style
- Keep adapter mostly stdlib and defensive.
- Parse loosely, validate strictly.
- Return machine‑readable diagnostics instead of throwing.
- Always emit a JSON object with keys `edits` and `diagnostics`.

### Config and Compatibility
- Add new behavior behind config defaults in `lua/vaer/config.lua`.
- Preserve existing command names and payload schema unless migration is documented.
- Prefer backwards‑compatible defaults and feature flags.

## Where To Make Changes
- Dispatch behavior, debounce, payload shaping: `lua/vaer/init.lua`.
- Queueing, supersede, process lifecycle: `lua/vaer/request.lua`.
- Safety policy / edit acceptance: `lua/vaer/apply.lua`.
- Line status lifecycle: `lua/vaer/line_state.lua`.
- Persistence format/path: `lua/vaer/persistence.lua`.
- UI visuals/statusline/task window: `lua/vaer/ui.lua`.
- Provider behavior, routing, JSON extraction: `scripts/vaer_adapter.py`.

## Testing and Verification Guidance
Use fast local verification before large changes:
- Smoke‑check setup, toggle mode, edit line, dispatch, apply.
- Verify stale/cancel/timeout paths still restore `working → progress`.
- Verify cross‑file edits are rejected.
- Verify no‑op/blank/destructive edits are filtered.
- Verify cache files in `tmp/vaer/` are still readable after format changes.

If headless local scripts exist under `tmp/`, treat them as ad‑hoc checks (not guaranteed CI).

## Known Caveats
- `lua/vaer/treesitter.lua` exists, but ensure it is actually wired before assuming import detection is active in runtime flow.
- Root Python prototype modules can drift from Lua runtime behavior; prefer Lua as source of truth for plugin behavior.