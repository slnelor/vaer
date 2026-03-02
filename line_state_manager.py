from .types import BufferStateSnapshot, LineStatus, Range


class LineStateManager:
    """Source of truth for line statuses in current buffer."""

    def __init__(self):
        self.status_by_line: dict[int, LineStatus] = {}
        self.dirty_lines_since_last_enter: set[int] = set()

    def initialize(self, total_lines: int):
        self.status_by_line = {
            i: LineStatus.COMPLETE for i in range(1, total_lines + 1)
        }
        self.dirty_lines_since_last_enter.clear()

    def mark_line_progress(self, line_num: int):
        self.status_by_line[line_num] = LineStatus.PROGRESS
        self.dirty_lines_since_last_enter.add(line_num)

    def mark_range_working(self, r: Range):
        for i in range(r.start_line, r.end_line + 1):
            if self.status_by_line.get(i) == LineStatus.PROGRESS:
                self.status_by_line[i] = LineStatus.WORKING

    def mark_range_progress(self, r: Range):
        for i in range(r.start_line, r.end_line + 1):
            self.status_by_line[i] = LineStatus.PROGRESS

    def mark_range_complete(self, r: Range):
        for i in range(r.start_line, r.end_line + 1):
            self.status_by_line[i] = LineStatus.COMPLETE

    def mark_all_complete(self):
        for line_num in list(self.status_by_line.keys()):
            self.status_by_line[line_num] = LineStatus.COMPLETE
        self.dirty_lines_since_last_enter.clear()

    def on_user_line_edited(self, line_num: int, mode_is_vaer: bool):
        # HAND edits do not accumulate progress.
        if mode_is_vaer:
            self.mark_line_progress(line_num)

    def mark_lines_progress(self, lines: set[int]):
        for line_num in lines:
            self.mark_line_progress(line_num)

    def collect_progress_ranges(self) -> list[Range]:
        lines = sorted(
            line_num
            for line_num, status in self.status_by_line.items()
            if status == LineStatus.PROGRESS
        )
        if not lines:
            return []

        ranges: list[Range] = []
        start = prev = lines[0]
        for line_num in lines[1:]:
            if line_num == prev + 1:
                prev = line_num
                continue
            ranges.append(Range(start_line=start, end_line=prev))
            start = prev = line_num
        ranges.append(Range(start_line=start, end_line=prev))
        return ranges

    def is_complete_line(self, line_num: int) -> bool:
        return self.status_by_line.get(line_num) == LineStatus.COMPLETE

    def apply_snapshot(self, snapshot: BufferStateSnapshot, total_lines: int):
        self.initialize(total_lines)
        for line_num, status in snapshot.status_by_line.items():
            if 1 <= line_num <= total_lines:
                self.status_by_line[line_num] = status

    def as_snapshot(self, target_file: str, mode) -> BufferStateSnapshot:
        return BufferStateSnapshot(
            target_file=target_file,
            mode=mode,
            status_by_line=dict(self.status_by_line),
        )
