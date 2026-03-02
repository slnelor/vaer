local M = {}

M.defaults = {
  mode = "HAND",
  spinner_frames = { "[.,]", "[,.]" },
  spinner_interval_ms = 120,
  max_parallel_requests = 4,
  stale_strategy = "skip", -- skip | retry
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
    -- JSON in: { target_file, changedtick, progress_ranges, file_text, cwd, permissions }
    -- JSON out: { edits = [{ target_file, start_line, end_line, replacement_lines, reason? }] }
    command = nil,
    timeout_ms = 30000,
  },
  treesitter = {
    enable = true,
    use_fallback_heuristics = true,
  },
  notify = true,
}

return M
