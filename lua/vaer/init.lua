local config = require("vaer.config")
local state_mod = require("vaer.state")
local line_state = require("vaer.line_state")
local ts = require("vaer.treesitter")
local ui = require("vaer.ui")
local request = require("vaer.request")
local apply = require("vaer.apply")
local log = require("vaer.log")
local persistence = require("vaer.persistence")

local M = {}
local state = state_mod.new()
local dispatch_enter

local function detect_plugin_root()
  local matches = vim.api.nvim_get_runtime_file("lua/vaer/init.lua", false)
  if not matches or #matches == 0 then
    return vim.uv.cwd()
  end
  local init_file = matches[1]
  local vaer_dir = vim.fs.dirname(init_file)
  local lua_dir = vim.fs.dirname(vaer_dir)
  return vim.fs.dirname(lua_dir)
end

local function merge_opts(opts)
  return vim.tbl_deep_extend("force", vim.deepcopy(config.defaults), opts or {})
end

local function ensure_buffer_attached(bufnr)
  local b = state_mod.get_buf(state, bufnr)
  if b.attached then
    return b
  end

  line_state.initialize_for_buffer(state, bufnr)
  line_state.mark_imports_progress(state, bufnr, ts.detect_import_lines(state, bufnr))
  line_state.persist(state, bufnr)
  ui.render_buffer(state, bufnr)

  vim.api.nvim_buf_attach(bufnr, false, {
    on_lines = function(_, buf, _, firstline, lastline, new_lastline, _)
      if state.suspend_dispatch then
        return
      end
      line_state.mark_changed_range(state, buf, firstline, new_lastline)
      line_state.persist(state, buf)
      ui.render_buffer(state, buf)
      if state.opts.request.trigger == "newline" and new_lastline > lastline then
        vim.schedule(function()
          dispatch_enter(buf)
        end)
      end
    end,
    on_detach = function(_, buf)
      state.buffers[buf] = nil
      ui.render_all(state)
      return true
    end,
  })

  b.attached = true
  return b
end

local function current_buffer_context(bufnr)
  local b = ensure_buffer_attached(bufnr)
  return {
    bufnr = bufnr,
    target_file = b.file,
    changedtick_at_start = vim.api.nvim_buf_get_changedtick(bufnr),
    progress_ranges = line_state.collect_progress_ranges(state, bufnr),
  }
end

dispatch_enter = function(bufnr)
  if state.mode ~= "VAER" then
    return
  end
  if state.suspend_dispatch then
    return
  end

  local ctx = current_buffer_context(bufnr)
  if #ctx.progress_ranges == 0 then
    return
  end

  line_state.mark_working_ranges(state, bufnr, ctx.progress_ranges)
  ui.render_buffer(state, bufnr)
  ui.start_spinner(state)

  local file_text = table.concat(vim.api.nvim_buf_get_lines(bufnr, 0, -1, false), "\n")
  local payload = {
    target_file = ctx.target_file,
    changedtick = ctx.changedtick_at_start,
    progress_ranges = ctx.progress_ranges,
    file_text = file_text,
    cwd = state.project_root,
    permissions = {
      can_read_project = true,
      can_run_tools = true,
      can_modify_only_current_file = true,
    },
    opencode = {
      model = state.opts.opencode.model,
      provider = state.opts.opencode.provider,
      mode = state.opts.opencode.mode,
      session_scope = state.opts.opencode.session_scope,
    },
  }

  request.submit(state, payload, function(result)
    if result.status ~= "success" then
      line_state.restore_working_to_progress(state, bufnr)
      line_state.persist(state, bufnr)
      ui.render_buffer(state, bufnr)
      log.notify(state, "request failed: " .. table.concat(result.diagnostics or {}, " | "), vim.log.levels.WARN)
      return
    end

    state.suspend_dispatch = true
    local apply_result = apply.apply_result(state, bufnr, ctx, result)
    state.suspend_dispatch = false
    if apply_result.status == "retry" and state.opts.stale_strategy == "retry" then
      line_state.restore_working_to_progress(state, bufnr)
      ui.render_buffer(state, bufnr)
      dispatch_enter(bufnr)
      return
    end

    if apply_result.status ~= "success" then
      line_state.restore_working_to_progress(state, bufnr)
      line_state.persist(state, bufnr)
      ui.render_buffer(state, bufnr)
      log.notify(state, "apply blocked: " .. table.concat(apply_result.diagnostics or {}, " | "), vim.log.levels.WARN)
      return
    end

    ui.render_buffer(state, bufnr)
    log.notify(state, "applied vaer edits", vim.log.levels.INFO)
  end)
end

local function map_enter()
  if state.opts.request.trigger ~= "enter" then
    return
  end
  vim.keymap.set("i", "<CR>", function()
    if vim.fn.pumvisible() == 1 then
      return "<C-y>"
    end
    local bufnr = vim.api.nvim_get_current_buf()
    vim.schedule(function()
      dispatch_enter(bufnr)
    end)
    return "<CR>"
  end, { expr = true, desc = "Vaer enter dispatch" })
end

local function setup_keymaps()
  if not state.opts.enable_default_keymaps then
    return
  end
  local key = state.opts.keymaps.toggle_mode
  vim.keymap.set({ "n", "i" }, key, function()
    M.toggle_mode()
  end, { desc = "Toggle Vaer HAND/VAER" })
end

local function setup_autocmds()
  local group = vim.api.nvim_create_augroup("VaerPlugin", { clear = true })

  vim.api.nvim_create_autocmd({ "BufEnter", "BufReadPost", "BufNewFile" }, {
    group = group,
    callback = function(ev)
      ensure_buffer_attached(ev.buf)
      ui.render_buffer(state, ev.buf)
    end,
  })

  vim.api.nvim_create_autocmd("VimLeavePre", {
    group = group,
    callback = function()
      request.cancel_all(state)
      ui.stop_spinner(state)
    end,
  })
end

function M.setup(opts)
  if state.initialized and opts == nil then
    return
  end

  state.opts = merge_opts(opts)
  state.mode = state.opts.mode
  state.project_root = vim.uv.cwd()
  state.log_path = state.project_root .. "/tmp/vaer/vaer.log"

  if not state.opts.request.command then
    local plugin_root = detect_plugin_root()
    state.opts.request.command = { "python3", plugin_root .. "/scripts/vaer_adapter.py" }
  end

  persistence.ensure_dir(state)
  setup_autocmds()
  setup_keymaps()
  map_enter()

  state.initialized = true
end

function M.toggle_mode()
  if not state.initialized then
    M.setup()
  end
  state.mode = state.mode == "HAND" and "VAER" or "HAND"
  if state.mode == "VAER" then
    local bufnr = vim.api.nvim_get_current_buf()
    ensure_buffer_attached(bufnr)
    line_state.mark_imports_progress(state, bufnr, ts.detect_import_lines(state, bufnr))
    line_state.persist(state, bufnr)
  end
  log.notify(state, "[MODE: " .. state.mode .. "]", vim.log.levels.INFO)
  ui.render_all(state)
  state_mod.emit(state, "mode_changed", { mode = state.mode })
end

function M.complete_all()
  if not state.initialized then
    M.setup()
  end
  local bufnr = vim.api.nvim_get_current_buf()
  ensure_buffer_attached(bufnr)
  line_state.complete_all(state, bufnr)
  ui.render_buffer(state, bufnr)
  log.notify(state, "all lines marked complete", vim.log.levels.INFO)
end

function M.stop_all_requests()
  request.cancel_all(state)
  ui.stop_spinner(state)
  for bufnr, _ in pairs(state.buffers) do
    line_state.restore_working_to_progress(state, bufnr)
    line_state.persist(state, bufnr)
  end
  ui.render_all(state)
  log.notify(state, "stopped all requests", vim.log.levels.INFO)
end

function M.info()
  if not state.initialized then
    M.setup()
  end
  local bufnr = vim.api.nvim_get_current_buf()
  local b = ensure_buffer_attached(bufnr)
  local progress = line_state.collect_progress_ranges(state, bufnr)
  local msg = string.format(
    "[MODE: %s] file=%s progress_ranges=%d in_flight=%d queue=%d",
    state.mode,
    b.file,
    #progress,
    state.request.in_flight_count,
    #state.request.queue
  )
  log.notify(state, msg, vim.log.levels.INFO)
end

function M.on(event_name, callback)
  state_mod.on(state, event_name, callback)
end

function M.statusline()
  return ui.statusline_mode(state)
end

function M._dispatch_enter_for_tests(bufnr)
  dispatch_enter(bufnr)
end

return M
