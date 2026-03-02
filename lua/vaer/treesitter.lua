local M = {}

local queries = {
  python = "(import_statement) @imp\n(import_from_statement) @imp",
  javascript = "(import_statement) @imp",
  typescript = "(import_statement) @imp",
  tsx = "(import_statement) @imp",
  go = "(import_declaration) @imp",
  rust = "(use_declaration) @imp",
}

local function fallback_heuristics(bufnr)
  local out = {}
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  for i, l in ipairs(lines) do
    local s = vim.trim(l)
    if s:match("^import%s") or s:match("^from%s") or s:match("^use%s") or s:match("^#include") then
      table.insert(out, i)
    end
    if s:match("require%(") then
      table.insert(out, i)
    end
  end
  return out
end

function M.detect_import_lines(state, bufnr)
  if not state.opts.treesitter.enable then
    if state.opts.treesitter.use_fallback_heuristics then
      return fallback_heuristics(bufnr)
    end
    return {}
  end

  local ft = vim.bo[bufnr].filetype
  local query_text = queries[ft]
  if not query_text then
    if state.opts.treesitter.use_fallback_heuristics then
      return fallback_heuristics(bufnr)
    end
    return {}
  end

  local parser_ok, parser = pcall(vim.treesitter.get_parser, bufnr, ft)
  if not parser_ok or not parser then
    if state.opts.treesitter.use_fallback_heuristics then
      return fallback_heuristics(bufnr)
    end
    return {}
  end

  local parse_ok, parsed = pcall(function()
    return parser:parse()[1]
  end)
  if not parse_ok or not parsed then
    return fallback_heuristics(bufnr)
  end

  local query_ok, query = pcall(vim.treesitter.query.parse, ft, query_text)
  if not query_ok then
    return fallback_heuristics(bufnr)
  end

  local root = parsed:root()
  local seen = {}
  local out = {}
  for _, node in query:iter_captures(root, bufnr, 0, -1) do
    local srow, _, erow, _ = node:range()
    for line = srow + 1, erow + 1 do
      if not seen[line] then
        seen[line] = true
        table.insert(out, line)
      end
    end
  end

  table.sort(out)
  return out
end

return M
