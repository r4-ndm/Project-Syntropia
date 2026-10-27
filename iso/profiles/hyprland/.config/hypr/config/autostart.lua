-- Auto-start config
-- if you dont use UWSM add your auto start programs here, otherwise use XDG autostart https://wiki.archlinux.org/title/XDG_Autostart

-- Ensure Noctalia first-boot setup wizard / welcome window is suppressed
os.execute("mkdir -p \"${XDG_CONFIG_HOME:-$HOME/.config}/noctalia\" \"${XDG_STATE_HOME:-$HOME/.local/state}/noctalia\" && touch \"${XDG_CONFIG_HOME:-$HOME/.config}/noctalia/.setup-complete\" \"${XDG_STATE_HOME:-$HOME/.local/state}/noctalia/.setup-complete\" 2>/dev/null")

hl.on("hyprland.start", function ()
    hl.exec_cmd("dbus-update-activation-environment --systemd --all")
    hl.exec_cmd("sh -c 'mkdir -p \"${XDG_CONFIG_HOME:-$HOME/.config}/noctalia\" \"${XDG_STATE_HOME:-$HOME/.local/state}/noctalia\" && touch \"${XDG_CONFIG_HOME:-$HOME/.config}/noctalia/.setup-complete\" \"${XDG_STATE_HOME:-$HOME/.local/state}/noctalia/.setup-complete\" && exec noctalia'")
    hl.exec_cmd("xhost +SI:localuser:root")
end)

-- Syntropia overlay autostart & configuration
pcall(require, "config.syntropia")
