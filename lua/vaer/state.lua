local config = require("vaer.config")

local M = {}

local function deepcopy(v)
  return vim.deepcopy(v)
end

function M.new()
  local cwd = vim.uv.cwd()
  return {
    opts = deepcopy(config.defaults),
    mode = config.defaults.mode,
    project_root = cwd,
    log_path = cwd .. "/tmp/vaer/vaer.log",
    ns = vim.api.nvim_create_namespace("vaer.status"),
    spinner_index = 1,
    spinner_timer = nil,
    task_win = nil,
    task_buf = nil,
    suspend_dispatch = false,
    buffers = {},
    hooks = {},
    initialized = false,
    request = {
      active = {}, -- id -> handle
      active_by_key = {}, -- key -> request_id
      pending_by_key = {}, -- key -> {payload,on_done,opts}
      queue = {}, -- pending function entries
      in_flight_count = 0,
      seq = 0,
      launch_scheduled = false,
    },
  }
end

function M.get_buf(state, bufnr)
  local b = state.buffers[bufnr]
  if b then
    return b
  end
  b = {
    attached = false,
    file = vim.api.nvim_buf_get_name(bufnr),
    status_by_line = {}, -- [line] = complete|progress|working
    working_ranges = {},
    last_changedtick = vim.api.nvim_buf_get_changedtick(bufnr),
    last_line_count = vim.api.nvim_buf_line_count(bufnr),
    dispatch_scheduled = false,
    dispatch_token = 0,
    pending_dispatch = false,
    request_in_flight = false,
    persist_scheduled = false,
    render_scheduled = false,
  }
  state.buffers[bufnr] = b
  return b
end

function M.emit(state, event_name, payload)
  local callbacks = state.hooks[event_name] or {}
  for _, cb in ipairs(callbacks) do
    pcall(cb, payload)
  end
end

function M.on(state, event_name, cb)
  state.hooks[event_name] = state.hooks[event_name] or {}
  table.insert(state.hooks[event_name], cb)
end

return M
