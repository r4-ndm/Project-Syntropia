import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("syntropia.healer")


class ScriptFailureTracker:
    """Tracks script failures and determines when healing is needed."""
    def __init__(self, failure_threshold: int = 3):
        self.failures: Dict[str, int] = {}
        self.threshold = failure_threshold

    def increment_failure(self, script_id: str) -> bool:
        """Increments failure count. Returns True if the threshold is met/exceeded."""
        self.failures[script_id] = self.failures.get(script_id, 0) + 1
        return self.failures[script_id] >= self.threshold

    def reset_failures(self, script_id: str):
        """Resets the failure counter for a script."""
        if script_id in self.failures:
            self.failures[script_id] = 0


class HealerEngine:
    """
    Implements Rule 14 (Phoenix Resurrection Protocol).
    Spawns Healer Agents to repair broken scripts, and falls back to agent
    resurrection from vaporization records if healing fails.
    """
    def __init__(self, orchestrator, failure_threshold: int = 3):
        self.orchestrator = orchestrator
        self.tracker = ScriptFailureTracker(failure_threshold)

    def handle_script_failure(self, script_id: str, role: str, error: str) -> str:
        """
        Main entry point for handling script workers that return failure.
        - Under threshold: log & track.
        - Exceeds threshold: trigger Healer Agent.
        - Healer Agent fails: trigger Agent Resurrection.
        """
        if not self.tracker.increment_failure(script_id):
            logger.info(f"🩺 Healer: Script '{script_id}' failure tracked ({self.tracker.failures[script_id]} fails).")
            return "Logged"

        logger.warning(f"🩺 Healer: Script '{script_id}' has failed repeatedly. Spawning Healer Agent...")
        
        # 1. Simulate Healer Agent trying to resolve the error
        healer_success = self._run_healer_simulation(script_id, error)
        if healer_success:
            logger.info(f"✅ Healer: Healer Agent successfully patched script '{script_id}'. Reseting failures.")
            self.tracker.reset_failures(script_id)
            return "Healed"

        # 2. Fallback: Resurrection of original AI agent
        logger.warning(f"🔥 Healer: Healer Agent failed to patch. Triggering Phoenix Resurrection for '{script_id}'...")
        self._resurrect_agent(script_id, role)
        self.tracker.reset_failures(script_id)
        return "Resurrected"

    def _run_healer_simulation(self, script_id: str, error: str) -> bool:
        """Simulates Healer Agent script patching. Fails on irrecoverable exceptions."""
        if "irrecoverable" in error.lower() or "syntax" in error.lower():
            return False
        return True

    def _resurrect_agent(self, script_id: str, role: str):
        """Resurrects the original AI agent that vaporized into the script."""
        # 1. Create reconstructed resurrected agent instance
        class ResurrectedHermesAgent:
            def __init__(self, name: str, role: str):
                self.name = name
                self.role = role
                self.status = "Resurrected"
                
            def execute(self, inputs):
                # Returns success and triggers vaporization simulation
                return f"Resurrected {self.name} processed: {inputs}"

        agent_name = f"Hermes_{role.capitalize()}"
        resurrected_instance = ResurrectedHermesAgent(agent_name, role)

        # 2. Re-register the agent with Orchestrator routing
        self.orchestrator.register_agent(resurrected_instance, role)

        # 3. Log resurrection on-chain (as a mutation proposal check)
        self.orchestrator.blockchain.register_agent(
            public_key=f"pubkey_{agent_name.lower()}",
            name=agent_name,
            role=role,
            code_hash="resurrected_genesis"
        )
        # Log mutation to verify Rule 14 compliance
        proposal = {
            "status": "Resurrected",
            "target_file": f"/scripts/vaporized_{role}.py",
            "limits": {"memory_mb": 64}
        }
        self.orchestrator.blockchain.log_mutation(
            public_key=f"pubkey_{agent_name.lower()}",
            proposal=proposal,
            signature="resurrection_sig"
        )
        logger.info(f"🧬 Healer: Resurrected agent '{agent_name}' for role '{role}'. Swarm lifecycle restored.")
