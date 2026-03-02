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
          virt_text_pos = "overlay",
          virt_text_win_col = 0,
          hl_mode = "combine",
          priority = 200,
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

local function close_task_window(state)
  if state.task_win and vim.api.nvim_win_is_valid(state.task_win) then
    pcall(vim.api.nvim_win_close, state.task_win, true)
  end
  if state.task_buf and vim.api.nvim_buf_is_valid(state.task_buf) then
    pcall(vim.api.nvim_buf_delete, state.task_buf, { force = true })
  end
  state.task_win = nil
  state.task_buf = nil
end

function M.render_task_window(state)
  local total = state.request.in_flight_count + #state.request.queue
  if total <= 1 then
    close_task_window(state)
    return
  end

  local lines = { string.format("Vaer tasks: %d", total) }
  for request_id, _ in pairs(state.request.active) do
    table.insert(lines, "- " .. request_id)
  end
  if #state.request.queue > 0 then
    table.insert(lines, string.format("- queued: %d", #state.request.queue))
  end

  local width = 18
  for _, line in ipairs(lines) do
    width = math.max(width, #line + 2)
  end
  local height = #lines
  local col = math.max(0, vim.o.columns - width - 2)

  if not (state.task_buf and vim.api.nvim_buf_is_valid(state.task_buf)) then
    state.task_buf = vim.api.nvim_create_buf(false, true)
    vim.bo[state.task_buf].bufhidden = "wipe"
  end

  vim.api.nvim_buf_set_lines(state.task_buf, 0, -1, false, lines)

  local opts = {
    relative = "editor",
    row = 1,
    col = col,
    width = width,
    height = height,
    style = "minimal",
    border = "rounded",
    focusable = false,
    noautocmd = true,
  }

  if state.task_win and vim.api.nvim_win_is_valid(state.task_win) then
    vim.api.nvim_win_set_config(state.task_win, opts)
  else
    state.task_win = vim.api.nvim_open_win(state.task_buf, false, opts)
    vim.wo[state.task_win].winblend = 10
  end
end

function M.statusline_mode(state)
  return "VAER:" .. state.mode
end

return M
