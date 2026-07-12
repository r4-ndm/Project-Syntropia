#!/usr/bin/env python3
import argparse
import sys
import threading
import time
import os
import logging

try:
    import tomllib  # Python 3.11+
except ImportError:
    import toml as tomllib  # Fallback for Python < 3.11

from syntropia.registry import AgentRegistry
from syntropia.orchestrator import Orchestrator
from syntropia.engine import SyntropiaEngine

logger = logging.getLogger("syntropia")

DEFAULT_CONFIG = {
    "core": {
        "bpm": 120,
        "agents_dir": "agents"
    },
    "resource": {
        "slider_percentage": 5,
        "only_when_idle": True,
        "idle_threshold_seconds": 300
    },
    "audio": {
        "latency_target_ms": 1,
        "pipewire_config": "/etc/pipewire/pipewire.conf"
    },
    "security": {
        "landlock_enabled": True,
        "seccomp_enabled": True,
        "no_new_privileges": True
    },
    "network": {
        "p2p_protocol": "libp2p",
        "bootstrap_nodes": []
    },
    "logging": {
        "level": "INFO",
        "file": "/var/log/syntropia/syntropia.log"
    }
}

def print_banner():
    # Print color code (cyan)
    sys.stdout.write("\033[1;36m")
    
    # Raw banner with backslashes
    banner = r"""
 ▀█▀ █ █ █▀█ █▀█ ▀ █▀▀   █ █ ▄▀█ █▀▄▀█ █▀▄▀█ █▀▀ █▀█
  █  █▀█ █▄█ █▀▄   ▄▄█   █▀█ █▀█ █ ▀ █ █ ▀ █ ██▄ █▀▄"""
    print(banner)
    
    # Reset color and print subtitle
    sys.stdout.write("\033[0m\n")
    sys.stdout.write("\033[1;33m  \"The Living Computer P2P Torrent Sync Engine\"\033[0m\n")
    sys.stdout.write("  --------------------------------------------------\n")

def setup_logging(config, daemon_mode=False):
    """Sets up unified logging to file and console/journal."""
    log_level_str = config.get("logging", {}).get("level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_file = config.get("logging", {}).get("file", "/var/log/syntropia/syntropia.log")
    
    handlers = []
    
    # File logging
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))
    except Exception:
        # Fallback to local directory log file if system path is not writable
        try:
            handlers.append(logging.FileHandler("syntropia_local.log"))
        except Exception:
            pass # Fallback entirely to stream logging if system is read-only
            
    # Console logging (suppressed in daemon mode since systemd captures journal stdout/stderr)
    if not daemon_mode:
        handlers.append(logging.StreamHandler(sys.stdout))
        
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers
    )

def main():
    parser = argparse.ArgumentParser(description="Syntropia: The Living Computer Node Engine")
    parser.add_argument("--start-node", action="store_true", help="Start the local Syntropia node engine")
    parser.add_argument("--bpm", type=int, default=None, help="Override tempo of the internal tick clock")
    parser.add_argument("--config", type=str, default=None, help="Path to config TOML file")
    parser.add_argument("--daemon", action="store_true", help="Run in background daemon mode (suppresses stream logs)")
    
    args = parser.parse_args()

    if not args.start_node:
        parser.print_help()
        sys.exit(0)

    # Resolve configuration path
    config_path = args.config or os.environ.get("SYNTROPIA_CONFIG")
    if not config_path:
        user_config_path = os.path.expanduser("~/.config/syntropia/config.toml")
        if os.path.exists(user_config_path):
            config_path = user_config_path
        else:
            config_path = "/etc/syntropia/config.toml"
    
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, "rb") as f:
                user_config = tomllib.load(f)
                # Simple dictionary merge
                for key in user_config:
                    if isinstance(config.get(key), dict) and isinstance(user_config[key], dict):
                        config[key].update(user_config[key])
                    else:
                        config[key] = user_config[key]
        except Exception as e:
            logger.error(f"Error loading config file: {e}. Using defaults.")
    else:
        if args.config:
            logger.error(f"Config file not found: {config_path}")
            sys.exit(1)

    setup_logging(config, daemon_mode=args.daemon)
    
    logger.info("Initializing Syntropia Node...")
    if not args.daemon:
        print_banner()

    # Load agent registry
    agents_dir = config["core"]["agents_dir"]
    # Fallback to local directory registry if default /opt path is not found (local testing)
    if not os.path.exists(agents_dir) and agents_dir == "/opt/syntropia/agents" and os.path.exists("agents"):
        agents_dir = "agents"
        
    registry = AgentRegistry(agents_dir=agents_dir)
    registry.scan_and_load()

    # Setup Orchestrator
    orchestrator = Orchestrator()

    # Instantiate and register local agents dynamically
    for name, manifest in registry.manifests.items():
        agent_instance = registry.get_agent_instance(name)
        if agent_instance:
            orchestrator.register_agent(agent_instance, role=manifest.role)
            logger.info(f"Registered agent: {name} (Role: {manifest.role})")

    # Initialize Clock-Tick Engine
    engine = SyntropiaEngine(orchestrator)
    orchestrator.set_engine(engine)

    # Spin up the tick generator loop in a background thread
    bpm = args.bpm or config["core"]["bpm"]
    clock_thread = threading.Thread(target=engine.internal_clock_loop, args=(bpm,), daemon=True)
    clock_thread.start()
    time.sleep(1.0) # Allow engine thread to print bootstrap logs

    # Possess and profile the CachyOS host environment
    logger.info("Profiling Host Environment & Injecting Overlay...")
    from syntropia import CachyHostPossessor
    possessor = CachyHostPossessor()
    env = possessor.detect_host_environment()
    logger.info(f"Host detected: {env['host_os']} | BORE Scheduler: {env['bore_scheduler']} | CPU Cores: {env['cpu_cores']}")
    
    # Run audio tuning
    success, audio_log = possessor.optimize_audio_performance()
    logger.info(f"Audio Optimization: {audio_log}")
    
    # Run sandbox init-layer hardening
    _, sec_log = possessor.init_harden_security()
    logger.info(f"Security Hardening: {sec_log}")
    
    # Start the resource sacrifice daemon
    slider_percentage = config["resource"]["slider_percentage"]
    possessor.start_resource_sacrifice(percentage=slider_percentage)

    # Initialize P2P Layer
    logger.info("Initializing P2P Swarm Layer...")
    from syntropia.gossip import GossipNetwork
    gossip_net = GossipNetwork()
    local_node_id = f"node_{env['host_os'].lower().replace(' ', '_')}"
    local_gossip_node = gossip_net.add_node(local_node_id)
    
    # Initialize P2P Script Registry hooked into local node
    from syntropia.registry import P2PScriptRegistry
    p2p_registry = P2PScriptRegistry(gossip_node=local_gossip_node)
    p2p_registry.subscribe("syntropia/scripts", lambda msg: logger.info(f"P2P script update received: {msg}"))

    # Start Continuous Mutation Loop
    def mutation_loop():
        logger.info("Continuous Mutation Loop active.")
        # Simulates periodic checking of agent status
        while True:
            time.sleep(300) # Check every 5 minutes
            for agent_name in list(orchestrator.active_agents.keys()):
                logger.info(f"[Mutation Loop] Running continuous checks for agent '{agent_name}'...")

    mutation_thread = threading.Thread(target=mutation_loop, daemon=True)
    mutation_thread.start()

    # Keep node alive
    logger.info("Node is running. Ready for task synchronization.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        possessor.stop_resource_sacrifice()
        engine.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()
