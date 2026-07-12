# Contributing to Syntropia 🌀

Thank you for your interest in contributing to Syntropia: The Living OS! We are building a performance-focused operating system overlay—a swarm of AI containers that possess and enhance an existing CachyOS installation to run Windows games, DAWs, and VST3 plugins flawlessly while sharing idle compute resources.

We welcome all kinds of contributions:
* **Audio & DAW compatibility**: Optimizing Pipewire, PipeASIO, and yabridge sync for sub-millisecond latency.
* **Gaming tweaks**: Tuning BORE scheduler latencies and Proton runtime variables.
* **Security & Sandboxing**: Hardening the L4 system init sandboxes using Landlock LSM, seccomp filters, and cgroups.
* **P2P Transport**: Developing libp2p, WebRTC, or DePIN mesh networking features for swarm synchronization.

---

## 🛠️ Developer Environment Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/your-username/Project-Syntropia.git
   cd Project-Syntropia
   ```

2. **Set up a virtual environment and install dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: `venv\Scripts\activate`
   pip install -r requirements.txt
   ```

3. **Verify the active setup**:
   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests
   ```

---

## 🐜 How to Submit a New Agent

To submit a new compatibility or system optimization agent to the overlay swarm:

1. Create a subfolder inside `agents/` matching your agent's category (e.g. `agents/binary_analyzer/` or `agents/audio_tuner/`).
2. Add a `manifest.json` describing the agent:
   ```json
   {
     "name": "BinaryAnalyzerAgent",
     "role": "binary_analyzer",
     "timeout": 4,
     "description": "Profiles binary formats (ELF/PE) on host to identify Wine/Proton dependency mappings."
   }
   ```
3. Implement the logic in `agent.py`. The class name must match the one defined in your manifest, and it must implement the `execute` method:
   ```python
   class BinaryAnalyzerAgent:
       def __init__(self):
           self.role = "binary_analyzer"
           self.timeout = 4
       
       def execute(self, file_path):
           # Perform binary format detection or optimization checks
           return {"status": "success", "file": file_path}
   ```
4. Verify local functionality and submit a Pull Request.

---

## 🚀 Submitting Pull Requests

1. **Branch naming**: Create a branch named after your feature: `feature/your-feature-name` or `bugfix/your-fix-name`.
2. **Write unit tests**: Add test cases for your new functionality under the `tests/` folder (e.g., matching the style in `tests/test_cachy_host.py`).
3. **Verify tests pass**: Ensure all tests are green before committing:
   ```bash
   PYTHONPATH=src python3 -m unittest discover -s tests
   ```
4. **Keep commits clean**: Use concise commit titles and describe any configuration changes.
