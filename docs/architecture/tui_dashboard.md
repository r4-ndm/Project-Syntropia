# Architecture Spec: Native Python TUI Dashboard 🖥️

To display the live state of the living computer—agent heartbeats, torrent downloads, model seeding, and logical BPM clocks—Syntropia uses a terminal-based dashboard built directly in Python.

---

## 🎨 Interface Layout Design

The TUI splits the terminal screen into a modular grid:

```text
┌───────────────────────────────────────┯───────────────────────────────────────┐
│  🌀 SYNTROPIA: THE LIVING COMPUTER    │  🐜 ACTIVE AGENT SWARM POPULATION     │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ Node Status: [Active]                 │ • AdditionAgent v1   [Idle]  Fit: 105 │
│ Local Clock: 120 BPM                  │ • MulAgent v1        [Idle]  Fit: 100 │
│ Logical Tick: 1482 pulses             │ • Storage_Alpha v1   [Idle]  Fit: 100 │
│ Active Swarm Connections: 4 peers     │ • Qwen_0.5B_Chat v2  [Busy]  Fit: 115 │
│                                       │                                       │
├───────────────────────────────────────┼───────────────────────────────────────┤
│  📥 BACKGROUND TORRENT WEIGHT SYNC     │  📻 EVENT MONITOR / SONIFICATION LOGS │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ Qwen-2.5-0.5B-Instruct.gguf           │ [Tick 1480] Dispatched 'addition' task │
│ █▓░░░░░░░░░░░░░░░░░░ [15% - 2.1 MB/s]  │ [Tick 1482] AdditionAgent success (+C5)│
│ Seeding: OLMo-1B-Instruct.gguf         │ [Tick 1485] Warning: Peer Berlin slow │
│ Seeders: 12  | Upload Speed: 850 KB/s  │ [Tick 1488] Route fallback -> Local   │
├───────────────────────────────────────┴───────────────────────────────────────┤
│ > Enter Calculation or Prompt (e.g. 5 * 2 + 1): _____________________________ │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Key UI Sections:
1. **System Metadata Panel (Top-Left)**: Monitors local CPU/RAM constraints, network sync statistics, and current clock rate (BPM).
2. **Agent Swarm Panel (Top-Right)**: Displays the active local agent registry, their current execution state (`Idle`, `Busy`, `Unresponsive`, `Dead`), and their evolutionary fitness scores.
3. **Torrent Downloader Panel (Bottom-Left)**: Displays active model weight file downloads (similar to the progress layout in Thor Hammer), download percentages, seed/peer counts, and upload speed.
4. **Log Monitor (Bottom-Right)**: Real-time scrolling output of the Orchestrator routing path.
5. **Interactive Console Bar (Bottom)**: Allows typing queries directly into the living computer without exiting the monitor.

---

## ⌨️ Keyboard Navigation Shortcuts

| Key | Action |
| :--- | :--- |
| **`Tab`** | Move focus between the Input Console and the Panels. |
| **`+` / `-`** | Increase / decrease internal clock BPM (tempo). |
| **`m`** | Toggle MIDI output (Sonification audio mute). |
| **`t`** | Toggle clock sync master (Internal timer vs. External MIDI). |
| **`Ctrl+C`** | Safe shutdown of the node and background torrent seeders. |
