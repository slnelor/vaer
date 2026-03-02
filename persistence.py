import hashlib
import json
from pathlib import Path

from .config import TMP_DIR_NAME
from .types import BufferStateSnapshot, LineStatus, Mode


class PersistenceManager:
    """Persists per-file Vaer state into project-local tmp/."""

    def __init__(self, project_root: str | None = None):
        base = Path(project_root) if project_root else Path.cwd()
        self.tmp_dir = base / TMP_DIR_NAME / "vaer"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, target_file: str) -> Path:
        digest = hashlib.sha1(target_file.encode("utf-8")).hexdigest()[:16]
        return self.tmp_dir / f"state_{digest}.json"

    def save_snapshot(self, snapshot: BufferStateSnapshot):
        payload = {
            "target_file": snapshot.target_file,
            "mode": snapshot.mode.value,
            "status_by_line": {
                str(k): v.value for k, v in snapshot.status_by_line.items()
            },
        }
        self._state_path(snapshot.target_file).write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    def load_snapshot(self, target_file: str) -> BufferStateSnapshot | None:
        path = self._state_path(target_file)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        status_by_line = {
            int(k): LineStatus(v) for k, v in data.get("status_by_line", {}).items()
        }

        return BufferStateSnapshot(
            target_file=data.get("target_file", target_file),
            mode=Mode(data.get("mode", Mode.HAND.value)),
            status_by_line=status_by_line,
        )
