import json
import sqlite3
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple


class SQLiteBulletinChain:
    """
    SQLite Bulletin Chain Mock Ledger.
    Mimics the content-addressable storage, block hash chains,
    agent registry, and reputation system of the Polkadot Bulletin Chain.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        """Creates the initial database schema with appropriate indexes."""
        cursor = self.conn.cursor()
        
        # 1. Blocks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_height INTEGER PRIMARY KEY AUTOINCREMENT,
                block_hash TEXT NOT NULL UNIQUE,
                parent_hash TEXT NOT NULL,
                timestamp INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blocks_hash ON blocks(block_hash)")
        
        # 2. Agent Registry Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_registry (
                public_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                reputation_score REAL NOT NULL DEFAULT 100.0,
                status TEXT NOT NULL DEFAULT 'Active'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_role ON agent_registry(role)")
        
        # 3. Mutation Ledger Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutation_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                proposal_hash TEXT NOT NULL,
                code_diff TEXT NOT NULL,
                last_safe_hash TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                signature TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (agent_id) REFERENCES agent_registry(public_key)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mutation_agent ON mutation_ledger(agent_id)")
        
        # 4. Content-Addressable Storage (CAS) Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS content_addressable_storage (
                cid TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
        """)

        # 5. Reap Requests Table (Container termination queue for the external Reaper Daemon)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reap_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id TEXT NOT NULL,
                public_key TEXT NOT NULL,
                signature TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                timestamp INTEGER NOT NULL
            )
        """)
        
        # Write genesis block if table is empty
        cursor.execute("SELECT COUNT(*) FROM blocks")
        if cursor.fetchone()[0] == 0:
            genesis_hash = hashlib.sha256(b"Syntropia Genesis Block").hexdigest()
            cursor.execute(
                "INSERT INTO blocks (block_hash, parent_hash, timestamp) VALUES (?, ?, ?)",
                (genesis_hash, "0000000000000000000000000000000000000000000000000000000000000000", int(time.time()))
            )
            
        self.conn.commit()

    def register_agent(self, public_key: str, name: str, role: str, code_hash: str) -> None:
        """Registers a new agent identity on the blockchain."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO agent_registry (public_key, name, role, code_hash, reputation_score) VALUES (?, ?, ?, ?, ?)",
            (public_key, name, role, code_hash, 100.0)
        )
        self.conn.commit()

    def update_agent_status(self, public_key: str, status: str) -> None:
        """Updates the status of a registered agent on the blockchain."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE agent_registry SET status = ? WHERE public_key = ?",
            (status, public_key)
        )
        self.conn.commit()

    def get_agent(self, public_key: str) -> Optional[Dict[str, Any]]:
        """Retrieves registered agent metadata from public key."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name, role, code_hash, reputation_score, status FROM agent_registry WHERE public_key = ?",
            (public_key,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "public_key": public_key,
                "name": row[0],
                "role": row[1],
                "code_hash": row[2],
                "reputation_score": row[3],
                "status": row[4]
            }
        return None

    def update_reputation(self, public_key: str, score_delta: float) -> float:
        """Applies a reputation score adjustment on-chain."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT reputation_score FROM agent_registry WHERE public_key = ?", (public_key,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Agent with key {public_key} is not registered.")
        
        new_score = max(0.0, min(200.0, row[0] + score_delta))
        cursor.execute(
            "UPDATE agent_registry SET reputation_score = ? WHERE public_key = ?",
            (new_score, public_key)
        )
        self.conn.commit()
        return new_score

    def store_payload(self, payload: Dict[str, Any]) -> str:
        """
        Stores a JSON payload in Content-Addressable Storage (CAS).
        Generates and returns an IPFS-like Content Identifier (CID).
        """
        serialized = json.dumps(payload, sort_keys=True)
        # Compute SHA-256 hash as the CID
        cid = "cid_" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO content_addressable_storage (cid, payload) VALUES (?, ?)",
            (cid, serialized)
        )
        self.conn.commit()
        return cid

    def get_payload(self, cid: str) -> Optional[Dict[str, Any]]:
        """Retrieves a payload from Content-Addressable Storage (CAS) via its CID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT payload FROM content_addressable_storage WHERE cid = ?", (cid,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def log_mutation(self, public_key: str, proposal: Dict[str, Any], signature: str) -> str:
        """Logs a signed mutation proposal into the blockchain ledger."""
        # 1. Verify agent is registered
        agent = self.get_agent(public_key)
        if not agent:
            raise ValueError(f"Proposing agent {public_key} is not registered in the registry.")
            
        proposal_serialized = json.dumps(proposal, sort_keys=True)
        proposal_hash = hashlib.sha256(proposal_serialized.encode("utf-8")).hexdigest()
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO mutation_ledger 
            (agent_id, proposal_hash, code_diff, last_safe_hash, timestamp, signature, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            public_key,
            proposal_hash,
            proposal.get("code_diff", ""),
            proposal.get("last_safe_hash", ""),
            int(time.time()),
            signature,
            "Logged"
        ))
        
        # 2. Append a new block to verify the ledger state
        cursor.execute("SELECT block_hash FROM blocks ORDER BY block_height DESC LIMIT 1")
        last_block_hash = cursor.fetchone()[0]
        
        # Combine last block hash with mutation proposal hash for the new block hash
        new_block_data = last_block_hash + proposal_hash
        new_block_hash = hashlib.sha256(new_block_data.encode("utf-8")).hexdigest()
        
        cursor.execute(
            "INSERT INTO blocks (block_hash, parent_hash, timestamp) VALUES (?, ?, ?)",
            (new_block_hash, last_block_hash, int(time.time()))
        )
        
        self.conn.commit()
        return new_block_hash

    def get_mutation_history(self, public_key: str) -> List[Dict[str, Any]]:
        """Retrieves the mutation logs logged for a specific agent key."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT proposal_hash, code_diff, last_safe_hash, timestamp, signature, status 
            FROM mutation_ledger WHERE agent_id = ? ORDER BY id ASC
        """, (public_key,))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "proposal_hash": row[0],
                "code_diff": row[1],
                "last_safe_hash": row[2],
                "timestamp": row[3],
                "signature": row[4],
                "status": row[5]
            })
        return history

    def add_reap_request(self, container_id: str, public_key: str, signature: str) -> None:
        """Adds a request to kill/reap a container on vaporization."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO reap_requests (container_id, public_key, signature, timestamp, status)
            VALUES (?, ?, ?, ?, 'Pending')
        """, (container_id, public_key, signature, int(time.time())))
        self.conn.commit()

    def get_pending_reaps(self) -> List[Dict[str, Any]]:
        """Retrieves all pending reap requests for the ContainerReaper daemon."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, container_id, public_key, signature, timestamp, status 
            FROM reap_requests WHERE status = 'Pending' ORDER BY id ASC
        """)
        reaps = []
        for row in cursor.fetchall():
            reaps.append({
                "id": row[0],
                "container_id": row[1],
                "public_key": row[2],
                "signature": row[3],
                "timestamp": row[4],
                "status": row[5]
            })
        return reaps

    def mark_reaped(self, request_id: int) -> None:
        """Marks a reap request as completed/reaped."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE reap_requests SET status = 'Reaped' WHERE id = ?
        """, (request_id,))
        self.conn.commit()

    def close(self):
        """Closes the connection to SQLite."""
        self.conn.close()
