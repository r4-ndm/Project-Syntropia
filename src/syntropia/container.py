from typing import List, Dict, Any, Optional, Tuple
import json

LEVEL_VALUES = {
    "L0": 0,
    "L1": 1,
    "L2": 2,
    "L3": 3,
    "L4": 4,
    "L5": 5
}

class ContainerNode:
    """Represents a virtualized container or a group of containers (within boss containers)."""

    def __init__(
        self,
        node_id: str,
        name: str,
        level: str,
        role: str,
        intelligence_tier: str = "none",
        parent_id: Optional[str] = None,
        runtime: Optional[Dict[str, Any]] = None,
        resource_limits: Optional[Dict[str, Any]] = None,
        status: str = "idle",
        reputation: float = 100.0,
        children: Optional[List['ContainerNode']] = None
    ):
        if level not in LEVEL_VALUES:
            raise ValueError(f"Invalid container level: {level}. Must be one of {list(LEVEL_VALUES.keys())}")
            
        self.id = node_id
        self.name = name
        self.level = level
        self.role = role
        self.intelligence_tier = intelligence_tier
        self.parent_id = parent_id
        self.runtime = runtime or {}
        self.resource_limits = resource_limits or {}
        self.status = status
        self.reputation = reputation
        self.children = children or []

    def add_child(self, child: 'ContainerNode') -> None:
        """Adds a child node (nesting a group inside this container)."""
        parent_val = LEVEL_VALUES[self.level]
        child_val = LEVEL_VALUES[child.level]
        
        # Enforce that children must be strictly lower level than parents
        if child_val >= parent_val:
            raise ValueError(
                f"Hierarchical violation: Parent container '{self.id}' (level {self.level}) "
                f"cannot contain child container '{child.id}' (level {child.level}). "
                "Child level must be strictly lower."
            )
            
        child.parent_id = self.id
        self.children.append(child)

    def remove_child(self, child_id: str) -> Optional['ContainerNode']:
        """Removes a child node by ID."""
        for i, child in enumerate(self.children):
            if child.id == child_id:
                removed = self.children.pop(i)
                removed.parent_id = None
                return removed
        return None

    def find_node(self, node_id: str) -> Optional['ContainerNode']:
        """Recursively finds a container node in the tree."""
        if self.id == node_id:
            return self
        for child in self.children:
            found = child.find_node(node_id)
            if found:
                return found
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes this container node and all its nested children to a dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "role": self.role,
            "intelligence_tier": self.intelligence_tier,
            "parent_id": self.parent_id,
            "runtime": self.runtime,
            "resource_limits": self.resource_limits,
            "status": self.status,
            "reputation": self.reputation,
            "children": [child.to_dict() for child in self.children]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContainerNode':
        """Recursively deserializes a dictionary structure into a ContainerNode tree."""
        children_data = data.get("children", [])
        children = []
        
        node = cls(
            node_id=data["id"],
            name=data["name"],
            level=data["level"],
            role=data["role"],
            intelligence_tier=data.get("intelligence_tier", "none"),
            parent_id=data.get("parent_id"),
            runtime=data.get("runtime"),
            resource_limits=data.get("resource_limits"),
            status=data.get("status", "idle"),
            reputation=data.get("reputation", 100.0)
        )
        
        for child_dict in children_data:
            child_node = cls.from_dict(child_dict)
            node.add_child(child_node)
            
        return node

    def validate_tree(self) -> Tuple[bool, str]:
        """
        Recursively validates the entire subtree under this node.
        Ensures correct parent_id mapping and strict hierarchical ordering of levels.
        """
        parent_val = LEVEL_VALUES[self.level]
        for child in self.children:
            if child.parent_id != self.id:
                return False, f"Parent ID mismatch: Child '{child.id}' claims parent is '{child.parent_id}', but actual parent is '{self.id}'"
            
            child_val = LEVEL_VALUES[child.level]
            if child_val >= parent_val:
                return False, f"Hierarchical ordering violation: Child '{child.id}' ({child.level}) is not strictly below Parent '{self.id}' ({self.level})"
            
            # Recursive check
            is_valid, msg = child.validate_tree()
            if not is_valid:
                return False, msg
                
        return True, "Valid"

    def execute_logical_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates task execution routing.
        Passes down instructions through nested containers and returns execution logs.
        """
        self.status = "running"
        execution_log = {
            "node_id": self.id,
            "level": self.level,
            "role": self.role,
            "status": "processing",
            "children_logs": []
        }

        # L0 is a leaf node and executes actual work.
        if self.level == "L0":
            execution_log["status"] = "success"
            execution_log["result"] = f"Executed script {self.runtime.get('script_path')} successfully."
            self.status = "idle"
            return execution_log

        # Higher level nodes coordinate or split work among their children.
        for child in self.children:
            child_log = child.execute_logical_task(task)
            execution_log["children_logs"].append(child_log)

        execution_log["status"] = "success"
        self.status = "idle"
        return execution_log

    def __repr__(self) -> str:
        return f"<ContainerNode level={self.level} id={self.id} role={self.role} children={len(self.children)}>"
