# Architecture Spec: Trust & Consensus Verification

In a decentralized system where nodes are run by arbitrary volunteers across the internet, we cannot assume that every peer is honest or that their local models are working correctly. This specification details the verification protocols designed for Syntropia.

---

## 🛡️ Multi-Tier Verification Model

Depending on the criticality of the computation, Syntropia employs three distinct verification methods:

```
                  [ Task Dispatched ]
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
    [ Standard Task ]           [ Critical Task ]
            │                           │
    (Single execution)          (3-Peer Replication)
            │                           │
    Verify signature of         Compare responses.
    agent state hash.           Majority (2/3) match.
            │                           │
            └─────────────┬─────────────┘
                          ▼
            [ Update Peer Reputation ]
```

### 1. Cryptographic Signatures (Standard Tasks)
* **Objective**: Ensure that a computation was executed by a specific verified agent and not tampered with in transit.
* **Mechanism**:
  - Each agent has an asymmetric key pair generated upon creation.
  - The response payload is hashed along with the agent's current state hash.
  - The executing node signs the combined hash using the agent's private key.
  - The requesting node verifies the signature using the public key indexed in the DHT registry.

### 2. 3-Way Redundant Consensus (Critical Tasks)
* **Objective**: Guard against malicious output or random LLM hallucinations.
* **Mechanism**:
  - The Orchestrator flags specific tasks as `critical` (e.g., core system arithmetic or key database transactions).
  - The Orchestrator routes the identical payload to three random, unrelated nodes hosting the required agent.
  - Upon receiving the three responses:
    - If all three match, the result is accepted.
    - If there is a 2/3 majority match, the majority result is accepted, and the outlier node is flagged.
    - If there is no majority match, the task is re-routed to a secondary pool of highly trusted peers.

### 3. Node Reputation Tracking
* **Objective**: Create a self-healing trust layer.
* **Mechanism**:
  - Every node maintains a local trust score ledger for other peers.
  - Scoring updates:
    - **+1** for verified successful executions.
    - **-5** for submitting conflicting results in consensus tasks or timing out.
  - If a peer's reputation falls below a threshold, it is excluded from executing critical tasks and eventually banned from peer routing.
