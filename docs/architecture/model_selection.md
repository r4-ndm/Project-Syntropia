# Architecture Spec: Hardware Probe & Dynamic Model Selection

To enable volunteer participation on any machine—from a Raspberry Pi to a high-end gaming desktop—Syntropia dynamically measures local system resources on startup and matches them with appropriate AI models.

---

## 🛠️ System Diagnostics & Tiers

On startup, the client node executes a hardware diagnostics routine checking:
1. **System RAM** (via memory stats)
2. **GPU VRAM** (checking CUDA, ROCm, or Metal availability)
3. **CPU cores & instructions** (checking vector extensions like AVX2, AVX-512, or ARM NEON support)

Based on these metrics, the client maps to one of four model tiers:

| Tier | Minimum RAM | VRAM Required | Recommended Model Size | GGUF Quantization | Example Model |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ultra-Light** | < 4 GB | None (CPU only) | 0.1B - 0.3B parameters | Q4_K_M / Q8_0 | `SmolLM-135M-Instruct` |
| **Light** | 4 - 8 GB | None (CPU only) | 0.5B - 1.1B parameters | Q4_K_M / Q6_K | `Qwen2.5-0.5B-Instruct` |
| **Medium** | 8 - 16 GB | Optional | 1.5B - 3B parameters | Q5_K_M / Q8_0 | `Qwen2.5-1.5B-Instruct` |
| **Heavy** | 16+ GB | 4+ GB VRAM | 7B - 8B parameters | Q4_K_M | `Llama-3-8B-Instruct` |

---

## 🔄 Fallback & Synchronization Chain

If an agent requires reasoning capabilities:
1. The **Hardware Selector** chooses the highest tier the local node can safely run without swapping RAM to disk.
2. The **Torrent Client** pulls the GGUF weights corresponding to that tier.
3. If execution fails (e.g. out-of-memory error during execution or download failure), the node falls back to the next lowest tier automatically to maintain agent availability.
