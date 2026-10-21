-- ==============================================================================
-- Syntropia OS — Hyprland Look and Feel (Omarchy Square Edge Styling)
-- ==============================================================================

hl.config({
    general = {
        gaps_in = 4,
        gaps_out = 8,
        border_size = 2,
        -- Generous grab area so a window can be resized by dragging its border
        -- with the mouse alone — no modifier keys, like KDE/Windows.
        extend_border_grab_area = 14,
        resize_on_border = true,
        -- Edge/other-window snapping for floating windows, so they behave like
        -- traditional desktop windows when dragged towards a screen edge.
        snap = {
            enabled = true,
        },
        col = {
            active_border = {
                colors = { "rgba(bd93f9ff)", "rgba(798bb2ff)" }, -- Syntropia purple & slate
                angle = 45,
            },
            inactive_border = "rgba(282a36ff)",
        },
    },
    group = {
        col = {
            border_active = "rgba(bd93f9ff)",
            border_inactive = "rgba(282a36ff)",
            border_locked_active = "rgba(ff79c6ff)",
            border_locked_inactive = "rgba(282a36ff)",
        },
        groupbar = {
            col = {
                active = "rgba(bd93f9ff)",
                inactive = "rgba(282a36ff)",
                locked_active = "rgba(ff79c6ff)",
                locked_inactive = "rgba(282a36ff)",
            },
            gradient_rounding = 0,
        },
    },
    decoration = {
        dim_special = 0.3,
        rounding = 0, -- Omarchy square edges
        active_opacity = 0.98,
        inactive_opacity = 0.90,
        fullscreen_opacity = 1.0,
        blur = {
            enabled = false, -- Clean square aesthetic
            size = 5,
            passes = 4,
            special = true,
        },
        shadow = {
            enabled = false,
        },
    },
})
