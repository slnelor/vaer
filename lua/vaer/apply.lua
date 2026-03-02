local line_state = require("vaer.line_state")

local M = {}

local function normalize_edit(edit)
  if type(edit) ~= "table" then
    return nil
  end
  if type(edit.target_file) ~= "string" then
    return nil
  end
  if type(edit.start_line) ~= "number" or type(edit.end_line) ~= "number" then
    return nil
  end
  if type(edit.replacement_lines) ~= "table" then
    return nil
  end
  return {
    target_file = edit.target_file,
    start_line = math.floor(edit.start_line),
    end_line = math.floor(edit.end_line),
    replacement_lines = edit.replacement_lines,
    reason = edit.reason,
  }
end

local function validate_no_complete_lines(state, bufnr, edit)
  for line = edit.start_line, edit.end_line do
    if line_state.is_complete_line(state, bufnr, line) then
      return false, string.format("Blocked edit on complete line %d", line)
    end
  end
  return true
end

function M.apply_result(state, bufnr, ctx, result)
  if not vim.api.nvim_buf_is_valid(bufnr) then
    return { status = "failed", diagnostics = { "invalid_buffer" } }
  end

  if vim.api.nvim_buf_get_changedtick(bufnr) ~= ctx.changedtick_at_start then
    if state.opts.stale_strategy == "retry" then
      return { status = "retry", diagnostics = { "stale_changedtick" } }
    end
    return { status = "stale", diagnostics = { "stale_changedtick" } }
  end

  local edits = {}
  for _, raw in ipairs(result.edits or {}) do
    local edit = normalize_edit(raw)
    if not edit then
      return { status = "failed", diagnostics = { "malformed_edit" } }
    end
    if edit.target_file ~= ctx.target_file then
      return { status = "failed", blocked_reason = "blocked_non_current_file_edit", diagnostics = { "cross_file_write_blocked" } }
    end
    local ok, msg = validate_no_complete_lines(state, bufnr, edit)
    if not ok then
      return { status = "failed", blocked_reason = "attempt_edit_complete_line", diagnostics = { msg } }
    end
    table.insert(edits, edit)
  end

  table.sort(edits, function(a, b)
    return a.start_line > b.start_line
  end)

  local completed_ranges = {}
  for _, edit in ipairs(edits) do
    vim.api.nvim_buf_set_lines(
      bufnr,
      edit.start_line - 1,
      edit.end_line,
      false,
      edit.replacement_lines
    )
    table.insert(completed_ranges, { start_line = edit.start_line, end_line = edit.start_line + math.max(#edit.replacement_lines - 1, 0) })
  end

  line_state.mark_ranges_complete(state, bufnr, completed_ranges)
  line_state.persist(state, bufnr)
  return { status = "success", diagnostics = {} }
end

return M
