---
name: New Agent Proposal 🐜
about: Propose a new specialized agent role or model configuration
title: "[AGENT] "
labels: new-agent
assignees: ''

---

**Agent Name & Role**
State the name of your proposed agent and its role (e.g. `TranslationAgent`, role: `translation`).

**Computational Logic**
* Is this a **pure logic/rule-based** agent, or does it run an **Edge LLM**?
* If it runs an LLM, what model parameter size are you proposing (e.g. Qwen 0.5B, TinyLlama 1.1B)?

**Magnet Link / Torrent Data (if applicable)**
Provide the magnet link or hash of the model weights file so others can seed and verify it:
```text
magnet:?xt=urn:btih:...
```

**Simple Input/Output Specification**
What data payload does the agent accept, and what does it output?
* Input payload: `{"text": "...", "target_lang": "..."}`
* Output payload: `{"translated_text": "..."}`

**Expected Timeout / Ticks**
How many system ticks should be allowed before fallback triggers?
* Primary timeout: [e.g. 5 ticks]
* Latency estimation: [e.g. 3 ticks]
