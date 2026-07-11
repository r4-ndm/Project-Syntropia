import unittest
from syntropia.gossip import XORErasureCoder, GossipNetwork, GossipNode

class TestGossipAndErasure(unittest.TestCase):

    def test_erasure_coding_roundtrip(self):
        original_data = b"Syntropia: Universal Self-Assembling Swarm Computer."
        K = 4
        
        # 1. Encode into K+1 chunks (4 data + 1 parity)
        chunks = XORErasureCoder.encode(original_data, K)
        self.assertEqual(len(chunks), K + 1)
        
        # 2. Decode using all chunks
        decoded = XORErasureCoder.decode(chunks, K, len(original_data))
        self.assertEqual(decoded, original_data)

    def test_erasure_coding_recovery_missing_data_chunk(self):
        original_data = b"Techno DAW Synthesizer Module"
        K = 3
        chunks = XORErasureCoder.encode(original_data, K)
        
        # Remove a data chunk (index 1)
        reduced_chunks = [c for c in chunks if c[0] != 1]
        self.assertEqual(len(reduced_chunks), K)
        
        # Decode should still recover the original data using the parity chunk
        decoded = XORErasureCoder.decode(reduced_chunks, K, len(original_data))
        self.assertEqual(decoded, original_data)

    def test_erasure_coding_recovery_missing_parity(self):
        original_data = b"Blockchain Ledgers Are Stateless"
        K = 3
        chunks = XORErasureCoder.encode(original_data, K)
        
        # Remove the parity chunk (index K = 3)
        reduced_chunks = [c for c in chunks if c[0] != K]
        self.assertEqual(len(reduced_chunks), K)
        
        # Decode should still recover the original data using just the data chunks
        decoded = XORErasureCoder.decode(reduced_chunks, K, len(original_data))
        self.assertEqual(decoded, original_data)

    def test_erasure_coding_insufficient_chunks(self):
        original_data = b"Small payload"
        K = 3
        chunks = XORErasureCoder.encode(original_data, K)
        
        # Remove two chunks (only 2 left, we need K=3)
        reduced_chunks = chunks[:2]
        with self.assertRaises(ValueError):
            XORErasureCoder.decode(reduced_chunks, K, len(original_data))

    def test_gossip_rumor_dissemination(self):
        net = GossipNetwork()
        for i in range(5):
            net.add_node(f"node_{i}")
            
        net.fully_connect()
        
        # Trigger rumor from node_0
        net.trigger_gossip_rumor("node_0", "cid_rep_99", {"reputation": "node_x_adjust_minus_15"})
        
        # Ensure all nodes received and updated their ledger
        for i in range(5):
            node = net.nodes[f"node_{i}"]
            self.assertIn("cid_rep_99", node.ledger)
            self.assertEqual(node.ledger["cid_rep_99"]["reputation"], "node_x_adjust_minus_15")

    def test_anti_entropy_sync(self):
        # Create node A and B, not connected directly
        node_a = GossipNode("node_a")
        node_b = GossipNode("node_b")
        
        node_a.ledger["cid_block_1"] = "Block 1 content"
        node_b.ledger["cid_block_2"] = "Block 2 content"
        
        # Perform anti-entropy sync between A and B
        node_a.anti_entropy_check(node_b)
        
        # Both nodes should have both blocks now
        self.assertIn("cid_block_1", node_a.ledger)
        self.assertIn("cid_block_2", node_a.ledger)
        self.assertIn("cid_block_1", node_b.ledger)
        self.assertIn("cid_block_2", node_b.ledger)

if __name__ == "__main__":
    unittest.main()
