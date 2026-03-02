# vaer.nvim (prototype)

Neovim plugin prototype for HAND/VAER inline coding flow.

## Features in this prototype

- Modes: `HAND` and `VAER`.
- Toggle key: `<C-t>` in Normal and Insert mode.
- Enter in Insert mode dispatches requests only in `VAER`.
- Line states: `complete`, `progress`, `working`.
- Spinner animation on working lines: `[.,]` and `[,.]`.
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
  opencode = {
    model = "openai/gpt-4.1-mini",
    -- provider = "openai", -- optional override
    mode = "code",
    session_scope = "project",
  },
})
```

The plugin auto-detects and uses bundled adapter: `scripts/vaer_adapter.py`.

## Dependencies

- Python 3
- OpenCode Python SDK:

```bash
pip install --pre opencode-ai
```

Configure OpenCode/provider auth according to your OpenCode SDK setup.

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
    "model": "openai/gpt-4.1-mini",
    "provider": "openai",
    "mode": "code",
    "session_scope": "project"
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
