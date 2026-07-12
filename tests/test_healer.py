import unittest
from unittest.mock import MagicMock
from syntropia.orchestrator import Orchestrator
from syntropia.healer import HealerEngine, ScriptFailureTracker


class TestHealerAndPhoenixProtocol(unittest.TestCase):

    def setUp(self):
        self.orchestrator = Orchestrator()
        # Mock engine to prevent threading logical tick dependency
        self.orchestrator.engine = MagicMock()
        self.orchestrator.engine.logical_tick = 10

    def test_failure_tracker_threshold(self):
        tracker = ScriptFailureTracker(failure_threshold=3)
        self.assertFalse(tracker.increment_failure("script_a"))
        self.assertFalse(tracker.increment_failure("script_a"))
        self.assertTrue(tracker.increment_failure("script_a"))
        
        tracker.reset_failures("script_a")
        self.assertFalse(tracker.increment_failure("script_a"))

    def test_script_healing_under_threshold(self):
        healer = HealerEngine(self.orchestrator, failure_threshold=3)
        # 1st failure - returns Logged
        status = healer.handle_script_failure("script_1", "worker", "Some recoverable exception")
        self.assertEqual(status, "Logged")

    def test_healer_patches_successfully(self):
        healer = HealerEngine(self.orchestrator, failure_threshold=2)
        # 1st failure
        healer.handle_script_failure("script_1", "worker", "Some recoverable exception")
        # 2nd failure - exceeds threshold, tries healing. Recoverable exception -> success.
        status = healer.handle_script_failure("script_1", "worker", "Some recoverable exception")
        self.assertEqual(status, "Healed")

    def test_phoenix_agent_resurrection(self):
        healer = HealerEngine(self.orchestrator, failure_threshold=2)
        
        # 1st failure
        healer.handle_script_failure("script_failed", "hash_crack", "irrecoverable database corruption")
        
        # 2nd failure - exceeds threshold, healer fails due to 'irrecoverable' in error -> resurrect agent
        status = healer.handle_script_failure("script_failed", "hash_crack", "irrecoverable database corruption")
        self.assertEqual(status, "Resurrected")
        
        # Verify that resurrected agent is now registered in orchestrator
        self.assertIn("Hermes_Hash_crack", self.orchestrator.active_agents)
        resurrected_agent = self.orchestrator.active_agents["Hermes_Hash_crack"]
        self.assertEqual(resurrected_agent.status, "Resurrected")
        
        # Verify that on-chain registration and mutation logs comply with Rule 14
        agent_data = self.orchestrator.blockchain.get_agent("pubkey_hermes_hash_crack")
        self.assertIsNotNone(agent_data)
        self.assertEqual(agent_data["name"], "Hermes_Hash_crack")
        
        mutations = self.orchestrator.blockchain.get_mutation_history("pubkey_hermes_hash_crack")
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0]["status"], "Logged")


if __name__ == "__main__":
    unittest.main()
