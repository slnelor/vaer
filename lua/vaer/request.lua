local ui = require("vaer.ui")

local M = {}

local function build_command(state, cmd)
  local nice_value = state.opts.request.process_priority_nice
  if type(nice_value) == "number" and vim.fn.executable("nice") == 1 then
    local full = { "nice", "-n", tostring(math.floor(nice_value)) }
    for _, part in ipairs(cmd) do
      table.insert(full, part)
    end
    return full
  end
  return cmd
end

local function next_id(state)
  state.request.seq = state.request.seq + 1
  return string.format("vaer-%d", state.request.seq)
end

local function schedule_launch(state, delay_ms)
  if state.request.launch_scheduled then
    return
  end

  state.request.launch_scheduled = true
  vim.defer_fn(function()
    state.request.launch_scheduled = false
    if state.request.in_flight_count >= state.opts.max_parallel_requests then
      return
    end

    local item = table.remove(state.request.queue, 1)
    if not item then
      return
    end

    item.start()

    if state.request.in_flight_count < state.opts.max_parallel_requests and #state.request.queue > 0 then
      schedule_launch(state, state.opts.request.launch_stagger_ms or 120)
    end
  end, delay_ms or 0)
end

local function purge_queued_for_key(state, key)
  for i = #state.request.queue, 1, -1 do
    local q = state.request.queue[i]
    if q and q.key == key then
      table.remove(state.request.queue, i)
    end
  end
end

local function schedule_pending_for_key(state, key)
  local pending = state.request.pending_by_key[key]
  if not pending then
    return
  end
  state.request.pending_by_key[key] = nil
  M.submit(state, pending.payload, pending.on_done, pending.opts)
end

function M.cancel_all(state)
  for _, active in pairs(state.request.active) do
    if active.handle and active.handle.kill then
      pcall(active.handle.kill, active.handle, 15)
    end
  end
  state.request.active = {}
  state.request.active_by_key = {}
  state.request.pending_by_key = {}
  state.request.queue = {}
  state.request.in_flight_count = 0
  state.request.launch_scheduled = false
  ui.render_task_window(state)
end

function M.submit(state, payload, on_done, opts)
  opts = opts or {}
  local key = opts.key
  local supersede = opts.supersede == true
  local cancel_active = opts.cancel_active_on_supersede == true

  if supersede and type(key) == "string" then
    purge_queued_for_key(state, key)
  end

  if supersede and type(key) == "string" and state.request.active_by_key[key] then
    state.request.pending_by_key[key] = {
      payload = payload,
      on_done = on_done,
      opts = opts,
    }

    if cancel_active then
      local active_request_id = state.request.active_by_key[key]
      local active = active_request_id and state.request.active[active_request_id] or nil
      if active and active.handle and active.handle.kill then
        pcall(active.handle.kill, active.handle, 15)
      end
    end

    return state.request.active_by_key[key]
  end

  local request_id = next_id(state)

  local function run()
    state.request.in_flight_count = state.request.in_flight_count + 1
    local cmd = state.opts.request.command
    if type(cmd) ~= "table" or #cmd == 0 then
      state.request.in_flight_count = state.request.in_flight_count - 1
      ui.render_task_window(state)
      on_done({
        request_id = request_id,
        status = "failed",
        diagnostics = { "request.command is not configured" },
        edits = {},
      })
      schedule_launch(state, state.opts.request.launch_stagger_ms or 120)
      return
    end

    local launch_cmd = build_command(state, cmd)
    local encoded = vim.json.encode(payload)
    local handle = vim.system(launch_cmd, {
      cwd = state.project_root,
      text = true,
      stdin = encoded,
      timeout = state.opts.request.timeout_ms,
    }, function(obj)
      vim.schedule(function()
        local active = state.request.active[request_id]
        local active_key = active and active.key or nil
        state.request.active[request_id] = nil
        if type(active_key) == "string" then
          state.request.active_by_key[active_key] = nil
        end
        state.request.in_flight_count = math.max(state.request.in_flight_count - 1, 0)
        ui.render_task_window(state)

        local result = {
          request_id = request_id,
          status = "failed",
          diagnostics = {},
          edits = {},
        }

        if obj.code ~= 0 then
          result.diagnostics = { "adapter_exit_code=" .. tostring(obj.code), obj.stderr or "" }
          on_done(result)
          if type(active_key) == "string" then
            schedule_pending_for_key(state, active_key)
          end
          schedule_launch(state, state.opts.request.launch_stagger_ms or 120)
          return
        end

        local ok, decoded = pcall(vim.json.decode, obj.stdout or "")
        if not ok or type(decoded) ~= "table" then
          result.diagnostics = { "invalid_adapter_json" }
          on_done(result)
          if type(active_key) == "string" then
            schedule_pending_for_key(state, active_key)
          end
          schedule_launch(state, state.opts.request.launch_stagger_ms or 120)
          return
        end

        result.status = "success"
        result.edits = decoded.edits or {}
        result.diagnostics = decoded.diagnostics or {}
        on_done(result)
        if type(active_key) == "string" then
          schedule_pending_for_key(state, active_key)
        end
        schedule_launch(state, state.opts.request.launch_stagger_ms or 120)
      end)
    end)

    state.request.active[request_id] = { handle = handle, key = key }
    if type(key) == "string" then
      state.request.active_by_key[key] = request_id
    end
    ui.render_task_window(state)
  end

  table.insert(state.request.queue, { start = run, key = key })
  ui.render_task_window(state)
  schedule_launch(state, 0)

  return request_id
end

return M
