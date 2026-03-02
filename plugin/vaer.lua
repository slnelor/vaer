if vim.g.loaded_vaer == 1 then
  return
end
vim.g.loaded_vaer = 1

vim.api.nvim_create_user_command("VaerToggleMode", function()
  require("vaer").toggle_mode()
end, { desc = "Toggle Vaer HAND/VAER mode" })

vim.api.nvim_create_user_command("VaerCompleteAll", function()
  require("vaer").complete_all()
end, { desc = "Mark all lines complete" })

vim.api.nvim_create_user_command("VaerStopAll", function()
  require("vaer").stop_all_requests()
end, { desc = "Cancel all in-flight Vaer requests" })

vim.api.nvim_create_user_command("VaerInfo", function()
  require("vaer").info()
end, { desc = "Show Vaer mode and buffer state" })

vim.schedule(function()
  require("vaer").setup()
end)
