# Contributing to Syntropia 🌀

Thank you for your interest in contributing to Syntropia: The Living Computer! We are building a new paradigm of computing beyond quantum limits, powered by decentralized edge AI and swarm evolution.

We welcome all kinds of contributions: from core engine optimizations, specialized AI agent designs, P2P network code, to philosophy and docs.

---

## 🛠️ Developer Environment Setup

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/your-username/Project-Syntropia.git
   cd Project-Syntropia
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: `venv\Scripts\activate`
   pip install -r requirements.txt
   ```
3. Set up pre-commit or install dev dependencies:
   ```bash
   pip install -e .[dev]
   ```

---

## 🐜 How to Submit a New Agent

To submit a new computational agent to the swarm:

1. Create a subfolder inside `agents/` matching its category (e.g. `agents/math/add/` or `agents/reasoning/my_agent/`).
2. Add a `manifest.json` describing the agent:
   ```json
   {
     "name": "AdditionAgent",
     "role": "addition",
     "timeout": 2,
     "model": null,
     "description": "Performs fast arithmetic addition on numerical inputs."
   }
   ```
   If your agent requires a local AI model, add the `model` object containing the BitTorrent magnet link:
   ```json
   {
     "name": "QwenAgent",
     "role": "reasoning",
     "timeout": 8,
     "model": {
       "filename": "qwen2.5-0.5b-instruct.gguf",
       "magnet": "magnet:?xt=urn:btih:..."
     },
     "description": "Syntropic reasoning agent powered by local Qwen 0.5B."
   }
   ```
3. Implement the logic in `agent.py`. The class name must match the one defined in your manifest, and implement the `execute` method:
   ```python
   class AdditionAgent:
       def __init__(self):
           self.role = "addition"
           self.timeout = 2
       
       def execute(self, inputs):
           return sum(inputs)
   ```
4. Verify local functionality and submit a Pull Request!

---

## 🚀 Submitting Pull Requests

1. Create a branch named after your feature: `feature/your-feature-name`.
2. Write unit tests for new functionality under the `tests/` folder.
3. Verify that all tests pass before committing.
4. Keep commits clean, self-contained, and well-described.
