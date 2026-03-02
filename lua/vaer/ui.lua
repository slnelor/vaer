local line_state = require("vaer.line_state")

local M = {}

local function set_hl_once()
  vim.api.nvim_set_hl(0, "VaerProgress", { link = "DiagnosticWarn" })
  vim.api.nvim_set_hl(0, "VaerWorking", { link = "DiagnosticInfo" })
  vim.api.nvim_set_hl(0, "VaerSpinner", { link = "Comment" })
end

local function frame(state)
  return state.opts.spinner_frames[state.spinner_index]
end

function M.render_buffer(state, bufnr)
  if not vim.api.nvim_buf_is_valid(bufnr) then
    return
  end

  set_hl_once()
  local b = require("vaer.state").get_buf(state, bufnr)
  vim.api.nvim_buf_clear_namespace(bufnr, state.ns, 0, -1)

  for line, status in pairs(b.status_by_line) do
    if status == line_state.PROGRESS or status == line_state.WORKING then
      local hl = status == line_state.WORKING and "VaerWorking" or "VaerProgress"
      vim.api.nvim_buf_add_highlight(bufnr, state.ns, hl, line - 1, 0, -1)
    end
  end

  local current_frame = frame(state)
  for _, r in ipairs(b.working_ranges) do
    for line = r.start_line, r.end_line do
      if b.status_by_line[line] == line_state.WORKING then
        vim.api.nvim_buf_set_extmark(bufnr, state.ns, line - 1, 0, {
          virt_text = { { current_frame, "VaerSpinner" } },
          virt_text_pos = "eol",
          hl_mode = "combine",
        })
      end
    end
  end
end

function M.render_all(state)
  for bufnr, _ in pairs(state.buffers) do
    M.render_buffer(state, bufnr)
  end
end

local function has_working(state)
  for bufnr, _ in pairs(state.buffers) do
    if vim.api.nvim_buf_is_valid(bufnr) then
      local b = require("vaer.state").get_buf(state, bufnr)
      if #b.working_ranges > 0 then
        return true
      end
    end
  end
  return false
end

function M.start_spinner(state)
  if state.spinner_timer then
    return
  end

  state.spinner_timer = vim.uv.new_timer()
  state.spinner_timer:start(
    0,
    state.opts.spinner_interval_ms,
    vim.schedule_wrap(function()
      if not has_working(state) then
        M.stop_spinner(state)
        return
      end
      state.spinner_index = state.spinner_index + 1
      if state.spinner_index > #state.opts.spinner_frames then
        state.spinner_index = 1
      end
      M.render_all(state)
    end)
  )
end

function M.stop_spinner(state)
  if not state.spinner_timer then
    return
  end
  state.spinner_timer:stop()
  state.spinner_timer:close()
  state.spinner_timer = nil
end

function M.statusline_mode(state)
  return "VAER:" .. state.mode
end

return M
