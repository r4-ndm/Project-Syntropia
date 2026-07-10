import unittest
from syntropia.crypto import AgentIdentity


class TestCryptoIdentity(unittest.TestCase):
    def test_master_identity_creation(self):
        # Deterministic master creation
        seed_material = b"test_seed_material_123_456_789"
        identity1 = AgentIdentity.create_master(seed_material)
        identity2 = AgentIdentity.create_master(seed_material)
        
        self.assertEqual(identity1.seed, identity2.seed)
        self.assertEqual(identity1.chain_code, identity2.chain_code)
        self.assertEqual(identity1.public_key_bytes, identity2.public_key_bytes)
        self.assertEqual(identity1.public_key_hex, identity2.public_key_hex)
        
        # Verify length of keys
        self.assertEqual(len(identity1.seed), 32)
        self.assertEqual(len(identity1.chain_code), 32)
        self.assertEqual(len(identity1.public_key_bytes), 32)

    def test_random_master_creation(self):
        # Two random master identities must be different
        identity1 = AgentIdentity.create_master()
        identity2 = AgentIdentity.create_master()
        self.assertNotEqual(identity1.seed, identity2.seed)
        self.assertNotEqual(identity1.public_key_bytes, identity2.public_key_bytes)

    def test_child_key_derivation_determinism(self):
        master = AgentIdentity.create_master(b"master_seed")
        
        # Child derivation must be deterministic
        child1_a = master.derive_child(1)
        child1_b = master.derive_child(1)
        self.assertEqual(child1_a.public_key_bytes, child1_b.public_key_bytes)
        
        # Different index derives different child key
        child2 = master.derive_child(2)
        self.assertNotEqual(child1_a.public_key_bytes, child2.public_key_bytes)
        
        # Hierarchy: child can derive grandchild
        grandchild_a = child1_a.derive_child(5)
        grandchild_b = child1_b.derive_child(5)
        self.assertEqual(grandchild_a.public_key_bytes, grandchild_b.public_key_bytes)

    def test_sign_and_verify(self):
        identity = AgentIdentity.create_master()
        message = b"Syntropia Swarm Message 2026"
        
        # Sign
        signature = identity.sign(message)
        self.assertEqual(len(signature), 64)
        
        # Verify with instance public key
        is_valid = AgentIdentity.verify(identity.public_key, message, signature)
        self.assertTrue(is_valid)
        
        # Verify with public key bytes
        is_valid_bytes = AgentIdentity.verify(identity.public_key_bytes, message, signature)
        self.assertTrue(is_valid_bytes)
        
        # Verify with public key hex string
        is_valid_hex = AgentIdentity.verify(identity.public_key_hex, message, signature)
        self.assertTrue(is_valid_hex)
        
        # Verify string message
        str_msg = "Hello Syntropia Swarm"
        sig_str = identity.sign(str_msg)
        self.assertTrue(AgentIdentity.verify(identity.public_key, str_msg, sig_str))

    def test_tampered_signature_verification_fails(self):
        identity = AgentIdentity.create_master()
        message = b"Original message contents"
        signature = identity.sign(message)
        
        # Tamper with message
        self.assertFalse(AgentIdentity.verify(identity.public_key, b"Tampered message contents", signature))
        
        # Tamper with signature
        tampered_sig = bytearray(signature)
        tampered_sig[0] ^= 0xFF
        self.assertFalse(AgentIdentity.verify(identity.public_key, message, bytes(tampered_sig)))
        
        # Tamper with public key (verify with different key)
        other_identity = AgentIdentity.create_master()
        self.assertFalse(AgentIdentity.verify(other_identity.public_key, message, signature))


if __name__ == "__main__":
    unittest.main()
