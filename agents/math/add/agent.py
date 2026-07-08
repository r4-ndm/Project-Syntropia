class AdditionAgent:
    """
    Proof-of-Concept Addition Agent.
    Strictly follows the single responsibility principle of Syntropia:
    Accepts list of numbers, outputs their sum.
    """
    def __init__(self):
        self.role = "addition"
        self.timeout = 2  # ticks

    def execute(self, inputs: list) -> float:
        """
        Executes summation.
        Expected input format: [num1, num2, num3, ...]
        """
        if not isinstance(inputs, list):
            raise TypeError("AdditionAgent inputs must be a list of numbers.")
        return sum(inputs)
