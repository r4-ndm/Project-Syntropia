import unittest
from syntropia.blockchain import SQLiteBulletinChain


class TestSQLiteBulletinChain(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite for isolated tests
        self.chain = SQLiteBulletinChain(":memory:")

    def tearDown(self):
        self.chain.close()

    def test_genesis_block(self):
        cursor = self.chain.conn.cursor()
        cursor.execute("SELECT block_hash, parent_hash FROM blocks ORDER BY block_height ASC LIMIT 1")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        # Parent hash for genesis should be 64-char zeroes
        self.assertEqual(row[1], "0" * 64)

    def test_agent_registration(self):
        pubkey = "test_pubkey_123"
        self.chain.register_agent(pubkey, "TestAgent", "test_role", "code_hash_abc")
        
        agent = self.chain.get_agent(pubkey)
        self.assertIsNotNone(agent)
        self.assertEqual(agent["name"], "TestAgent")
        self.assertEqual(agent["role"], "test_role")
        self.assertEqual(agent["code_hash"], "code_hash_abc")
        self.assertEqual(agent["reputation_score"], 100.0)

    def test_reputation_updates(self):
        pubkey = "test_pubkey_123"
        self.chain.register_agent(pubkey, "TestAgent", "test_role", "code_hash_abc")
        
        # Increase reputation
        score = self.chain.update_reputation(pubkey, 15.5)
        self.assertEqual(score, 115.5)
        self.assertEqual(self.chain.get_agent(pubkey)["reputation_score"], 115.5)
        
        # Decrease reputation
        score = self.chain.update_reputation(pubkey, -30.0)
        self.assertEqual(score, 85.5)
        
        # Upper bounds limit (max 200.0)
        score = self.chain.update_reputation(pubkey, 150.0)
        self.assertEqual(score, 200.0)
        
        # Lower bounds limit (min 0.0)
        score = self.chain.update_reputation(pubkey, -250.0)
        self.assertEqual(score, 0.0)

    def test_content_addressable_storage(self):
        payload = {"data": "hello world", "version": 1, "numbers": [1, 2, 3]}
        cid = self.chain.store_payload(payload)
        
        # Verify CID structure
        self.assertTrue(cid.startswith("cid_"))
        
        # Retrieve and check equivalence
        retrieved = self.chain.get_payload(cid)
        self.assertEqual(retrieved, payload)
        
        # Non-existent CID returns None
        self.assertIsNone(self.chain.get_payload("cid_nonexistent"))

    def test_mutation_logging(self):
        pubkey = "test_pubkey_123"
        self.chain.register_agent(pubkey, "TestAgent", "test_role", "code_hash_abc")
        
        proposal = {
            "code_diff": "def execute(inputs): pass",
            "last_safe_hash": "genesis_safe_hash"
        }
        
        # Log mutation
        block_hash = self.chain.log_mutation(pubkey, proposal, "signature_xyz")
        self.assertIsNotNone(block_hash)
        
        # Check mutation history
        history = self.chain.get_mutation_history(pubkey)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["code_diff"], "def execute(inputs): pass")
        self.assertEqual(history[0]["signature"], "signature_xyz")
        self.assertEqual(history[0]["last_safe_hash"], "genesis_safe_hash")
        
        # Check block table size (should have 2 blocks now: genesis + mutation block)
        cursor = self.chain.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM blocks")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
