import time
import threading
from typing import Callable, Optional

try:
    import mido
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False

class SyntropiaEngine:
    """The heartbeat of the living computer—MIDI-syncable."""
    
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.logical_tick = 0
        self.bpm = 120
        self.pulse_interval = 60.0 / (120 * 24)  # 24 PPQN (pulses per quarter note)
        self.running = False
        self.midi_input = None
        self.midi_output = None
        
        if MIDI_AVAILABLE:
            self._setup_midi()
    
    def _setup_midi(self):
        """Attempt to connect to virtual or hardware MIDI ports."""
        try:
            ports = mido.get_input_names()
            if not ports:
                print("[MIDI] No ports found. Falling back to internal clock.")
                return
            
            # Auto-select first available port (user can override)
            print(f"[MIDI] Available ports: {ports}")
            self.midi_input = mido.open_input(ports[0])
            self.midi_output = mido.open_output(ports[0])
            print(f"[MIDI] Connected to: {ports[0]}")
        except Exception as e:
            print(f"[MIDI] Failed to connect: {e}")
    
    def _send_midi_note(self, note: int, velocity: int = 80):
        """Sonify agent execution events."""
        if self.midi_output:
            try:
                note_on = mido.Message('note_on', note=note, velocity=velocity)
                note_off = mido.Message('note_off', note=note, velocity=0)
                self.midi_output.send(note_on)
                # Schedule note off to prevent hanging notes
                threading.Timer(0.1, lambda: self.midi_output.send(note_off)).start()
            except Exception as e:
                # Silently fail if MIDI connection gets disrupted during computation
                pass
    
    def internal_clock_loop(self, bpm: int = 120):
        """Synthetic clock generator (no DAW required)."""
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
    
    def external_midi_listener(self):
        """Listens for 0xF8 (Timing Clock) pulses from a DAW or sequencer."""
        if not self.midi_input:
            print("[MIDI] No external source available. Using internal clock.")
            return
        
        self.running = True
        print("[MIDI] Waiting for master clock pulses (0xF8)...")
        try:
            for msg in self.midi_input:
                if not self.running:
                    break
                # Status byte 0xF8 corresponds to a MIDI Timing Clock message
                if hasattr(msg, 'type') and msg.type == 'clock':
                    self._tick()
        except Exception as e:
            print(f"[MIDI] Error in external listener: {e}")
            self.running = False
    
    def _tick(self):
        """Single system tick: triggers orchestrator routing and downbeat clicks."""
        self.logical_tick += 1
        
        # Trigger orchestrator execution for the tick
        self.orchestrator.route(self.logical_tick)
        
        # Sonification: emit a subtle MIDI note click on every downbeat (every quarter note / 24 ticks)
        if self.logical_tick % 24 == 0:
            self._send_midi_note(60, velocity=20)  # Play C4 softly

    def update_logical_clock(self, sender_tick: int):
        """Lamport timestamp coordination."""
        self.logical_tick = max(self.logical_tick, sender_tick) + 1
            
    def trigger_agent_sound(self, event_type: str):
        """Helper to play MIDI sounds mapped to agent success/failure events."""
        if not MIDI_AVAILABLE or not self.midi_output:
            return
            
        # Mapping events to specific note frequencies
        if event_type == "success_math":
            self._send_midi_note(72, velocity=80)  # C5 (Bright)
        elif event_type == "retrieve_memory":
            # Play a quick E-G-B arpeggio chord trigger
            self._send_midi_note(64, velocity=60)  # E4
            self._send_midi_note(67, velocity=60)  # G4
            self._send_midi_note(71, velocity=60)  # B4
        elif event_type == "fault_consensus":
            # Play a dissonant chord cluster
            self._send_midi_note(60, velocity=90)  # C4
            self._send_midi_note(66, velocity=90)  # F#4
            self._send_midi_note(67, velocity=90)  # G4
            
    def stop(self):
        self.running = False
        if self.midi_input:
            self.midi_input.close()
        if self.midi_output:
            self.midi_output.close()
