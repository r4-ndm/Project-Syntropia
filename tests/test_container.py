import unittest
from syntropia.container import ContainerNode

class TestContainerNode(unittest.TestCase):

    def test_create_node(self):
        node = ContainerNode(
            node_id="L1_MIDI_MANAGER_001",
            name="MIDI Manager",
            level="L1",
            role="midi_manager",
            intelligence_tier="light"
        )
        self.assertEqual(node.id, "L1_MIDI_MANAGER_001")
        self.assertEqual(node.level, "L1")
        self.assertEqual(node.role, "midi_manager")
        self.assertEqual(node.intelligence_tier, "light")
        self.assertEqual(len(node.children), 0)

    def test_invalid_level(self):
        with self.assertRaises(ValueError):
            ContainerNode("node_id", "Name", "L6", "role")

    def test_add_child_valid(self):
        parent = ContainerNode("L2_SUPERVISOR_001", "Supervisor", "L2", "track_supervisor")
        child = ContainerNode("L1_MANAGER_001", "Manager", "L1", "midi_manager")
        
        parent.add_child(child)
        self.assertEqual(len(parent.children), 1)
        self.assertEqual(child.parent_id, "L2_SUPERVISOR_001")
        
        # Test tree validation
        is_valid, msg = parent.validate_tree()
        self.assertTrue(is_valid)
        self.assertEqual(msg, "Valid")

    def test_add_child_invalid_hierarchy(self):
        parent = ContainerNode("L1_MANAGER_001", "Manager", "L1", "midi_manager")
        child = ContainerNode("L2_SUPERVISOR_001", "Supervisor", "L2", "track_supervisor")
        
        with self.assertRaises(ValueError) as ctx:
            parent.add_child(child)
        self.assertIn("Hierarchical violation", str(ctx.exception))

    def test_find_node(self):
        boss = ContainerNode("L5_BOSS", "Boss", "L5", "ceo")
        brain = ContainerNode("L4_BRAIN", "Brain", "L4", "core_ai")
        orchestrator = ContainerNode("L3_ORCH", "Orch", "L3", "orchestrator")
        
        boss.add_child(brain)
        brain.add_child(orchestrator)
        
        found = boss.find_node("L3_ORCH")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Orch")
        
        not_found = boss.find_node("NON_EXISTENT")
        self.assertIsNone(not_found)

    def test_serialization(self):
        boss = ContainerNode("L5_BOSS", "Boss", "L5", "ceo")
        brain = ContainerNode("L4_BRAIN", "Brain", "L4", "core_ai")
        boss.add_child(brain)
        
        serialized = boss.to_dict()
        self.assertEqual(serialized["id"], "L5_BOSS")
        self.assertEqual(len(serialized["children"]), 1)
        self.assertEqual(serialized["children"][0]["id"], "L4_BRAIN")
        
        deserialized = ContainerNode.from_dict(serialized)
        self.assertEqual(deserialized.id, "L5_BOSS")
        self.assertEqual(len(deserialized.children), 1)
        self.assertEqual(deserialized.children[0].id, "L4_BRAIN")
        
        is_valid, msg = deserialized.validate_tree()
        self.assertTrue(is_valid)

    def test_execute_logical_task(self):
        manager = ContainerNode("L1_MANAGER", "Manager", "L1", "midi_manager")
        worker1 = ContainerNode("L0_WORKER1", "Worker 1", "L0", "midi_generator", runtime={"script_path": "gen1.py"})
        worker2 = ContainerNode("L0_WORKER2", "Worker 2", "L0", "midi_generator", runtime={"script_path": "gen2.py"})
        
        manager.add_child(worker1)
        manager.add_child(worker2)
        
        task = {"action": "generate_kick_pattern"}
        log = manager.execute_logical_task(task)
        
        self.assertEqual(log["node_id"], "L1_MANAGER")
        self.assertEqual(log["status"], "success")
        self.assertEqual(len(log["children_logs"]), 2)
        self.assertEqual(log["children_logs"][0]["node_id"], "L0_WORKER1")
        self.assertEqual(log["children_logs"][0]["status"], "success")
        self.assertIn("gen1.py", log["children_logs"][0]["result"])

if __name__ == "__main__":
    unittest.main()
