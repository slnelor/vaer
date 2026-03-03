local M = {}

M.defaults = {
  mode = "HAND",
  spinner_frames = { "[v]", "[a]", "[e]", "[r]" },
  spinner_interval_ms = 120,
  max_parallel_requests = 10,
  stale_strategy = "retry", -- skip | retry
  enable_default_keymaps = true,
  keymaps = {
    toggle_mode = "<C-t>",
  },
  cache = {
    dir = "tmp/vaer",
    enabled = true,
  },
  request = {
    -- External adapter command that receives JSON via stdin and returns JSON on stdout.
    -- Default bundled adapter uses OpenCode CLI (`opencode run`).
    -- JSON in: { target_file, changedtick, progress_ranges, file_text, cwd, permissions }
    -- JSON out: { edits = [{ target_file, start_line, end_line, replacement_lines, reason? }] }
    command = nil,
    timeout_ms = 90000,
    trigger = "newline", -- newline | enter
    allow_stale_apply = true,
    debounce_ms = 300,
    render_debounce_ms = 40,
    launch_stagger_ms = 120,
    context_radius = 24,
    max_payload_chars = 16000,
    cancel_active_on_supersede = true,
    process_priority_nice = 10,
    max_progress_ranges = 12,
  },
  apply = {
    max_edit_count = 8,
    max_edit_lines = 120,
    max_replacement_lines = 240,
    max_total_replacement_lines = 480,
    reject_blank_replacements = true,
  },
  safety = {
    max_cached_progress_lines = 500,
  },
  opencode = {
    -- model can be provider/model format, eg: openai/gpt-5.3-codex
    model = "openai/gpt-5.3-codex",
    provider = nil,
    mode = "code",
    session_scope = "project", -- project | buffer
  },
  treesitter = {
    enable = true,
    use_fallback_heuristics = true,
  },
  ui = {
    enable_spinner = false,
    show_task_window = false,
  },
  notify = true,
}

return M
