import time
import unittest
import threading
from syntropia.engine import SyntropiaEngine
from syntropia.orchestrator import Orchestrator


class MockAgent:
    def __init__(self, name, role, timeout=3, fail=False):
        self.name = name
        self.role = role
        self.timeout = timeout
        self.fail = fail

    def execute(self, inputs):
        if self.fail:
            raise RuntimeError(f"MockAgent {self.name} failure")
        return f"{self.name} processed: {inputs}"


class TestCoreEngine(unittest.TestCase):
    def test_routing_success_and_lamport_clock(self):
        orchestrator = Orchestrator()
        engine = SyntropiaEngine(orchestrator)
        orchestrator.set_engine(engine)

        primary = MockAgent("PrimaryAgent", "mock_role", timeout=4)
        orchestrator.register_agent(primary, "mock_role")

        # Start logical clock at 10
        engine.logical_tick = 10

        result = orchestrator.execute_task("mock_role", "data123")
        self.assertEqual(result, "PrimaryAgent processed: data123")
        
        # Verify Lamport clock updated (10 -> max(10, 10)+1 = 11)
        self.assertEqual(engine.logical_tick, 11)
        # Reputation should increase
        self.assertEqual(orchestrator.reputation["PrimaryAgent"], 101.0)

    def test_fallback_on_failure(self):
        orchestrator = Orchestrator()
        engine = SyntropiaEngine(orchestrator)
        orchestrator.set_engine(engine)

        primary = MockAgent("PrimaryAgent", "mock_role", fail=True)
        fallback = MockAgent("FallbackAgent", "mock_role")

        orchestrator.register_agent(primary, "mock_role", fallback_name="FallbackAgent")
        orchestrator.register_agent(fallback, "mock_role")

        result = orchestrator.execute_task("mock_role", "data456")
        self.assertEqual(result, "FallbackAgent processed: data456")

        # Primary reputation should drop, fallback should rise
        self.assertEqual(orchestrator.reputation["PrimaryAgent"], 85.0)
        self.assertEqual(orchestrator.reputation["FallbackAgent"], 101.0)

    def test_logical_timeout_routing(self):
        orchestrator = Orchestrator()
        engine = SyntropiaEngine(orchestrator)
        orchestrator.set_engine(engine)

        # Primary agent with a timeout of 2 ticks
        primary = MockAgent("PrimaryAgent", "mock_role", timeout=2)
        fallback = MockAgent("FallbackAgent", "mock_role")

        orchestrator.register_agent(primary, "mock_role", fallback_name="FallbackAgent")
        orchestrator.register_agent(fallback, "mock_role")

        # We will dispatch a task that simulates a 0.5s delay
        # The engine will tick in a separate thread every 0.05 seconds
        # This will trigger ticks fast enough to exceed the 2 tick limit
        inputs = {"mock_delay_seconds": 0.5}

        # Keep track of ticks
        ticks_started = engine.logical_tick

        # Spin clock generator in background
        engine.running = True
        
        def mock_clock():
            while engine.running:
                time.sleep(0.05)
                engine._tick()

        clock_thread = threading.Thread(target=mock_clock, daemon=True)
        clock_thread.start()

        try:
            result = orchestrator.execute_task("mock_role", inputs)
            self.assertEqual(result, "FallbackAgent processed: {'mock_delay_seconds': 0.5}")
            
            # Primary reputation should drop due to timeout
            self.assertEqual(orchestrator.reputation["PrimaryAgent"], 85.0)
            # Fallback reputation should increase
            self.assertEqual(orchestrator.reputation["FallbackAgent"], 101.0)
        finally:
            engine.stop()


if __name__ == "__main__":
    unittest.main()
