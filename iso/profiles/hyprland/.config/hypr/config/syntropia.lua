-- ==============================================================================
-- Syntropia OS — Hyprland Audio, Workflow & Styling Overlay
-- ==============================================================================

local mainMod = "SUPER"

---------------------------------------
---- OMARCHY SQUARE EDGE STYLING ------
---------------------------------------

hl.config({
    general = {
        border_size = 2,
        col = {
            active_border = {
                colors = { "rgba(bd93f9ff)", "rgba(798bb2ff)" },
                angle = 45,
            },
            inactive_border = "rgba(282a36ff)",
        },
    },
    decoration = {
        rounding = 0, -- Omarchy square edges
        shadow = {
            enabled = false,
        },
        blur = {
            enabled = false,
        },
    },
})

-----------------------------------------------
---- FLOATING WINDOWS (TRADITIONAL DESKTOP) ---
-----------------------------------------------

-- New users expect an application to open in its own frame and stay where they
-- put it, not to be auto-tiled into the layout. This catch-all rule floats every
-- window (KDE/Windows-style). It lives in the Syntropia overlay, which
-- hyprland.lua requires last, so it also wins over any upstream "float: false"
-- rule; the app-specific rules below still layer their own placement on top.
hl.window_rule({
    name = "syntropia-float-by-default",
    match = { class = ".*" },
    float = true,
})

---------------------------------------
---- AUDIO & DAW FLOATING WINDOWS ----
---------------------------------------

-- REAPER FX and Plugin windows
hl.window_rule({
    match = {
        class = "^(REAPER)$",
        title = "^(FX: .*|VST: .*|VST3: .*|CLAP: .*|JS: .*|Plugin.*)$",
    },
    float = true,
})

-- Bitwig Studio Plugin windows
hl.window_rule({
    match = {
        class = "^(Bitwig Studio)$",
        title = "^(Plugin: .*)$",
    },
    float = true,
})

-- Syntropia App Wizard & Floating Helpers
hl.window_rule({
    match = { title = ".*app-wiz4rd.*" },
    float = true,
    center = true,
})

hl.window_rule({
    match = { class = "^(floating_terminal)$" },
    float = true,
    center = true,
    size = { "840", "640" },
})

-----------------------------------------
---- WALLPAPER & THEME SELECTOR ---------
-----------------------------------------

-- Omarchy-style hotkey: Super + Ctrl + Space toggles wallpaper panel
hl.bind(mainMod .. " + CONTROL + space", hl.dsp.exec_cmd("uwsm app -- /usr/local/bin/syntropia-wallpaper-picker toggle"))
-- Alternative hotkey: Super + Shift + W
hl.bind(mainMod .. " + SHIFT + W",       hl.dsp.exec_cmd("uwsm app -- /usr/local/bin/syntropia-wallpaper-picker toggle"))
-- Quick random wallpaper: Super + Ctrl + W
hl.bind(mainMod .. " + CONTROL + W",     hl.dsp.exec_cmd("uwsm app -- /usr/local/bin/syntropia-wallpaper-picker random"))

-----------------------------------
---- NAVIGATION & CHEATSHEET ------
-----------------------------------

-- Keybindings cheatsheet
hl.bind(mainMod .. " + slash", hl.dsp.exec_cmd("uwsm app -- /usr/local/bin/syntropia-cheatsheet"))
hl.bind(mainMod .. " + SHIFT + slash", hl.dsp.exec_cmd("uwsm app -- /usr/local/bin/syntropia-cheatsheet"))

-- Vim-style navigation fallback
hl.bind(mainMod .. " + H", hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "down" }))

hl.bind(mainMod .. " + SHIFT + H", hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + K", hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + J", hl.dsp.window.move({ direction = "down" }))

-- Bring back windows minimised with the yellow titlebar button
hl.bind(mainMod .. " + SHIFT + M", hl.dsp.workspace.toggle_special("minimized"))
