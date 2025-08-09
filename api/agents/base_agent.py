"""Base agent class for common functionality."""


class BaseAgent:
    """Base class for agents that use message history."""
    
    def __init__(self, queries_history: list, result_history: list):
        """Initialize the agent with query and result history."""
        if result_history is None:
            self.messages = []
        else:
            self.messages = []
            for query, result in zip(queries_history[:-1], result_history):
                self.messages.append({"role": "user", "content": query})
                self.messages.append({"role": "assistant", "content": result})