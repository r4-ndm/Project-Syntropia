import os
import hmac
import hashlib
import struct
from typing import Tuple, Union
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


class AgentIdentity:
    """
    Verifiable Agent DNA & Cryptographic Identity.
    Provides BIP32/SLIP10-like Hierarchical Deterministic (HD) key derivation,
    Ed25519 signing, and signature verification.
    """
    
    def __init__(self, seed: bytes, chain_code: bytes):
        self.seed = seed
        self.chain_code = chain_code
        self.private_key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        self.public_key = self.private_key.public_key()
        
    @property
    def public_key_bytes(self) -> bytes:
        """Returns the raw 32-byte public key."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
    @property
    def public_key_hex(self) -> str:
        """Returns the hex-encoded public key string."""
        return self.public_key_bytes.hex()

    @classmethod
    def create_master(cls, seed_material: bytes = None) -> 'AgentIdentity':
        """Generates a master identity from random bytes or specified seed material."""
        if seed_material is None:
            # Generate 32 secure random bytes
            seed_material = os.urandom(32)
            
        # HMAC-SHA512 to generate master seed and chain code
        h = hmac.new(b"Syntropia Agent Master Seed", seed_material, hashlib.sha512)
        I = h.digest()
        master_seed = I[0:32]
        master_chain_code = I[32:64]
        return cls(master_seed, master_chain_code)

    def derive_child(self, index: int) -> 'AgentIdentity':
        """
        Derives a child identity using BIP32/SLIP10 hardened child key derivation.
        Forces hardened derivation (index >= 2^31) for Ed25519 security.
        """
        # Ensure index is in hardened range to prevent public-key-to-private-key leaks
        if index < 0x80000000:
            index += 0x80000000
            
        # data = 0x00 + parent_seed + index (4 bytes BE)
        data = b"\x00" + self.seed + struct.pack(">I", index)
        h = hmac.new(self.chain_code, data, hashlib.sha512)
        I = h.digest()
        
        child_seed = I[0:32]
        child_chain_code = I[32:64]
        return AgentIdentity(child_seed, child_chain_code)

    def sign(self, message: Union[bytes, str]) -> bytes:
        """Signs a message using the agent's private key."""
        if isinstance(message, str):
            message = message.encode("utf-8")
        return self.private_key.sign(message)

    @staticmethod
    def verify(public_key_input: Union[bytes, str, ed25519.Ed25519PublicKey], 
               message: Union[bytes, str], 
               signature: bytes) -> bool:
        """Verifies an Ed25519 signature against a message and a public key."""
        if isinstance(message, str):
            message = message.encode("utf-8")
            
        # Parse public key if bytes or hex string
        if isinstance(public_key_input, str):
            try:
                public_key_input = bytes.fromhex(public_key_input)
            except Exception:
                return False
        if isinstance(public_key_input, bytes):
            try:
                public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_input)
            except Exception:
                return False
        else:
            public_key = public_key_input
            
        try:
            public_key.verify(signature, message)
            return True
        except InvalidSignature:
            return False
        except Exception:
            return False
