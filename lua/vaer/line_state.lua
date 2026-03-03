local persistence = require("vaer.persistence")

local M = {}

local COMPLETE = "complete"
local PROGRESS = "progress"
local WORKING = "working"

M.COMPLETE = COMPLETE
M.PROGRESS = PROGRESS
M.WORKING = WORKING

function M.initialize_for_buffer(state, bufnr)
  local b = require("vaer.state").get_buf(state, bufnr)
  local file = b.file
  local count = vim.api.nvim_buf_line_count(bufnr)

  b.status_by_line = {}

  local cached = persistence.load(state, file)
  if type(cached) == "table" then
    for k, v in pairs(cached) do
      local line = tonumber(k)
      if line and line >= 1 and line <= count and type(v) == "string" then
        if v == PROGRESS then
          b.status_by_line[line] = PROGRESS
        elseif v == WORKING then
          b.status_by_line[line] = PROGRESS
        end
      end
    end
  end

  b.last_changedtick = vim.api.nvim_buf_get_changedtick(bufnr)
  return b
end

function M.persist(state, bufnr)
  local b = require("vaer.state").get_buf(state, bufnr)
  persistence.save(state, b.file, b.status_by_line)
end

function M.mark_changed_range(state, bufnr, firstline_zero, new_lastline_zero)
  local b = require("vaer.state").get_buf(state, bufnr)
  b.last_changedtick = vim.api.nvim_buf_get_changedtick(bufnr)
  b.last_line_count = vim.api.nvim_buf_line_count(bufnr)

  if state.mode ~= "VAER" then
    return
  end

  local start_line = firstline_zero + 1
  local finish_line = math.max(start_line, new_lastline_zero)
  for i = start_line, finish_line do
    b.status_by_line[i] = PROGRESS
  end
end

function M.mark_imports_progress(state, bufnr, import_lines)
  if state.mode ~= "VAER" then
    return
  end
  local b = require("vaer.state").get_buf(state, bufnr)
  for _, line in ipairs(import_lines) do
    b.status_by_line[line] = PROGRESS
  end
end

function M.collect_progress_ranges(state, bufnr)
  local b = require("vaer.state").get_buf(state, bufnr)
  local lines = {}
  for line, status in pairs(b.status_by_line) do
    if status == PROGRESS then
      table.insert(lines, line)
    end
  end
  table.sort(lines)

  local ranges = {}
  if #lines == 0 then
    return ranges
  end

  local s = lines[1]
  local prev = lines[1]
  for i = 2, #lines do
    local ln = lines[i]
    if ln == prev + 1 then
      prev = ln
    else
      table.insert(ranges, { start_line = s, end_line = prev })
      s = ln
      prev = ln
    end
  end
  table.insert(ranges, { start_line = s, end_line = prev })
  return ranges
end

function M.mark_working_ranges(state, bufnr, ranges)
  local b = require("vaer.state").get_buf(state, bufnr)
  b.working_ranges = ranges
  for _, r in ipairs(ranges) do
    for i = r.start_line, r.end_line do
      if b.status_by_line[i] == PROGRESS then
        b.status_by_line[i] = WORKING
      end
    end
  end
end

function M.mark_ranges_complete(state, bufnr, ranges)
  local b = require("vaer.state").get_buf(state, bufnr)
  for _, r in ipairs(ranges) do
    for i = r.start_line, r.end_line do
      b.status_by_line[i] = nil
    end
  end
  b.working_ranges = {}
end

function M.restore_working_to_progress(state, bufnr)
  local b = require("vaer.state").get_buf(state, bufnr)
  for _, r in ipairs(b.working_ranges) do
    for i = r.start_line, r.end_line do
      if b.status_by_line[i] == WORKING then
        b.status_by_line[i] = PROGRESS
      end
    end
  end
  b.working_ranges = {}
end

function M.complete_all(state, bufnr)
  local b = require("vaer.state").get_buf(state, bufnr)
  b.status_by_line = {}
  b.working_ranges = {}
  M.persist(state, bufnr)
end

function M.is_complete_line(state, bufnr, line)
  local b = require("vaer.state").get_buf(state, bufnr)
  return (b.status_by_line[line] or COMPLETE) == COMPLETE
end

return M
