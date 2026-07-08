import time
import random
from typing import Optional, Any

class Orchestrator:
    """Manages agent tasks, heartbeat monitoring, and fallback routing."""
    
    def __init__(self):
        self.engine = None
        self.active_agents = {}  # agent_name -> instance
        self.role_map = {}       # role -> list of agent_names
        self.fallbacks = {}      # primary_name -> secondary_name
        self.reputation = {}     # node/agent name -> score
        
    def set_engine(self, engine):
        self.engine = engine

    def register_agent(self, instance, role: str, fallback_name: Optional[str] = None):
        name = getattr(instance, "__class__").__name__
        # Fall back to instance.name if defined
        if hasattr(instance, "name"):
            name = instance.name
            
        self.active_agents[name] = instance
        self.reputation[name] = 100.0  # Starting reputation score
        
        if role not in self.role_map:
            self.role_map[role] = []
        self.role_map[role].append(name)
        
        if fallback_name:
            self.fallbacks[name] = fallback_name
            
        print(f"[Orchestrator] Registered agent '{name}' for role '{role}'")

    def route(self, current_tick: int):
        """Called by the SyntropiaEngine on each heartbeat tick."""
        # Heartbeat check: query all busy agents and check if their execution exceeded timeouts
        pass

    def execute_task(self, role: str, inputs: Any) -> Any:
        """Dispatches a task to the primary agent for the role, falling back if it fails."""
        agent_names = self.role_map.get(role, [])
        if not agent_names:
            raise ValueError(f"No agents found for role '{role}'")

        # Select primary agent (highest reputation)
        primary_name = sorted(agent_names, key=lambda name: self.reputation.get(name, 100.0), reverse=True)[0]
        primary = self.active_agents[primary_name]
        
        print(f"\n\033[1m[Orchestrator] Routing '{role}' task to primary: {primary_name}\033[0m")
        
        # Simulate local execution
        try:
            start_time = time.perf_counter()
            # If engine is attached, play sound for success
            if self.engine:
                # Math role triggers success sounds
                if role == "addition":
                    self.engine.trigger_agent_sound("success_math")
                    
            result = primary.execute(inputs)
            
            # Record reputation bonus
            self.reputation[primary_name] = min(200.0, self.reputation.get(primary_name, 100.0) + 1.0)
            return result
            
        except Exception as e:
            print(f"  \033[31m[Warning] Primary agent '{primary_name}' failed: {e}\033[0m")
            # Update reputation penalty
            self.reputation[primary_name] = max(0.0, self.reputation.get(primary_name, 100.0) - 15.0)
            
            if self.engine:
                self.engine.trigger_agent_sound("fault_consensus")
                
            # Attempt fallback
            fallback_name = self.fallbacks.get(primary_name)
            if fallback_name and fallback_name in self.active_agents:
                print(f"  \033[33m[Fallback] Redirecting to backup: {fallback_name}...\033[0m")
                backup = self.active_agents[fallback_name]
                try:
                    return backup.execute(inputs)
                except Exception as e_backup:
                    print(f"  \033[31m[Critical] Backup agent '{fallback_name}' also failed: {e_backup}\033[0m")
                    
            raise RuntimeError(f"All execution paths for role '{role}' failed.")
