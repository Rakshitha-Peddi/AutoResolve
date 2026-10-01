from ai_agent.engine import CodeFixEngine

class FixEngine:
    def __init__(self):
        self.impl = CodeFixEngine()

    def propose_fix(self, *args, **kwargs):
        return self.impl.propose_fix(*args, **kwargs)
