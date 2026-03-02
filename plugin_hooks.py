from collections import defaultdict
from collections.abc import Callable


class PluginHooks:
    """Simple extension point registry for integrations (statusline, telescope, etc.)."""

    def __init__(self):
        self._hooks: dict[str, list[Callable[..., None]]] = defaultdict(list)

    def on(self, event_name: str, callback: Callable[..., None]):
        self._hooks[event_name].append(callback)

    def emit(self, event_name: str, *args, **kwargs):
        for cb in self._hooks.get(event_name, []):
            cb(*args, **kwargs)
