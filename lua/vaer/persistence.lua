local M = {}

local function get_cache_dir(state)
  return state.project_root .. "/" .. state.opts.cache.dir
end

local function file_key(path)
  return vim.fn.sha256(path):sub(1, 16)
end

local function state_path(state, file_path)
  return string.format("%s/state_%s.json", get_cache_dir(state), file_key(file_path))
end

function M.ensure_dir(state)
  if not state.opts.cache.enabled then
    return
  end
  vim.fn.mkdir(get_cache_dir(state), "p")
end

function M.save(state, file_path, status_by_line)
  if not state.opts.cache.enabled then
    return
  end
  M.ensure_dir(state)
  local payload = {
    target_file = file_path,
    status_by_line = status_by_line,
  }
  local encoded = vim.json.encode(payload)
  vim.fn.writefile({ encoded }, state_path(state, file_path), "b")
end

function M.load(state, file_path)
  if not state.opts.cache.enabled then
    return nil
  end
  local path = state_path(state, file_path)
  if vim.fn.filereadable(path) ~= 1 then
    return nil
  end
  local lines = vim.fn.readfile(path, "b")
  local raw = table.concat(lines, "\n")
  local ok, decoded = pcall(vim.json.decode, raw)
  if not ok or type(decoded) ~= "table" then
    return nil
  end
  return decoded.status_by_line
end

return M
