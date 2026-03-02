from .types import Mode


class ModeManager:
    def __init__(self):
        self._mode = Mode.HAND

    @property
    def mode(self) -> Mode:
        return self._mode

    def toggle(self) -> Mode:
        self._mode = Mode.VAER if self._mode == Mode.HAND else Mode.HAND
        return self._mode

    def set_mode(self, mode: Mode):
        self._mode = mode

    def is_vaer(self) -> bool:
        return self._mode == Mode.VAER

    def is_hand(self) -> bool:
        return self._mode == Mode.HAND
