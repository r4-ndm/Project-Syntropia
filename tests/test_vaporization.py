import unittest
from unittest.mock import MagicMock
from syntropia.orchestrator import Orchestrator
from syntropia.constitution import ConstitutionGuard
from syntropia.vaporization import TraceLogger, CodeGenerator, ScriptVerifier, VaporizationEngine


class TestVaporization(unittest.TestCase):
    def setUp(self):
        self.orchestrator = Orchestrator()
        
        # Register a mock AI agent in orchestrator mapping
        class MockHermesAgent:
            def __init__(self):
                self.name = "HermesL1"
                self.role = "mock_role"
                self.status = "Active"
                
            def execute(self, inputs):
                return "executed"
                
        self.agent = MockHermesAgent()
        self.orchestrator.active_agents["HermesL1"] = self.agent
        self.orchestrator.role_map["mock_role"] = ["HermesL1"]
        
        # Register in SQLiteBulletinChain
        self.orchestrator.blockchain.register_agent(
            public_key="pubkey_hermes",
            name="HermesL1",
            role="mock_role",
            code_hash="genesis_hash"
        )
        
        self.engine = VaporizationEngine(self.orchestrator)

    def test_trace_logging(self):
        logger = TraceLogger("task_123")
        logger.log_step("hash_crack_attempt", {"hash": "abc1234"}, "success")
        logger.log_step("success_crack", {"plaintext": "admin123"}, "success")
        
        trace = logger.get_trace()
        self.assertEqual(trace["task_id"], "task_123")
        self.assertEqual(trace["total_steps"], 2)
        self.assertEqual(trace["steps"][0]["action"], "hash_crack_attempt")

    def test_code_generation_hash(self):
        generator = CodeGenerator()
        trace = {
            "steps": [
                {"action": "attempt_crack_hash", "details": {}, "status": "success"}
            ]
        }
        script = generator.generate_script(trace)
        self.assertIn("def check_hash", script)
        self.assertIn("hashlib.md5", script)

    def test_code_generation_vst(self):
        generator = CodeGenerator()
        trace = {
            "steps": [
                {"action": "sync_vst_plugins", "details": {}, "status": "success"}
            ]
        }
        script = generator.generate_script(trace)
        self.assertIn("def sync_vst", script)
        self.assertIn("yabridgectl sync", script)

    def test_script_verifier_sandbox_violation(self):
        verifier = ScriptVerifier(self.orchestrator.constitution)
        # Script containing restricted patterns should fail
        bad_script = "import os\nos.system('rm -rf /')"
        is_safe, reason = verifier.verify_safety(bad_script, "scripts/vaporized_script.py")
        self.assertFalse(is_safe)
        self.assertIn("Rule 6 Violation", reason)

    def test_script_verifier_safe(self):
        verifier = ScriptVerifier(self.orchestrator.constitution)
        # Safe script should pass
        good_script = "def add(a, b):\n    return a + b"
        is_safe, reason = verifier.verify_safety(good_script, "scripts/vaporized_script.py")
        self.assertTrue(is_safe)

    def test_rule13_vaporization_violation_limit(self):
        # Memory limit > 128 MB check inside Rule 13
        proposal = {
            "target_file": "scripts/vaporized_script.py",
            "timeout": 5,
            "limits": {"memory_mb": 256},  # Exceeds Rule 13 maximum memory
            "signature": "sig123",
            "proposer_key": "pubkey_hermes",
            "code_diff": "def add(a, b): return a + b",
            "last_safe_hash": "hash_abc_123",
            "baseline_latency": 15.0,
            "benchmarks": {
                "latency_ms": 1.0,
                "syscall_count": 5,
            }
        }
        approved, reason = self.orchestrator.constitution.check_mutation(proposal)
        self.assertFalse(approved)
        self.assertIn("Rule 13 Violation", reason)

    def test_full_vaporization_flow(self):
        # Log mock execution steps
        logger = TraceLogger("task_999")
        logger.log_step("vst_sync_action", {"folder": "/home/r4/vst"}, "success")
        trace = logger.get_trace()
        
        # Execute vaporization
        success, reason = self.engine.vaporize_container(
            agent_name="HermesL1",
            proposer_key="pubkey_hermes",
            trace=trace,
            signature="sig_vapor",
            target_path="scripts/vaporized_script.py"
        )
        
        self.assertTrue(success, f"Vaporization failed: {reason}")
        self.assertEqual(reason, "Vaporized successfully")
        
        # Verify container status is updated to Vaporized
        self.assertEqual(self.agent.status, "Vaporized")
        # Verify it has been removed from active routing mapping
        self.assertNotIn("HermesL1", self.orchestrator.role_map.get("mock_role", []))
        
        # Verify on-chain registration status
        on_chain_agent = self.orchestrator.blockchain.get_agent("pubkey_hermes")
        self.assertEqual(on_chain_agent["status"], "Vaporized")

        # Verify on-chain reap request was logged
        reaps = self.orchestrator.blockchain.get_pending_reaps()
        self.assertEqual(len(reaps), 1)
        self.assertEqual(reaps[0]["container_id"], "HermesL1")

    def test_script_validation_failure_fallback(self):
        # Verify that validation fails for bad syntax / bad return values
        generator = CodeGenerator()
        bad_syntax_code = "def check_hash(target, wordlist_item):\n    return target == wordlist_item\n\n# Syntax error here:\nincomplete code["
        self.assertFalse(generator._validate_script(bad_syntax_code))
        
        bad_logic_code = "def check_hash(target, wordlist_item):\n    return False # Always returns false, failing self-check"
        self.assertFalse(generator._validate_script(bad_logic_code))

    def test_reaper_daemon_execution(self):
        # 1. Log a pending reap request manually
        self.orchestrator.blockchain.add_reap_request(
            container_id="MockHermesContainer",
            public_key="pubkey_hermes",
            signature="sig123"
        )
        
        pending_reaps = self.orchestrator.blockchain.get_pending_reaps()
        self.assertEqual(len(pending_reaps), 1)
        
        # 2. Initialize and run ContainerReaper in mock mode (using database in memory)
        from reaper_daemon import ContainerReaper
        reaper = ContainerReaper(db_path=None)
        # Point daemon to use our active orchestrator database connection
        reaper.blockchain = self.orchestrator.blockchain
        
        # We manually process one iteration instead of infinite loop
        pending = reaper.blockchain.get_pending_reaps()
        for reap in pending:
            reaper._terminate_container(reap["container_id"])
            reaper.blockchain.mark_reaped(reap["id"])
            
        # 3. Verify request is marked as Reaped/completed
        remaining_reaps = self.orchestrator.blockchain.get_pending_reaps()
        self.assertEqual(len(remaining_reaps), 0)

    def test_p2p_registry_sync(self):
        from syntropia.gossip import GossipNode
        from syntropia.registry import P2PScriptRegistry

        # 1. Setup mock gossip peer node
        gossip_peer = GossipNode("node_1")
        p2p_registry = P2PScriptRegistry(gossip_node=gossip_peer)

        # 2. Subscribe and publish script
        p2p_registry.subscribe("syntropia/scripts/vst", lambda msg: None)
        self.assertIn("syntropia/scripts/vst", p2p_registry.subscribed_topics)

        script_code = "def sync_vst():\n    return True"
        cid = p2p_registry.publish("syntropia/scripts/vst", script_code, "sig_peer")

        # 3. Verify payload was synced to the gossip node's local ledger
        self.assertIn(cid, gossip_peer.ledger)
        self.assertEqual(gossip_peer.ledger[cid]["script"], script_code)
        self.assertEqual(gossip_peer.ledger[cid]["signature"], "sig_peer")


if __name__ == "__main__":
    unittest.main()
