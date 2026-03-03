#!/usr/bin/env python3
"""Vaer adapter backed by OpenCode CLI (`opencode run`).

Input: JSON payload via stdin.
Output: JSON payload via stdout with shape:
{
  "edits": [
    {
      "target_file": str,
      "start_line": int,
      "end_line": int,
      "replacement_lines": [str],
      "reason": str?
    }
  ],
  "diagnostics": [str]
}

Requires:
  opencode CLI installed and authenticated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def split_model(model: str) -> tuple[str | None, str | None]:
    if not model:
        return None, None
    if "/" not in model:
        return None, model
    provider, model_name = model.split("/", 1)
    return provider, model_name


def cache_dir(cwd: str) -> Path:
    return Path(cwd) / "tmp" / "vaer"


def session_key(cwd: str, scope: str, target_file: str) -> str:
    if scope == "buffer":
        src = target_file
    else:
        src = cwd
    digest = hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]
    return f"session_{digest}.json"


def load_cached_session_id(cwd: str, scope: str, target_file: str) -> str | None:
    path = cache_dir(cwd) / session_key(cwd, scope, target_file)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    sid = data.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def save_cached_session_id(cwd: str, scope: str, target_file: str, session_id: str):
    d = cache_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    path = d / session_key(cwd, scope, target_file)
    path.write_text(json.dumps({"session_id": session_id}), encoding="utf-8")


def clear_cached_session_id(cwd: str, scope: str, target_file: str):
    path = cache_dir(cwd) / session_key(cwd, scope, target_file)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def build_prompt(payload: dict) -> str:
    target_file = payload.get("target_file", "")
    progress_ranges = payload.get("progress_ranges", [])
    file_text = payload.get("file_text", "")

    return (
        "You are Vaer inline edit engine.\n"
        "Return ONLY JSON. No markdown and no prose.\n"
        "Schema:\n"
        "{\"edits\":[{\"target_file\":string,\"start_line\":number,\"end_line\":number,\"replacement_lines\":string[],\"reason\":string?}],\"diagnostics\":string[]}\n"
        "Rules:\n"
        "- You may reason about project context, but edits must target only target_file.\n"
        "- Prefer edits inside progress_ranges.\n"
        "- Keep output concise and valid JSON.\n"
        f"target_file: {target_file}\n"
        f"progress_ranges: {json.dumps(progress_ranges)}\n"
        "file_text:\n"
        f"{file_text}\n"
    )


def extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        try:
            value = json.loads(fenced.group(1))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[i:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


def call_opencode(payload: dict) -> dict:
    cfg = payload.get("opencode", {}) if isinstance(payload.get("opencode"), dict) else {}
    raw_model = cfg.get("model") or os.getenv("VAER_MODEL")
    model = raw_model if isinstance(raw_model, str) else ""
    provider_id, model_id = split_model(model)
    provider_override = cfg.get("provider")
    if isinstance(provider_override, str) and provider_override:
        provider_id = provider_override
    if provider_id and model_id:
        model = f"{provider_id}/{model_id}"
    session_scope = cfg.get("session_scope") or "project"

    cwd = payload.get("cwd") or os.getcwd()
    target_file = payload.get("target_file", "")

    session_id = load_cached_session_id(cwd, session_scope, target_file)
    prompt = build_prompt(payload)

    def run_once(use_session: bool, use_model: bool):
        cmd = ["opencode", "run", "--format", "json", "--dir", cwd]
        if use_model and model:
            cmd.extend(["--model", model])
        if use_session and isinstance(session_id, str) and session_id:
            cmd.extend(["--session", session_id])
        cmd.append(prompt)

        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )

        text_parts_local: list[str] = []
        event_errors_local: list[str] = []
        new_session_id_local: str | None = None

        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            sid = event.get("sessionID")
            if isinstance(sid, str) and sid:
                new_session_id_local = sid

            if event.get("type") == "error":
                err = event.get("error")
                if isinstance(err, dict):
                    data = err.get("data")
                    if isinstance(data, dict) and isinstance(data.get("message"), str):
                        event_errors_local.append(data["message"])
                    elif isinstance(err.get("name"), str):
                        event_errors_local.append(err["name"])

            if event.get("type") == "text":
                part = event.get("part", {})
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        text_parts_local.append(text)

        return proc, text_parts_local, event_errors_local, new_session_id_local

    try:
        proc, text_parts, event_errors, new_session_id = run_once(True, True)
    except FileNotFoundError:
        return {"edits": [], "diagnostics": ["opencode CLI not found in PATH"]}
    except subprocess.TimeoutExpired:
        return {"edits": [], "diagnostics": ["opencode run timeout"]}

    if event_errors and any("Model not found:" in e for e in event_errors):
        clear_cached_session_id(cwd, session_scope, target_file)
        try:
            proc, text_parts, event_errors, new_session_id = run_once(False, False)
        except subprocess.TimeoutExpired:
            return {"edits": [], "diagnostics": ["opencode run timeout"]}

    if proc.returncode != 0 and not event_errors:
        return {
            "edits": [],
            "diagnostics": [
                f"opencode_exit={proc.returncode}",
                (proc.stderr or "")[:400],
            ],
        }

    if isinstance(new_session_id, str) and new_session_id:
        save_cached_session_id(cwd, session_scope, target_file, new_session_id)

    parsed = extract_json_object("\n".join(text_parts))
    if not isinstance(parsed, dict):
        if event_errors:
            return {
                "edits": [],
                "diagnostics": event_errors,
            }
        return {
            "edits": [],
            "diagnostics": ["assistant did not return JSON edits"],
        }

    edits = parsed.get("edits", [])
    diagnostics = parsed.get("diagnostics", [])
    if not isinstance(edits, list):
        edits = []
    if not isinstance(diagnostics, list):
        diagnostics = []

    return {
        "edits": edits,
        "diagnostics": diagnostics,
    }


def main() -> int:
    payload = read_payload()
    try:
        result = call_opencode(payload)
    except Exception as e:
        result = {
            "edits": [],
            "diagnostics": [f"adapter_error: {e}"],
        }

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
