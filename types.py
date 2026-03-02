from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional


class Mode(str, Enum):
    HAND = "HAND"
    VAER = "VAER"


class LineStatus(str, Enum):
    COMPLETE = "complete"
    PROGRESS = "progress"
    WORKING = "working"


@dataclass
class Line:
    line_num: int
    content: str
    status: LineStatus = LineStatus.COMPLETE


@dataclass
class Range:
    start_line: int
    end_line: int


@dataclass
class Edit:
    target_file: str
    range: Range
    replacement_lines: list[str]
    reason: str = ""


@dataclass
class RequestContext:
    request_id: str
    bufnr: int
    target_file: str
    changedtick_at_start: int
    cursor_line: int
    progress_ranges: list[Range]
    user_enter_line: int


@dataclass
class RequestResult:
    request_id: str
    edits: list[Edit] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    status: Literal["success", "cancelled", "failed", "stale"] = "success"


@dataclass
class BufferStateSnapshot:
    target_file: str
    mode: Mode
    status_by_line: dict[int, LineStatus]
