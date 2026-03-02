import uuid

from .apply_engine import ApplyEngine
from .config import MAX_PARALLEL_REQUESTS
from .line_state_manager import LineStateManager
from .mode_manager import ModeManager
from .persistence import PersistenceManager
from .plugin_hooks import PluginHooks
from .request_manager import RequestManager
from .scheduler import Scheduler
from .treesitter_manager import TreesitterManager
from .tui_manager import TUIManager
from .types import RequestContext


class Agent:
    def __init__(self):
        self.request_manager = RequestManager()
        self.mode_manager = ModeManager()
        self.line_state_manager = LineStateManager()
        self.apply_engine = ApplyEngine()
        self.tui_manager = TUIManager()
        self.persistence = PersistenceManager()
        self.scheduler = Scheduler(max_parallel=MAX_PARALLEL_REQUESTS)
        self.treesitter = TreesitterManager()
        self.hooks = PluginHooks()
        self.current_file: str | None = None

    def toggle_mode(self):
        mode = self.mode_manager.toggle()
        self.tui_manager.render_mode(mode)
        self._persist_current_state()
        self.hooks.emit("mode_changed", mode)

    def complete_all(self):
        self.line_state_manager.mark_all_complete()
        self.tui_manager.render_line_status(self.line_state_manager.status_by_line)
        self._persist_current_state()
        self.hooks.emit("line_state_changed", self.line_state_manager.status_by_line)

    def stop_all_requests(self):
        self.request_manager.cancel_all()
        self.scheduler.cancel_all()

    def on_buffer_open(
        self,
        target_file: str,
        total_lines: int,
        file_text: str,
        filetype: str | None = None,
    ):
        self.current_file = target_file
        snapshot = self.persistence.load_snapshot(target_file)
        if snapshot:
            self.line_state_manager.apply_snapshot(snapshot, total_lines=total_lines)
            self.mode_manager.set_mode(snapshot.mode)
        else:
            self.line_state_manager.initialize(total_lines)

        self.refresh_import_progress(file_text=file_text, filetype=filetype)
        self.tui_manager.render_mode(self.mode_manager.mode)
        self.tui_manager.render_line_status(self.line_state_manager.status_by_line)

    def refresh_import_progress(self, file_text: str, filetype: str | None = None):
        if not self.mode_manager.is_vaer():
            return
        import_lines = self.treesitter.detect_import_lines(
            file_text=file_text,
            filetype=filetype,
        )
        self.line_state_manager.mark_lines_progress(import_lines)

    def on_user_line_edited(self, line_num: int):
        self.line_state_manager.on_user_line_edited(
            line_num=line_num,
            mode_is_vaer=self.mode_manager.is_vaer(),
        )
        self.tui_manager.render_line_status(self.line_state_manager.status_by_line)
        self._persist_current_state()
        self.hooks.emit("line_state_changed", self.line_state_manager.status_by_line)

    def on_enter_pressed(
        self,
        bufnr: int,
        target_file: str,
        changedtick: int,
        cursor_line: int,
        file_text: str,
        project_context: str,
    ):
        if self.mode_manager.is_hand():
            return

        progress_ranges = self.line_state_manager.collect_progress_ranges()
        if not progress_ranges:
            return

        request_id = str(uuid.uuid4())
        ctx = RequestContext(
            request_id=request_id,
            bufnr=bufnr,
            target_file=target_file,
            changedtick_at_start=changedtick,
            cursor_line=cursor_line,
            progress_ranges=progress_ranges,
            user_enter_line=cursor_line,
        )

        for r in progress_ranges:
            self.line_state_manager.mark_range_working(r)
        self.tui_manager.start_working_animation(progress_ranges)

        async def job():
            result = await self.request_manager.request_async(
                ctx=ctx,
                file_text=file_text,
                project_context=project_context,
            )

            now_changedtick = self._get_current_changedtick(bufnr)
            applied_result = self.apply_engine.apply(
                ctx=ctx,
                result=result,
                line_state=self.line_state_manager,
                current_changedtick=now_changedtick,
            )

            self.tui_manager.stop_working_animation(progress_ranges)
            self.tui_manager.render_line_status(self.line_state_manager.status_by_line)
            self._persist_state(target_file)
            self._report_result(applied_result)

        self.scheduler.submit(request_id, job)

    def _get_current_changedtick(self, bufnr: int) -> int:
        # Placeholder for editor API read.
        _ = bufnr
        return 0

    def _report_result(self, result):
        # Placeholder for notify/logging.
        _ = result

    def _persist_state(self, target_file: str):
        snapshot = self.line_state_manager.as_snapshot(
            target_file=target_file,
            mode=self.mode_manager.mode,
        )
        self.persistence.save_snapshot(snapshot)

    def _persist_current_state(self):
        if self.current_file:
            self._persist_state(self.current_file)
