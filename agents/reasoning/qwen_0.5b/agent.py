class QwenAgent:
    """
    Local reasoning agent. Runs CPU-based inferences.
    """
    def __init__(self):
        self.role = "reasoning"
        self.timeout = 8  # ticks

    def execute(self, payload: dict) -> dict:
        """
        Executes reasoning mock logic.
        """
        prompt = payload.get("prompt", "")
        return {"result": f"Qwen-0.5B inference output for prompt: '{prompt}'"}
