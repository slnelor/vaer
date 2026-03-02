import asyncio

from .config import SPINNER_INTERVAL_MS
from .types import LineStatus, Mode, Range


class TUIManager:
    def __init__(self):
        self.status_bar = ...
        self.spinner_frames = ["[.,]", "[,.]"]
        self.spinner_idx = 0
        self._spinner_task = None
        self._working_ranges: list[Range] = []

    def render_mode(self, mode: Mode):
        # Top-right status bar: HAND or VAER
        _ = mode

    def render_line_status(self, status_by_line: dict[int, LineStatus]):
        # Apply extmarks/highlights in a real editor implementation.
        _ = status_by_line

    def start_working_animation(self, ranges: list[Range]):
        self._working_ranges = list(ranges)
        if self._spinner_task is None:
            self._spinner_task = asyncio.create_task(self._spin_loop())

    def tick_spinner(self):
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_frames)
        frame = self.spinner_frames[self.spinner_idx]
        # Update extmark virtual text for working ranges.
        _ = frame, self._working_ranges

    def stop_working_animation(self, ranges: list[Range]):
        _ = ranges
        self._working_ranges = []
        if self._spinner_task:
            self._spinner_task.cancel()
            self._spinner_task = None

    async def _spin_loop(self):
        try:
            while True:
                self.tick_spinner()
                await asyncio.sleep(SPINNER_INTERVAL_MS / 1000)
        except asyncio.CancelledError:
            return
