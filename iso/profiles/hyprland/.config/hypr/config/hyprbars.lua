-- ==============================================================================
-- Syntropia OS — Titlebars with window buttons (hyprbars)
-- ==============================================================================
-- Windows float by default in this profile, so every window carries visible
-- controls: a close / maximise / minimise button row, exactly like KDE Plasma or
-- Windows. hyprbars is the upstream Hyprland plugin for this and is AUR-only;
-- iso/build.sh compiles it against the image's own Hyprland headers and installs
-- it at HYPRBARS_MODULE. The plugin is optional at runtime — without the module
-- the rest of the desktop must keep working — so everything below is gated on
-- the file being present.

local HYPRBARS_MODULE = "/usr/lib/hyprland/hyprbars.so"

local function module_installed(path)
    local file = io.open(path, "rb")
    if not file then
        return false
    end
    file:close()
    return true
end

if not module_installed(HYPRBARS_MODULE) then
    return
end

-- Loading happens here rather than in an exec-once so the compositor learns the
-- module before it parses the rest of this file. On the very first pass the
-- plugin is not resident yet, so its config keys and button API do not exist:
-- Hyprland then reloads the config with the plugin in place and everything
-- below applies. Bailing out until then avoids a "nil value" error on boot.
hl.plugin.load(HYPRBARS_MODULE)

-- Harmless when permission enforcement is off; keeps the shipped plugin working
-- for users who turn ecosystem.enforce_permissions on.
hl.permission("/usr/lib/hyprland/hyprbars\\.so", "plugin", "allow")

local hyprbars = hl.plugin and hl.plugin.hyprbars
if not hyprbars or not hyprbars.add_button then
    return
end

---------------------------------------
---- TITLEBAR LOOK (SYNTROPIA) --------
---------------------------------------

hl.config({
    plugin = {
        hyprbars = {
            enabled = true,
            bar_height = 28,
            bar_color = "rgba(282a36ff)",
            col = {
                text = "rgba(f8f8f2ff)",
            },
            bar_title_enabled = true,
            bar_text_size = 11,
            bar_text_font = "Sans",
            bar_text_align = "left",
            bar_padding = 10,
            bar_button_padding = 6,
            bar_buttons_alignment = "right",
            bar_blur = false,
            -- Double-clicking the titlebar maximises, like KDE/Windows.
            on_double_click = "hyprctl dispatch fullscreen 1",
        },
    },
})

---------------------------------------
---- WINDOW BUTTONS (R -> L order) ----
---------------------------------------
-- Buttons are appended right to left, so the list below renders as
-- [minimise] [maximise] [close] — the order users already know.

hyprbars.add_button({
    bg_color = "rgba(ff5555ff)", -- Dracula red
    fg_color = "rgba(282a36ff)",
    size = 12,
    icon = "×",
    action = "hyprctl dispatch killactive",
})

hyprbars.add_button({
    bg_color = "rgba(50fa7bff)", -- Dracula green
    fg_color = "rgba(282a36ff)",
    size = 12,
    icon = "□",
    action = "hyprctl dispatch fullscreen 1",
})

hyprbars.add_button({
    bg_color = "rgba(f1fa8cff)", -- Dracula yellow
    fg_color = "rgba(282a36ff)",
    size = 12,
    icon = "–",
    action = "hyprctl dispatch movetoworkspacesilent special:minimized",
})
