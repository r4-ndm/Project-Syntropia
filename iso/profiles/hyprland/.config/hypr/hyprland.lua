-- CachyOS Hyprland Configuration with Syntropia Overlay

require("config.animations")
require("config.autostart")
require("config.colors")
require("config.decorations")
require("config.hyprbars")
require("config.variables")
require("config.environment")
require("config.inputs")
require("config.binds")
require("config.misc")
require("config.monitors")
require("config.windowrules")
require("config.workspaces")

-- Syntropia Audio & Hotkey Overlay (loaded last: its floating-by-default
-- window rule must win over upstream "float: false" rules)
pcall(require, "config.syntropia")
