# MIDI Clock Integration: The Syntropia Conductor 🎵

## Overview
Syntropia can be synchronized to a MIDI Beat Clock, allowing a human operator or a Digital Audio Workstation (DAW) to control the speed of computation in real-time.

---

## The Core Mechanics
- **Protocol**: MIDI Timing Clock (24 pulses per quarter note, status byte `0xF8`).
- **Binding**: One MIDI pulse = One Syntropia system tick.
- **Speed Control**: Adjusting BPM in your DAW instantly speeds up or slows down the agent swarm.

---

## Tempo Mapping (BPM to Agent Behavior)

| BPM Range | System Behavior |
| :--- | :--- |
| **20 - 40 BPM** (Larghissimo) | **Debug Mode**. Watch heartbeat failovers and consensus negotiations in ultra-slow motion. |
| **60 - 80 BPM** (Andante) | **Standard Simulation**. Clear visual representation of agent routing. |
| **120 - 140 BPM** (Moderato) | **High-Performance Production**. Maximum node throughput. |
| **180+ BPM** (Prestissimo) | **Stress Testing**. Evolve the swarm at maximum speed to benchmark stability. |

---

## Sonification: The Computer Sings
When Syntropia runs on MIDI, every agent action becomes a musical event:
- **Arithmetic Agent (Success)** $\rightarrow$ Triggers a high C note (C5) via MIDI out.
- **Memory Agent (Retrieve)** $\rightarrow$ Triggers a soft arpeggio (E-G-B).
- **Consensus Fault / Rollback** $\rightarrow$ Triggers a dissonant cluster (C + F# + G).
- **Evolution Cycle (New Agent Born)** $\rightarrow$ Triggers a rising pitch bend over 500ms.

> This creates a real-time "audio signature" of the computer's health and activity.

---

## Implementation Path
1. **Internal Clock**: Use Python's `mido` to generate a synthetic clock if no DAW is connected.
2. **External Sync**: Connect to a DAW via a virtual MIDI port (e.g., `IAC Driver` on macOS, `loopMIDI` on Windows).
3. **Fallback**: If MIDI hardware is unavailable, the system automatically reverts to a high-precision software timer (`time.perf_counter`).
