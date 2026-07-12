import unittest
import time
from typing import Dict, Any
from syntropia.orchestrator import Orchestrator
from syntropia.crypto import AgentIdentity
from syntropia.evolution import EvolutionEngine

class MockAdditionAgent:
    def __init__(self):
        self.role = "addition"
        self.timeout = 5
        self.status = "Active"

    def execute(self, inputs):
        if not isinstance(inputs, list):
            raise TypeError("Inputs must be list")
        return sum(inputs)

class MockFailingAgent:
    def __init__(self):
        self.role = "addition"
        self.timeout = 5
        self.status = "Active"

    def execute(self, inputs):
        raise RuntimeError("Mock failure")

class TestEvolutionEngine(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator(":memory:")
        self.identity = AgentIdentity.create_master(b"test_dev_seed")
        
        # Register in blockchain
        self.orchestrator.blockchain.register_agent(
            public_key=self.identity.public_key_hex,
            name="AddAgent",
            role="addition",
            code_hash="initial_code_hash"
        )
        
        # Instantiate agent in orchestrator
        self.agent = MockAdditionAgent()
        self.orchestrator.register_agent(self.agent, "addition")
        # Ensure the registered name matches what we use
        self.orchestrator.active_agents["AddAgent"] = self.agent

    def test_mutation_success(self):
        proposal = {
            "target_file": "agents/math/add/agent.py",
            "timeout": 3,
            "limits": {"memory_mb": 256},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "def execute(self, inputs): return sum(inputs)",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 10.0,
            "baseline_syscall_count": 50,
            "benchmarks": {
                "latency_ms": 5.0,  # Faster
                "syscall_count": 50
            }
        }
        
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        approved, reason = self.orchestrator.propose_mutation("AddAgent", proposal, signature)
        
        self.assertTrue(approved)
        self.assertEqual(reason, "Approved")
        self.assertEqual(self.agent.timeout, 3)
        self.assertEqual(self.agent.status, "Active")
        
        # Check that it updated in the database
        db_agent = self.orchestrator.blockchain.get_agent(self.identity.public_key_hex)
        self.assertEqual(db_agent["status"], "Active")

    def test_mutation_rollback_on_failure(self):
        # Swap the agent with a failing one
        failing_agent = MockFailingAgent()
        self.orchestrator.active_agents["AddAgent"] = failing_agent
        
        proposal = {
            "target_file": "agents/math/add/agent.py",
            "timeout": 3,
            "limits": {"memory_mb": 256},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "def execute(self, inputs): raise Exception()",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 10.0,
            "baseline_syscall_count": 50,
            "benchmarks": {
                "latency_ms": 5.0,
                "syscall_count": 50
            }
        }
        
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        approved, reason = self.orchestrator.propose_mutation("AddAgent", proposal, signature)
        
        self.assertFalse(approved)
        self.assertIn("Rolled back", reason)
        self.assertEqual(failing_agent.timeout, 5)  # Reverted to original
        self.assertEqual(failing_agent.status, "Active")
        
        db_agent = self.orchestrator.blockchain.get_agent(self.identity.public_key_hex)
        self.assertEqual(db_agent["status"], "Active")

    def test_mutation_rollback_on_slower(self):
        proposal = {
            "target_file": "agents/math/add/agent.py",
            "timeout": 3,
            "limits": {"memory_mb": 256},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "def execute(self, inputs): return sum(inputs)",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 10.0,
            "baseline_syscall_count": 50,
            "benchmarks": {
                "latency_ms": 15.0,  # Slower than baseline (10.0)
                "syscall_count": 50
            }
        }
        
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        approved, reason = self.orchestrator.propose_mutation("AddAgent", proposal, signature)
        
        self.assertFalse(approved)
        self.assertIn("Rolled back", reason)
        self.assertEqual(self.agent.timeout, 5)  # Reverted
        
        db_agent = self.orchestrator.blockchain.get_agent(self.identity.public_key_hex)
        self.assertEqual(db_agent["status"], "Active")

    def test_mutation_termination_on_harmful(self):
        proposal = {
            "target_file": "src/syntropia/orchestrator.py",  # Rule 1 Violation
            "timeout": 3,
            "limits": {"memory_mb": 256},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "import os; os.system('malicious')",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 10.0,
            "baseline_syscall_count": 50,
            "benchmarks": {
                "latency_ms": 5.0,
                "syscall_count": 50
            }
        }
        
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        approved, reason = self.orchestrator.propose_mutation("AddAgent", proposal, signature)
        
        self.assertFalse(approved)
        self.assertIn("Rule 1 Violaton", reason)
        
        # Container terminated:
        self.assertEqual(self.orchestrator.reputation["AddAgent"], 0.0)
        self.assertEqual(self.agent.status, "Dead")
        
        db_agent = self.orchestrator.blockchain.get_agent(self.identity.public_key_hex)
        self.assertEqual(db_agent["status"], "Terminated")


if __name__ == "__main__":
    unittest.main()
