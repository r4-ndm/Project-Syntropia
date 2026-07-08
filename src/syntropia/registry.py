import os
import json
import importlib.util
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class AgentModelSpec(BaseModel):
    filename: str
    magnet: str

class AgentManifest(BaseModel):
    name: str
    role: str
    timeout: int
    model: Optional[AgentModelSpec] = None
    description: str

class AgentRegistry:
    """Scans and dynamically loads agent manifests and logic from the agents/ directory."""
    
    def __init__(self, agents_dir: str):
        self.agents_dir = os.path.abspath(agents_dir)
        self.manifests: Dict[str, AgentManifest] = {}
        self.agent_classes: Dict[str, Any] = {}

    def scan_and_load(self):
        """Scans the agents/ folder recursively for manifest.json and loads them."""
        print(f"\033[36m[Registry] Scanning agent definitions in: {self.agents_dir}...\033[0m")
        
        if not os.path.exists(self.agents_dir):
            print(f"[Registry] Directory not found: {self.agents_dir}")
            return

        for root, dirs, files in os.walk(self.agents_dir):
            if "manifest.json" in files:
                manifest_path = os.path.join(root, "manifest.json")
                agent_py_path = os.path.join(root, "agent.py")
                
                try:
                    # Load and validate manifest
                    with open(manifest_path, 'r') as f:
                        data = json.load(f)
                    
                    manifest = AgentManifest(**data)
                    self.manifests[manifest.name] = manifest
                    
                    # Dynamically load the agent class if agent.py exists
                    if os.path.exists(agent_py_path):
                        cls = self._load_class_from_file(agent_py_path, manifest.name)
                        if cls:
                            self.agent_classes[manifest.name] = cls
                            print(f"  \033[32m✔ Loaded agent: {manifest.name} (Role: '{manifest.role}')\033[0m")
                    else:
                        print(f"  \033[33m⚠ Found manifest for {manifest.name} but agent.py is missing.\033[0m")
                        
                except Exception as e:
                    print(f"  \033[31m✘ Failed to load agent at {root}: {e}\033[0m")

    def _load_class_from_file(self, filepath: str, class_name: str) -> Optional[Any]:
        """Uses importlib to load a specific class dynamically from a file."""
        module_name = f"dynamic_agent_{class_name.lower()}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Retrieve the class
            if hasattr(module, class_name):
                return getattr(module, class_name)
            else:
                # If class name doesn't match perfectly, search for any class ending in 'Agent'
                for name, obj in module.__dict__.items():
                    if isinstance(obj, type) and name.endswith("Agent"):
                        return obj
                raise AttributeError(f"Could not find class '{class_name}' in {filepath}")
        except Exception as e:
            print(f"  [Registry Error] Failed to import module from {filepath}: {e}")
            return None

    def get_agent_instance(self, name: str) -> Optional[Any]:
        """Instantiates and returns a new agent instance if registered."""
        cls = self.agent_classes.get(name)
        if cls:
            return cls()
        return None
