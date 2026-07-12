import time
import random
import logging
import threading
from typing import Optional, Any, Dict, Tuple, Set

logger = logging.getLogger("syntropia.orchestrator")

class Orchestrator:
    """Manages agent tasks, heartbeat monitoring, and fallback routing."""
    
    def __init__(self, db_path: str = ":memory:"):
        self.engine = None
        self.active_agents = {}  # agent_name -> instance
        self.role_map = {}       # role -> list of agent_names
        self.fallbacks = {}      # primary_name -> secondary_name
        self.reputation = {}     # node/agent name -> score
        
        # Track active executions
        self.active_tasks: Dict[str, dict] = {}
        self.task_counter = 0
        self.lock = threading.Lock()
        
        # Governance and ledger
        from syntropia.constitution import ConstitutionGuard
        from syntropia.blockchain import SQLiteBulletinChain
        self.blockchain = SQLiteBulletinChain(db_path)
        self.constitution = ConstitutionGuard()
        
        # Evolution Engine
        from syntropia.evolution import EvolutionEngine
        self.evolution = EvolutionEngine(self)
        
        # Vaporization Engine
        from syntropia.vaporization import VaporizationEngine
        self.vaporization = VaporizationEngine(self)
        
    def set_engine(self, engine):
        self.engine = engine

    def register_agent(self, instance, role: str, fallback_name: Optional[str] = None):
        name = getattr(instance, "__class__").__name__
        if hasattr(instance, "name"):
            name = instance.name
            
        self.active_agents[name] = instance
        self.reputation[name] = 100.0  # Starting reputation score
        
        if role not in self.role_map:
            self.role_map[role] = []
        self.role_map[role].append(name)
        
        if fallback_name:
            self.fallbacks[name] = fallback_name
            
        logger.info(f"Registered agent '{name}' for role '{role}'")

    def _select_next_fallback(self, task: dict) -> Optional[str]:
        """Selects the next best fallback agent for the task, excluding already tried agents."""
        current_agent = task["agent_name"]
        
        # 1. Follow the explicit fallback chain
        explicit_fallback = self.fallbacks.get(current_agent)
        while explicit_fallback:
            if explicit_fallback in self.active_agents and explicit_fallback not in task["tried_agents"]:
                return explicit_fallback
            explicit_fallback = self.fallbacks.get(explicit_fallback)
            
        # 2. Otherwise find other agents registered for this role with the highest reputation
        role = task["role"]
        agent_names = self.role_map.get(role, [])
        available_agents = [name for name in agent_names if name not in task["tried_agents"] and name in self.active_agents]
        
        if available_agents:
            # Sort by reputation descending
            best_fallback = sorted(available_agents, key=lambda name: self.reputation.get(name, 100.0), reverse=True)[0]
            return best_fallback
            
        return None

    def route(self, current_tick: int):
        """Called by the SyntropiaEngine on each heartbeat tick."""
        with self.lock:
            # Check for running tasks that have timed out logically
            for task_id, task in list(self.active_tasks.items()):
                if task["status"] == "running":
                    start_tick = task["start_tick"]
                    timeout = task["timeout"]
                    
                    if current_tick - start_tick > timeout:
                        agent_name = task["agent_name"]
                        logger.warning(
                            f"Timeout detected for task {task_id} on agent '{agent_name}' "
                            f"(logical tick: {current_tick}, started: {start_tick}, limit: {timeout} ticks)"
                        )
                        
                        # Penalize reputation
                        self.reputation[agent_name] = max(0.0, self.reputation.get(agent_name, 100.0) - 15.0)
                        task["status"] = "timeout"
                        
                        if self.engine:
                            self.engine.trigger_agent_sound("fault_consensus")
                            
                        # Redirect to fallback if available
                        fallback_name = self._select_next_fallback(task)
                        if fallback_name:
                            self._start_fallback(task, fallback_name)
                        else:
                            task["error"] = RuntimeError(
                                f"Task {task_id} timed out on agent '{agent_name}' and no remaining fallback was available."
                            )
                            task["status"] = "failed"
                            task["event"].set()

    def _start_fallback(self, task: dict, fallback_name: str):
        """Dispatches the fallback agent for a task under lock."""
        logger.info(f"Redirecting task {task['task_id']} to backup agent '{fallback_name}'...")
        fallback_agent = self.active_agents[fallback_name]
        
        current_tick = self.engine.logical_tick if self.engine else 0
        task["agent_name"] = fallback_name
        task["start_tick"] = current_tick
        task["timeout"] = getattr(fallback_agent, "timeout", 5)
        task["status"] = "running"
        task["tried_agents"].add(fallback_name)
        
        def run_fallback():
            try:
                result = fallback_agent.execute(task["inputs"])
                with self.lock:
                    # Thread safety check: only update task if this agent is still the active dispatcher
                    if task["status"] == "running" and task["agent_name"] == fallback_name:
                        task["status"] = "success"
                        task["result"] = result
                        self.reputation[fallback_name] = min(200.0, self.reputation.get(fallback_name, 100.0) + 1.0)
                        task["event"].set()
            except Exception as e_fallback:
                with self.lock:
                    if task["status"] == "running" and task["agent_name"] == fallback_name:
                        logger.warning(f"Fallback agent '{fallback_name}' failed: {e_fallback}")
                        self.reputation[fallback_name] = max(0.0, self.reputation.get(fallback_name, 100.0) - 15.0)
                        
                        if self.engine:
                            self.engine.trigger_agent_sound("fault_consensus")
                            
                        # Redirect to next fallback level
                        next_fallback = self._select_next_fallback(task)
                        if next_fallback:
                            self._start_fallback(task, next_fallback)
                        else:
                            task["status"] = "failed"
                            task["error"] = e_fallback
                            task["event"].set()

        t = threading.Thread(target=run_fallback, daemon=True)
        t.start()

    def execute_task(self, role: str, inputs: Any) -> Any:
        """Dispatches a task to the primary agent for the role, falling back if it fails/times out."""
        agent_names = self.role_map.get(role, [])
        if not agent_names:
            raise ValueError(f"No agents found for role '{role}'")

        # Select primary agent (highest reputation)
        primary_name = sorted(agent_names, key=lambda name: self.reputation.get(name, 100.0), reverse=True)[0]
        primary = self.active_agents[primary_name]
        timeout = getattr(primary, "timeout", 5)
        
        with self.lock:
            self.task_counter += 1
            task_id = f"task_{self.task_counter}"
            current_tick = self.engine.logical_tick if self.engine else 0
            event = threading.Event()
            
            task_record = {
                "task_id": task_id,
                "role": role,
                "agent_name": primary_name,
                "inputs": inputs,
                "start_tick": current_tick,
                "timeout": timeout,
                "status": "running",
                "event": event,
                "result": None,
                "error": None,
                "tried_agents": {primary_name}
            }
            self.active_tasks[task_id] = task_record

        logger.info(f"Routing '{role}' task to primary: {primary_name} (Logical Clock: {current_tick}, Timeout: {timeout} ticks)")
        
        def run_execution():
            try:
                # Support simulated mock delay in inputs (for testing timeouts)
                if isinstance(inputs, dict) and "mock_delay_seconds" in inputs:
                    time.sleep(inputs["mock_delay_seconds"])
                    
                result = primary.execute(inputs)
                
                with self.lock:
                    # Thread safety check: only update task if this agent is still the active dispatcher
                    if task_record["status"] == "running" and task_record["agent_name"] == primary_name:
                        task_record["status"] = "success"
                        task_record["result"] = result
                        self.reputation[primary_name] = min(200.0, self.reputation.get(primary_name, 100.0) + 1.0)
                        
                        if self.engine:
                            # Update logical clock (Lamport Timestamp coordination)
                            self.engine.update_logical_clock(current_tick)
                            if role == "addition":
                                self.engine.trigger_agent_sound("success_math")
                        task_record["event"].set()
            except Exception as e:
                with self.lock:
                    if task_record["status"] == "running" and task_record["agent_name"] == primary_name:
                        logger.warning(f"Primary agent '{primary_name}' failed: {e}")
                        self.reputation[primary_name] = max(0.0, self.reputation.get(primary_name, 100.0) - 15.0)
                        
                        if self.engine:
                            self.engine.trigger_agent_sound("fault_consensus")
                            
                        # Attempt fallback
                        fallback_name = self._select_next_fallback(task_record)
                        if fallback_name:
                            self._start_fallback(task_record, fallback_name)
                        else:
                            task_record["status"] = "failed"
                            task_record["error"] = e
                            task_record["event"].set()

        t = threading.Thread(target=run_execution, daemon=True)
        t.start()
        
        # Block until event matches success, failure, or timeout redirect completion
        event.wait()
        
        with self.lock:
            # Clean up active tasks registry
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]
            
            if task_record["status"] == "success":
                return task_record["result"]
            elif task_record["error"]:
                raise task_record["error"]
            else:
                raise RuntimeError(f"Task execution finished with unexpected status: {task_record['status']}")

    def propose_mutation(self, agent_name: str, proposal: Dict[str, Any], signature: str) -> Tuple[bool, str]:
        """
        Proposes a code mutation for an active agent.
        The proposal must pass the Constitution checks and get committed on-chain.
        Delegates to the Evolution Engine which implements 'Mutate First, Ask Questions Later'.
        """
        return self.evolution.mutate_agent(agent_name, proposal, signature)

    def vaporize_agent(
        self,
        agent_name: str,
        proposer_key: str,
        trace: Dict[str, Any],
        signature: str,
        target_path: str = "scripts/vaporized_script.py"
    ) -> Tuple[bool, str]:
        """
        Vaporizes an active AI agent into a deterministic script.
        """
        return self.vaporization.vaporize_container(
            agent_name=agent_name,
            proposer_key=proposer_key,
            trace=trace,
            signature=signature,
            target_path=target_path
        )


