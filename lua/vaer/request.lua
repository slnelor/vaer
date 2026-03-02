local log = require("vaer.log")

local M = {}

local function next_id(state)
  state.request.seq = state.request.seq + 1
  return string.format("vaer-%d", state.request.seq)
end

local function start_next(state)
  if state.request.in_flight_count >= state.opts.max_parallel_requests then
    return
  end
  local item = table.remove(state.request.queue, 1)
  if not item then
    return
  end
  item.start()
end

function M.cancel_all(state)
  for _, active in pairs(state.request.active) do
    if active.handle and active.handle.kill then
      pcall(active.handle.kill, active.handle, 15)
    end
  end
  state.request.active = {}
  state.request.queue = {}
  state.request.in_flight_count = 0
end

function M.submit(state, payload, on_done)
  local request_id = next_id(state)

  local function run()
    state.request.in_flight_count = state.request.in_flight_count + 1
    local cmd = state.opts.request.command
    if type(cmd) ~= "table" or #cmd == 0 then
      state.request.in_flight_count = state.request.in_flight_count - 1
      on_done({
        request_id = request_id,
        status = "failed",
        diagnostics = { "request.command is not configured" },
        edits = {},
      })
      start_next(state)
      return
    end

    local encoded = vim.json.encode(payload)
    local handle = vim.system(cmd, {
      cwd = state.project_root,
      text = true,
      stdin = encoded,
      timeout = state.opts.request.timeout_ms,
    }, function(obj)
      vim.schedule(function()
        state.request.active[request_id] = nil
        state.request.in_flight_count = math.max(state.request.in_flight_count - 1, 0)

        local result = {
          request_id = request_id,
          status = "failed",
          diagnostics = {},
          edits = {},
        }

        if obj.code ~= 0 then
          result.diagnostics = { "adapter_exit_code=" .. tostring(obj.code), obj.stderr or "" }
          on_done(result)
          start_next(state)
          return
        end

        local ok, decoded = pcall(vim.json.decode, obj.stdout or "")
        if not ok or type(decoded) ~= "table" then
          result.diagnostics = { "invalid_adapter_json" }
          on_done(result)
          start_next(state)
          return
        end

        result.status = "success"
        result.edits = decoded.edits or {}
        result.diagnostics = decoded.diagnostics or {}
        on_done(result)
        start_next(state)
      end)
    end)

    state.request.active[request_id] = { handle = handle }
    log.notify(state, "started request " .. request_id, vim.log.levels.DEBUG)
  end

  if state.request.in_flight_count < state.opts.max_parallel_requests then
    run()
  else
    table.insert(state.request.queue, { start = run })
  end

  return request_id
end

return M
