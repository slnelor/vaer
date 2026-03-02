local M = {}

local function level_name(level)
  if level == vim.log.levels.ERROR then
    return "ERROR"
  end
  if level == vim.log.levels.WARN then
    return "WARN"
  end
  if level == vim.log.levels.INFO then
    return "INFO"
  end
  return "DEBUG"
end

function M.notify(state, msg, level)
  level = level or vim.log.levels.INFO
  if state and state.opts and state.opts.notify then
    vim.notify(msg, level, { title = "vaer" })
  end

  local line = string.format("[%s] %s\n", level_name(level), msg)
  local path = state and state.log_path
  if path and path ~= "" then
    pcall(vim.fn.writefile, { line }, path, "a")
  end
end

return M
