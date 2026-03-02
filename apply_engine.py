from .line_state_manager import LineStateManager
from .types import RequestContext, RequestResult


class ApplyEngine:
    """
    Safety-first apply flow:
    - same file only
    - no complete-line writes
    - stale changedtick checks
    """

    def apply(
        self,
        ctx: RequestContext,
        result: RequestResult,
        line_state: LineStateManager,
        current_changedtick: int,
    ) -> RequestResult:
        if result.status != "success":
            return result

        if current_changedtick != ctx.changedtick_at_start:
            result.status = "stale"
            result.diagnostics.append("Buffer changed since request start")
            return result

        for edit in result.edits:
            if edit.target_file != ctx.target_file:
                result.status = "failed"
                result.blocked_reason = "blocked_non_current_file_edit"
                result.diagnostics.append("Cross-file write blocked")
                return result

            for line_num in range(edit.range.start_line, edit.range.end_line + 1):
                if line_state.is_complete_line(line_num):
                    result.status = "failed"
                    result.blocked_reason = "attempt_edit_complete_line"
                    result.diagnostics.append(
                        f"Blocked edit on complete line {line_num}"
                    )
                    return result

        for edit in sorted(result.edits, key=lambda x: x.range.start_line, reverse=True):
            self._replace_lines(edit)
            line_state.mark_range_progress(edit.range)

        return result

    def _replace_lines(self, edit):
        # Placeholder for nvim_buf_set_lines-like behavior in Lua implementation.
        _ = edit
