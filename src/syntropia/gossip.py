import random
from typing import Dict, Any, List, Optional, Tuple, Set

# =====================================================================
# 1. XOR-Based (K, 1) Erasure Coding Implementation
# =====================================================================

class XORErasureCoder:
    """
    Implements a simple (K, 1) XOR-based erasure coding scheme.
    Splits data into K equal-sized data chunks and creates 1 parity chunk.
    Any K chunks out of the K+1 total chunks are sufficient to reconstruct the data.
    """
    
    @staticmethod
    def encode(data: bytes, K: int) -> List[Tuple[int, bytes]]:
        """
        Splits data into K chunks and computes 1 XOR parity chunk.
        Returns a list of K+1 chunks as (chunk_index, chunk_data) tuples.
        """
        if K <= 0:
            raise ValueError("K must be a positive integer.")
            
        data_len = len(data)
        # Calculate chunk size (aligned to largest size, padding with null bytes)
        chunk_size = (data_len + K - 1) // K
        
        chunks = []
        for i in range(K):
            start = i * chunk_size
            end = min(start + chunk_size, data_len)
            chunk = bytearray(data[start:end])
            # Pad with null bytes if it's the last chunk and shorter
            if len(chunk) < chunk_size:
                chunk.extend(b'\x00' * (chunk_size - len(chunk)))
            chunks.append((i, bytes(chunk)))
            
        # Generate the parity chunk (index K)
        parity = bytearray(chunk_size)
        for _, chunk_bytes in chunks:
            for j in range(chunk_size):
                parity[j] ^= chunk_bytes[j]
                
        chunks.append((K, bytes(parity)))
        return chunks

    @staticmethod
    def decode(chunks: List[Tuple[int, bytes]], K: int, original_len: int) -> bytes:
        """
        Decodes K chunks back into the original data.
        Requires at least K unique chunks.
        """
        if len(chunks) < K:
            raise ValueError(f"Insufficient chunks for recovery. Needed {K}, got {len(chunks)}")
            
        # Deduplicate chunks by index
        unique_chunks = {idx: data for idx, data in chunks}
        if len(unique_chunks) < K:
            raise ValueError(f"Insufficient unique chunks for recovery. Needed {K}, got {len(unique_chunks)}")
            
        chunk_size = len(list(unique_chunks.values())[0])
        
        # Check if we are missing any data chunk
        missing_index = -1
        for i in range(K):
            if i not in unique_chunks:
                missing_index = i
                break
                
        # If we have all K data chunks, we don't need the parity chunk
        if missing_index == -1:
            reconstructed_bytes = bytearray()
            for i in range(K):
                reconstructed_bytes.extend(unique_chunks[i])
            return bytes(reconstructed_bytes[:original_len])
            
        # If one data chunk is missing, we must use the parity chunk (index K) to reconstruct it
        if K not in unique_chunks:
            raise ValueError(f"Missing data chunk index {missing_index} and no parity chunk available.")
            
        reconstructed_chunk = bytearray(unique_chunks[K]) # start with parity
        for idx, chunk_bytes in unique_chunks.items():
            if idx == K or idx == missing_index:
                continue
            for j in range(chunk_size):
                reconstructed_chunk[j] ^= chunk_bytes[j]
                
        # Insert the reconstructed chunk back into the dictionary
        unique_chunks[missing_index] = bytes(reconstructed_chunk)
        
        reconstructed_bytes = bytearray()
        for i in range(K):
            reconstructed_bytes.extend(unique_chunks[i])
            
        return bytes(reconstructed_bytes[:original_len])


# =====================================================================
# 2. Gossip Node & Network Simulation
# =====================================================================

class GossipNode:
    """Represents a stateless peer in the Syntropia swarm network."""
    
    def __init__(self, node_id: str):
        self.id = node_id
        self.peers: Set[str] = set()
        # Local storage representing local Cache (CID -> Payload)
        self.cache: Dict[str, Any] = {}
        # Local consensus ledger (CID -> State block data)
        self.ledger: Dict[str, Any] = {}

    def connect(self, peer_id: str) -> None:
        if peer_id != self.id:
            self.peers.add(peer_id)

    def disconnect(self, peer_id: str) -> None:
        self.peers.discard(peer_id)

    def receive_rumor(self, cid: str, payload: Any, sender_id: str, network: 'GossipNetwork') -> List[str]:
        """
        Receives a rumor update. If new, updates ledger and returns list of peer IDs 
        to forward the rumor to.
        """
        # If we already have this transaction/block in our ledger, ignore it (stop rumor loop)
        if cid in self.ledger:
            return []
            
        # Store in local ledger
        self.ledger[cid] = payload
        
        # Select a random subset of peers (e.g. up to 2) to propagate the rumor
        targets = []
        eligible_peers = [p for p in self.peers if p != sender_id]
        if eligible_peers:
            fanout = min(2, len(eligible_peers))
            targets = random.sample(eligible_peers, fanout)
            
        return targets

    def anti_entropy_check(self, target_node: 'GossipNode') -> Tuple[int, int]:
        """
        Compares local ledger state with a neighbor node.
        Pulls missing ledger blocks to synchronize state.
        Returns (pulled_count, pushed_count).
        """
        pulled = 0
        pushed = 0
        
        # Pull phase: find what target has that we miss
        for cid, payload in target_node.ledger.items():
            if cid not in self.ledger:
                self.ledger[cid] = payload
                pulled += 1
                
        # Push phase: find what we have that target misses
        for cid, payload in list(self.ledger.items()):
            if cid not in target_node.ledger:
                target_node.ledger[cid] = payload
                pushed += 1
                
        return pulled, pushed


class GossipNetwork:
    """Simulates a P2P network of GossipNodes executing state sync and erasure storage."""
    
    def __init__(self):
        self.nodes: Dict[str, GossipNode] = {}
        
    def add_node(self, node_id: str) -> GossipNode:
        node = GossipNode(node_id)
        self.nodes[node_id] = node
        return node
        
    def remove_node(self, node_id: str) -> None:
        # Disconnect node from all its peers
        if node_id in self.nodes:
            for other_node in self.nodes.values():
                other_node.disconnect(node_id)
            del self.nodes[node_id]

    def fully_connect(self) -> None:
        """Connects every node to every other node (mesh topology)."""
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                id1, id2 = node_ids[i], node_ids[j]
                self.nodes[id1].connect(id2)
                self.nodes[id2].connect(id1)

    def trigger_gossip_rumor(self, starting_node_id: str, cid: str, payload: Any) -> int:
        """
        Disseminates a rumor starting from a single node.
        Returns the number of steps/hops taken during broadcast.
        """
        queue = [(starting_node_id, cid, payload, "SYSTEM")]
        hops = 0
        
        while queue:
            current_id, item_cid, item_payload, sender_id = queue.pop(0)
            if current_id in self.nodes:
                node = self.nodes[current_id]
                next_nodes = node.receive_rumor(item_cid, item_payload, sender_id, self)
                for next_id in next_nodes:
                    queue.append((next_id, item_cid, item_payload, current_id))
                if next_nodes:
                    hops += 1
                    
        return hops

    def run_anti_entropy_round(self) -> int:
        """Runs a round of anti-entropy checks between randomly paired neighbors."""
        sync_events = 0
        node_ids = list(self.nodes.keys())
        if len(node_ids) < 2:
            return 0
            
        random.shuffle(node_ids)
        for i in range(0, len(node_ids) - 1, 2):
            node1 = self.nodes[node_ids[i]]
            node2 = self.nodes[node_ids[i+1]]
            
            # Connect them temporarily if they aren't connected
            node1.connect(node2.id)
            node2.connect(node1.id)
            
            pulled, pushed = node1.anti_entropy_check(node2)
            if pulled > 0 or pushed > 0:
                sync_events += 1
                
        return sync_events

    def scatter_erasure_chunks(self, cid: str, chunks: List[Tuple[int, bytes]]) -> List[str]:
        """
        Distributes erasure-coded chunks randomly across online nodes.
        Returns the list of node IDs where the chunks were stored.
        """
        nodes_list = list(self.nodes.values())
        if len(nodes_list) < len(chunks):
            raise ValueError(f"Not enough online nodes ({len(nodes_list)}) to host {len(chunks)} chunks.")
            
        assigned_nodes = random.sample(nodes_list, len(chunks))
        stored_locations = []
        for i, chunk in enumerate(chunks):
            node = assigned_nodes[i]
            node.cache[f"{cid}_chunk_{chunk[0]}"] = chunk[1]
            stored_locations.append(node.id)
            
        return stored_locations
