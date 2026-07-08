#!/usr/bin/env python3
import argparse
import sys
import threading
import time
from syntropia.registry import AgentRegistry
from syntropia.orchestrator import Orchestrator
from syntropia.engine import SyntropiaEngine
from syntropia.thor_hammer import ThorHammer

def print_banner():
    # Print color code (cyan)
    sys.stdout.write("\033[1;36m")
    
    # Raw banner with backslashes
    banner = r"""
  _______ __                 __  __                                
 /_  __// /_  ____  _____   / / / /___ _____ ___  ____ ___  ___  _____
  / /  / __ \/ __ \/ ___/  / /_/ / __ `/ __ `__ \/ __ `__ \/ _ \/ ___/
 / /  / / / / /_/ / /     / __  / /_/ / / / / / / / / / / /  __/ /    
/_/  /_/ /_/\____/_/     /_/ /_/\__,_/_/ /_/ /_/_/ /_/ /_/\___/_/     """
    print(banner)
    
    # Reset color and print subtitle
    sys.stdout.write("\033[0m\n")
    sys.stdout.write("\033[1;33m  \"The Living Computer P2P Torrent Sync Engine\"\033[0m\n")
    sys.stdout.write("  --------------------------------------------------\n")

def main():
    parser = argparse.ArgumentParser(description="Syntropia: The Living Computer Node Engine")
    parser.add_argument("--start-node", action="store_true", help="Start the local Syntropia node engine")
    parser.add_argument("--bpm", type=int, default=120, help="Tempo of the internal tick clock (default: 120)")
    parser.add_argument("--midi-master", action="store_true", help="Synchronize ticks to external MIDI Timing Clock")
    parser.add_argument("--no-midi", action="store_true", help="Disable MIDI port connectivity and sonification")
    
    args = parser.parse_args()

    if not args.start_node:
        parser.print_help()
        sys.exit(0)

    print_banner()

    # 1. Initialize Registry and scan agents/
    registry = AgentRegistry(agents_dir="agents")
    registry.scan_and_load()

    # 2. Run Thor Hammer P2P model synchronization
    thor_hammer = ThorHammer()
    thor_hammer.sync_models(registry)

    # 3. Setup Orchestrator
    orchestrator = Orchestrator()

    # 3. Instantiate and register local agents dynamically
    for name, manifest in registry.manifests.items():
        agent_instance = registry.get_agent_instance(name)
        if agent_instance:
            orchestrator.register_agent(agent_instance, role=manifest.role)

    # 4. Initialize Clock-Tick Engine
    if args.no_midi:
        # Override mido import inside engine to force fallback
        import syntropia.engine
        syntropia.engine.MIDI_AVAILABLE = False
        print("[System] Running in silent / no-MIDI mode.")

    engine = SyntropiaEngine(orchestrator)
    orchestrator.set_engine(engine)

    # 5. Spin up the tick generator loop in a background thread
    if args.midi_master:
        clock_thread = threading.Thread(target=engine.external_midi_listener, daemon=True)
    else:
        clock_thread = threading.Thread(target=engine.internal_clock_loop, args=(args.bpm,), daemon=True)

    clock_thread.start()
    time.sleep(1.0) # Allow engine thread to print bootstrap logs

    # 6. Execute a sample calculation task to prove the engine works
    print("\n\033[1;33m[Main] Sending query task to swarm: addition of [15, 27, 42]...\033[0m")
    try:
        result = orchestrator.execute_task("addition", [15, 27, 42])
        print(f"\033[1;32m[Main] Result returned: {result} (Expected: 84)\033[0m")
    except Exception as e:
        print(f"\033[1;31m[Main] Task failed: {e}\033[0m")

    # Keep node alive for demonstration
    print("\n\033[36m[Node] Node is running. Press Ctrl+C to terminate the node.\033[0m")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[Node] Shutting down...")
        engine.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()
