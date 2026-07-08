# Architecture Spec: P2P Peer Discovery via DHT

To operate without a single point of failure, Syntropia does not use centralized registry servers. Instead, peer discovery, agent listing, and routing tables are maintained over a Distributed Hash Table (DHT).

---

## 🌐 Kademlia Overlay & Mainline DHT

Syntropia uses the **BitTorrent Mainline DHT** protocol (Kademlia-based) to coordinate routing.

```
       [ Node A ]                               [ Node B ]
(Wants 'reasoning' agent)                (Hosts 'reasoning' agent)
           │                                        │
           ├───────── 1. Query DHT infohash ───────►│
           │          for 'syntropia:reasoning'     │
           │                                        │
           ◄───────── 2. Return Node B IP:Port ─────┤
           │                                        │
           ├───────── 3. Direct peer connection ───►│
           │             (gRPC/QUIC Task request)   │
```

### 1. Peer Registration
When a node starts up and loads its local agents:
1. It computes the SHA-256 hash of each agent role name (e.g. `hash("syntropia:role:addition")`). This acts as the **infohash** for that specific computational category.
2. The node announces itself to the DHT swarm under those infohashes.
3. Other nodes querying the DHT for that infohash receive the IP address and port of the provider.

### 2. Event-Driven Logical Clock Sync
Instead of forcing global wall-clock synchronization (which fails due to packet transit delay), Syntropia uses **Lamport Timestamps**:
* Each message payload includes an integer timestamp.
* When a node receives a message, it updates its local clock:
  $$\text{Clock}_{\text{local}} = \max(\text{Clock}_{\text{local}}, \text{Clock}_{\text{incoming}}) + 1$$
* This ensures a strict causal ordering of operations: Task request -> Sub-task generation -> Agent execution -> Results aggregation.
* Heartbeats are evaluated in terms of logical clock increments, allowing flexible, asynchronous operation.
