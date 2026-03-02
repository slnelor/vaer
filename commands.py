class Commands:
    """User-facing command handlers."""

    def __init__(self, agent):
        self.agent = agent

    def vaer_toggle_mode(self):
        self.agent.toggle_mode()

    def vaer_complete_all(self):
        self.agent.complete_all()

    def vaer_stop_all(self):
        self.agent.stop_all_requests()
