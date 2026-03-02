#!/usr/bin/env python3
"""Vaer adapter backed by OpenCode Python SDK.

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
  pip install --pre opencode-ai
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
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

    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    try:
        value = json.loads(text[first : last + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def call_opencode(payload: dict) -> dict:
    opencode_mod = importlib.import_module("opencode_ai")
    Opencode = getattr(opencode_mod, "Opencode")

    cfg = payload.get("opencode", {}) if isinstance(payload.get("opencode"), dict) else {}
    model = cfg.get("model") or os.getenv("VAER_MODEL", "openai/gpt-4.1-mini")
    provider_id, model_id = split_model(model)
    provider_id = cfg.get("provider") or provider_id
    model_id = cfg.get("model_id") or model_id
    mode = cfg.get("mode") or "code"
    session_scope = cfg.get("session_scope") or "project"

    cwd = payload.get("cwd") or os.getcwd()
    target_file = payload.get("target_file", "")

    client = Opencode(timeout=30.0, max_retries=2)
    session_id = load_cached_session_id(cwd, session_scope, target_file)

    if not session_id:
        session = client.session.create()
        session_id = getattr(session, "id", None)
        if not isinstance(session_id, str) or not session_id:
            return {"edits": [], "diagnostics": ["opencode session.create returned no id"]}
        save_cached_session_id(cwd, session_scope, target_file, session_id)

    prompt = build_prompt(payload)

    params = {
        "id": session_id,
        "parts": [{"type": "text", "text": prompt}],
        "mode": mode,
    }
    if provider_id:
        params["provider_id"] = provider_id
    if model_id:
        params["model_id"] = model_id

    response = client.session.chat(**params)

    text_parts: list[str] = []
    for part in getattr(response, "parts", []) or []:
        if getattr(part, "type", None) == "text":
            text_parts.append(getattr(part, "text", ""))

    parsed = extract_json_object("\n".join(text_parts))
    if not isinstance(parsed, dict):
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
    except ModuleNotFoundError:
        result = {
            "edits": [],
            "diagnostics": [
                "opencode_ai not installed",
                "run: pip install --pre opencode-ai",
            ],
        }
    except Exception as e:
        result = {
            "edits": [],
            "diagnostics": [f"adapter_error: {e}"],
        }

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
