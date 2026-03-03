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
  local s = math.floor(edit.start_line)
  local e = math.floor(edit.end_line)
  if e < s then
    s, e = e, s
  end
  return {
    target_file = edit.target_file,
    start_line = s,
    end_line = e,
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

local function is_inside_progress_ranges(progress_ranges, edit)
  for _, r in ipairs(progress_ranges or {}) do
    if edit.start_line <= r.end_line and edit.end_line >= r.start_line then
      return true
    end
  end
  return false
end

local function is_destructive_empty(edit)
  if #edit.replacement_lines > 0 then
    return false
  end
  return edit.end_line >= edit.start_line
end

local function is_blank_only(lines)
  for _, line in ipairs(lines) do
    if vim.trim(line) ~= "" then
      return false
    end
  end
  return true
end

local function is_noop_edit(bufnr, edit)
  local current = vim.api.nvim_buf_get_lines(bufnr, edit.start_line - 1, edit.end_line, false)
  if #current ~= #edit.replacement_lines then
    return false
  end
  for i = 1, #current do
    if current[i] ~= edit.replacement_lines[i] then
      return false
    end
  end
  return true
end

function M.apply_result(state, bufnr, ctx, result)
  if not vim.api.nvim_buf_is_valid(bufnr) then
    return { status = "failed", diagnostics = { "invalid_buffer" } }
  end

  local changedtick_mismatch = vim.api.nvim_buf_get_changedtick(bufnr) ~= ctx.changedtick_at_start
  if changedtick_mismatch and not state.opts.request.allow_stale_apply then
    if state.opts.stale_strategy == "retry" then
      return { status = "retry", diagnostics = { "stale_changedtick" } }
    end
    return { status = "stale", diagnostics = { "stale_changedtick" } }
  end

  local edits = {}
  local max_edit_count = (state.opts.apply and state.opts.apply.max_edit_count) or 8
  local max_edit_lines = (state.opts.apply and state.opts.apply.max_edit_lines) or 120
  local max_replacement_lines = (state.opts.apply and state.opts.apply.max_replacement_lines) or 240
  local max_total_replacement_lines = (state.opts.apply and state.opts.apply.max_total_replacement_lines) or 480
  local reject_blank_replacements = state.opts.apply == nil
    or state.opts.apply.reject_blank_replacements == nil
    or state.opts.apply.reject_blank_replacements
  local buf_line_count = vim.api.nvim_buf_line_count(bufnr)
  local total_replacement_lines = 0

  for _, raw in ipairs(result.edits or {}) do
    local edit = normalize_edit(raw)
    if not edit then
      return { status = "failed", diagnostics = { "malformed_edit" } }
    end

    if edit.start_line < 1 or edit.end_line > buf_line_count then
      goto continue
    end

    if (edit.end_line - edit.start_line + 1) > max_edit_lines then
      goto continue
    end

    if #edit.replacement_lines > max_replacement_lines then
      goto continue
    end

    if #edits >= max_edit_count then
      goto continue
    end

    if (total_replacement_lines + #edit.replacement_lines) > max_total_replacement_lines then
      goto continue
    end

    if edit.target_file ~= ctx.target_file then
      return { status = "failed", blocked_reason = "blocked_non_current_file_edit", diagnostics = { "cross_file_write_blocked" } }
    end
    if not is_inside_progress_ranges(ctx.progress_ranges, edit) then
      goto continue
    end
    if is_destructive_empty(edit) then
      goto continue
    end
    if reject_blank_replacements and is_blank_only(edit.replacement_lines) then
      goto continue
    end
    local ok, msg = validate_no_complete_lines(state, bufnr, edit)
    if not ok then
      goto continue
    end
    if is_noop_edit(bufnr, edit) then
      goto continue
    end
    table.insert(edits, edit)
    total_replacement_lines = total_replacement_lines + #edit.replacement_lines
    ::continue::
  end

  if #edits == 0 then
    return { status = "failed", diagnostics = { "no_applicable_edits" } }
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
  if changedtick_mismatch then
    return { status = "success", diagnostics = { "stale_changedtick_applied" } }
  end
  return { status = "success", diagnostics = {} }
end

return M
