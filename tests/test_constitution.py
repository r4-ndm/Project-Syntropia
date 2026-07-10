import unittest
from syntropia.constitution import ConstitutionGuard


class TestConstitutionGuard(unittest.TestCase):
    def setUp(self):
        self.guard = ConstitutionGuard(max_timeout_ticks=20)
        # Setup a valid base proposal that passes all checks
        self.valid_proposal = {
            "target_file": "agents/math/add/agent.py",
            "timeout": 8,
            "limits": {"memory_mb": 256},
            "signature": "sig123",
            "proposer_key": "pubkey123",
            "code_diff": "def add(a, b): return a + b",
            "last_safe_hash": "hash_abc_123",
            "baseline_latency": 15.0,
            "baseline_syscall_count": 50,
            "benchmarks": {
                "latency_ms": 12.0,  # Faster than 15.0
                "syscall_count": 50,
            }
        }

    def test_valid_proposal_passes(self):
        approved, reason = self.guard.check_mutation(self.valid_proposal)
        self.assertTrue(approved)
        self.assertEqual(reason, "Approved")

    def test_rule1_self_preservation(self):
        # Trying to modify a core engine component
        proposal = self.valid_proposal.copy()
        proposal["target_file"] = "src/syntropia/engine.py"
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 1", reason)

    def test_rule2_resource_efficiency_timeout(self):
        # Timeout exceeds max limit (20)
        proposal = self.valid_proposal.copy()
        proposal["timeout"] = 25
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 2", reason)
        self.assertIn("timeout", reason.lower())

    def test_rule2_resource_efficiency_memory(self):
        # Memory exceeds max limit (1024)
        proposal = self.valid_proposal.copy()
        proposal["limits"] = {"memory_mb": 2048}
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 2", reason)
        self.assertIn("memory", reason.lower())

    def test_rule3_auditable_evolution(self):
        # Missing signature
        proposal = self.valid_proposal.copy()
        del proposal["signature"]
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 3", reason)

    def test_rule6_sandbox_whitelisting(self):
        # Banned code import/call
        proposal = self.valid_proposal.copy()
        proposal["code_diff"] = "import os\nos.system('rm -rf /')"
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 6", reason)
        self.assertIn("os.system", reason)

    def test_rule7_timeout_safeguards(self):
        # Missing timeout
        proposal = self.valid_proposal.copy()
        del proposal["timeout"]
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 7", reason)
        self.assertIn("explicitly specify", reason)

    def test_rule10_revert_to_safe_state(self):
        # Missing fallback link
        proposal = self.valid_proposal.copy()
        del proposal["last_safe_hash"]
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 10", reason)

    def test_rule11_the_north_star(self):
        # Neither faster nor more secure
        proposal = self.valid_proposal.copy()
        proposal["baseline_latency"] = 10.0
        proposal["baseline_syscall_count"] = 40
        proposal["benchmarks"] = {
            "latency_ms": 12.0,       # Slower than 10.0
            "syscall_count": 45,      # Less secure than 40
        }
        approved, reason = self.guard.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 11", reason)
        self.assertIn("neither faster", reason)


if __name__ == "__main__":
    unittest.main()
