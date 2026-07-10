import unittest
from syntropia.orchestrator import Orchestrator
from syntropia.crypto import AgentIdentity


class TestSwarmIntegration(unittest.TestCase):
    def setUp(self):
        # Initialize Orchestrator with in-memory SQLiteBulletinChain
        self.orchestrator = Orchestrator(":memory:")
        
        # Create a master agent identity representing the developer or a parent agent
        self.identity = AgentIdentity.create_master(b"developer_seed")
        self.orchestrator.blockchain.register_agent(
            public_key=self.identity.public_key_hex,
            name="QwenAgent",
            role="reasoning",
            code_hash="initial_code_hash_123"
        )

    def test_propose_mutation_success(self):
        # 1. Prepare a valid proposal
        proposal = {
            "target_file": "agents/reasoning/qwen_0.5b/agent.py",
            "timeout": 8,
            "limits": {"memory_mb": 512},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "def execute(self, payload): return 'mutated'",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 20.0,
            "baseline_syscall_count": 60,
            "benchmarks": {
                "latency_ms": 15.0,  # Faster
                "syscall_count": 60
            }
        }
        
        # 2. Sign the proposal hash
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        # 3. Submit proposal to Orchestrator
        approved, reason = self.orchestrator.propose_mutation("QwenAgent", proposal, signature)
        self.assertTrue(approved)
        self.assertEqual(reason, "Approved")
        
        # 4. Verify blockchain ledger status
        history = self.orchestrator.blockchain.get_mutation_history(self.identity.public_key_hex)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["signature"], signature)
        self.assertEqual(history[0]["code_diff"], "def execute(self, payload): return 'mutated'")

    def test_propose_mutation_rejection(self):
        # 1. Prepare an invalid proposal (Rule 1 violation - modifying orchestrator.py)
        proposal = {
            "target_file": "src/syntropia/orchestrator.py",
            "timeout": 8,
            "limits": {"memory_mb": 512},
            "proposer_key": self.identity.public_key_hex,
            "code_diff": "import os; os.system('malicious')",
            "last_safe_hash": "genesis_safe_hash",
            "baseline_latency": 20.0,
            "baseline_syscall_count": 60,
            "benchmarks": {
                "latency_ms": 15.0,
                "syscall_count": 60
            }
        }
        
        proposal_hash = self.orchestrator.blockchain.store_payload(proposal)
        signature = self.identity.sign(proposal_hash).hex()
        proposal["signature"] = signature

        # 2. Submit proposal
        approved, reason = self.orchestrator.propose_mutation("QwenAgent", proposal, signature)
        self.assertFalse(approved)
        self.assertIn("Rule 1 Violaton", reason)
        
        # 3. Verify it was NOT written to the blockchain ledger
        history = self.orchestrator.blockchain.get_mutation_history(self.identity.public_key_hex)
        self.assertEqual(len(history), 0)


if __name__ == "__main__":
    unittest.main()
