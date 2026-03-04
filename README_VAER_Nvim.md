# vaer.nvim (prototype)

Neovim plugin prototype for HAND/VAER inline coding flow.

## Features in this prototype

- Modes: `HAND` and `VAER`.
- Toggle key: `<C-t>` in Normal and Insert mode.
- Enter in Insert mode dispatches requests only in `VAER`.
- Line states: `complete`, `progress`, `working`.
- Spinner animation on working lines: `[v]`, `[a]`, `[e]`, `[r]`.
- Treesitter-aware import detection with fallback heuristics.
- Async request queue with parallel limit and cancellation.
- Safety gates:
  - only current file edits are accepted
  - edits on `complete` lines are blocked
  - stale changedtick strategy (`skip` by default)
- Cache persistence to project `tmp/vaer` and automatic load on buffer open.

## Install (local runtimepath)

```lua
vim.opt.rtp:append("/home/mikhail/ForPython/vaer/proto/vaer")
require("vaer").setup({
  provider = {
    name = "opencode", -- or "inception"
  },
  opencode = {
    -- model = "openai/gpt-5.3-codex", -- default in plugin, override if needed
    -- provider = "openai", -- optional override
    mode = "code",
    session_scope = "project",
  },
  inception = {
    model = "mercury-2",
    stream = true,
    diffusing = false,
    reasoning_effort = "instant",
  },
})
```

The plugin auto-detects and uses bundled adapter: `scripts/vaer_adapter.py`.
The adapter supports two providers:

- `opencode` via `opencode run` (no `opencode serve` required)
- `inception` via direct HTTP (`https://api.inceptionlabs.ai/v1/chat/completions`)

## Dependencies

- Python 3
- OpenCode CLI (for `provider.name = "opencode"`):

```bash
curl -fsSL https://opencode.ai/install | bash
```

Configure OpenCode/provider auth via `opencode` CLI.

For Inception provider, set:

```bash
export INCEPTION_API_KEY="your_api_key_here"
```

## Stability defaults

For low-latency and fewer freezes under heavy typing:

- Keep `max_parallel_requests = 1`
- Use `request.trigger = "newline"`
- Use `request.debounce_ms = 300` (or higher)
- Keep `request.cancel_active_on_supersede = true`

## Adapter protocol

Plugin sends JSON via stdin:

```json
{
  "target_file": "/abs/path/file.py",
  "changedtick": 42,
  "progress_ranges": [{"start_line": 10, "end_line": 15}],
  "file_text": "...",
  "cwd": "/project/root",
  "permissions": {
    "can_read_project": true,
    "can_run_tools": true,
    "can_modify_only_current_file": true
  },
  "opencode": {
    "model": "openai/gpt-5.3-codex",
    "provider": "openai",
    "mode": "code",
    "session_scope": "project"
  },
  "provider": {
    "name": "opencode"
  },
  "inception": {
    "model": "mercury-2",
    "stream": true,
    "diffusing": false,
    "reasoning_effort": "instant",
    "max_tokens": 4096,
    "temperature": 0.0
  }
}
```

Adapter must return JSON on stdout:

```json
{
  "edits": [
    {
      "target_file": "/abs/path/file.py",
      "start_line": 10,
      "end_line": 12,
      "replacement_lines": ["new", "lines"]
    }
  ],
  "diagnostics": []
}
```

## Commands

- `:VaerToggleMode`
- `:VaerCompleteAll`
- `:VaerStopAll`
- `:VaerInfo`
