import time
import threading
from typing import Callable, Optional

class SyntropiaEngine:
    """The heartbeat of the living computer—coordinating task cycles and ticks."""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.logical_tick = 0
        self.bpm = 120
        self.pulse_interval = 60.0 / (120 * 24)  # 24 pulses per quarter note interval
        self.running = False
    
    def internal_clock_loop(self, bpm: int = 120):
        """Synthetic clock generator loop."""
        self.bpm = bpm
        self.pulse_interval = 60.0 / (bpm * 24.0)
        self.running = True
        
        print(f"[Engine] Internal clock started at {bpm} BPM.")
        while self.running:
            start = time.perf_counter()
            self._tick()
            elapsed = time.perf_counter() - start
            sleep_time = max(0, self.pulse_interval - elapsed)
            time.sleep(sleep_time)
            
    def _tick(self):
        """Single system tick: triggers orchestrator routing."""
        self.logical_tick += 1
        self.orchestrator.route(self.logical_tick)

    def update_logical_clock(self, sender_tick: int):
        """Lamport timestamp coordination."""
        self.logical_tick = max(self.logical_tick, sender_tick) + 1
            
    def trigger_agent_sound(self, event_type: str):
        """Stub for agent event sonification (MIDI interface removed)."""
        pass
            
    def stop(self):
        self.running = False
