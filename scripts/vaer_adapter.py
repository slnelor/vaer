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
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
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


def resolve_config_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if text.startswith("{file:") and text.endswith("}"):
        path_text = text[6:-1].strip()
        if not path_text:
            return None
        path = Path(path_text).expanduser()
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None

    return text


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
        "- Edits MUST use absolute line numbers from the numbered text block.\n"
        "- Keep edits strictly inside progress_ranges.\n"
        "- Never modify import lines unless an import line is explicitly in progress_ranges.\n"
        "- Prefer rewriting invalid/pseudo code into valid code on the same line(s).\n"
        "- Preserve user intent; do not perform unrelated refactors.\n"
        "- If uncertain, return edits=[] and explain in diagnostics.\n"
        "- Do NOT delete code. replacement_lines must include at least one non-empty line.\n"
        "- Keep output concise and valid JSON.\n"
        f"target_file: {target_file}\n"
        f"progress_ranges: {json.dumps(progress_ranges)}\n"
        "file_text (format: `<absolute_line>| <code>`):\n"
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


def run_timeout_seconds(payload: dict) -> int:
    timeout_ms = payload.get("request_timeout_ms")
    if isinstance(timeout_ms, (int, float)):
        return max(20, min(180, int(timeout_ms / 1000) - 2))
    return 85


def parse_structured_payload(parsed: dict, fallback_diagnostics: list[str] | None = None) -> dict:
    edits = parsed.get("edits", [])
    diagnostics = parsed.get("diagnostics", [])
    if not isinstance(edits, list):
        edits = []
    if not isinstance(diagnostics, list):
        diagnostics = []

    if not edits and fallback_diagnostics:
        diagnostics.extend(fallback_diagnostics)

    return {
        "edits": edits,
        "diagnostics": diagnostics,
    }


def response_schema() -> dict:
    return {
        "name": "VaerEdits",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target_file": {"type": "string"},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                            "replacement_lines": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "target_file",
                            "start_line",
                            "end_line",
                            "replacement_lines",
                        ],
                        "additionalProperties": False,
                    },
                },
                "diagnostics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["edits", "diagnostics"],
            "additionalProperties": False,
        },
    }


def resolve_provider(payload: dict) -> str:
    cfg = payload.get("provider")
    if isinstance(cfg, dict):
        name = cfg.get("name")
        if isinstance(name, str) and name:
            return name.lower()

    env_name = os.getenv("VAER_PROVIDER")
    if isinstance(env_name, str) and env_name:
        return env_name.lower()

    return "opencode"


def call_inception(payload: dict) -> dict:
    cfg = payload.get("inception", {}) if isinstance(payload.get("inception"), dict) else {}
    api_key = resolve_config_value(cfg.get("api_key")) or os.getenv("INCEPTION_API_KEY")
    if not api_key:
        return {"edits": [], "diagnostics": ["missing INCEPTION_API_KEY"]}

    model = cfg.get("model") if isinstance(cfg.get("model"), str) and cfg.get("model") else "mercury-2"
    stream = bool(cfg.get("stream", True))
    diffusing = bool(cfg.get("diffusing", False))
    reasoning_effort = cfg.get("reasoning_effort") if isinstance(cfg.get("reasoning_effort"), str) else "instant"
    max_tokens = cfg.get("max_tokens") if isinstance(cfg.get("max_tokens"), int) else 4096
    temperature = cfg.get("temperature") if isinstance(cfg.get("temperature"), (int, float)) else 0.0

    prompt = build_prompt(payload)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": response_schema(),
        },
        "reasoning_effort": reasoning_effort,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if stream and diffusing:
        body["diffusing"] = True

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.inceptionlabs.ai/v1/chat/completions",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    timeout_sec = run_timeout_seconds(payload)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if not stream:
                raw = resp.read().decode("utf-8", errors="replace")
                decoded = json.loads(raw)
                content = decoded.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not isinstance(content, str):
                    return {"edits": [], "diagnostics": ["inception invalid content"]}
                parsed = extract_json_object(content)
                if not isinstance(parsed, dict):
                    return {"edits": [], "diagnostics": ["inception did not return JSON edits"]}
                return parse_structured_payload(parsed)

            contents: list[str] = []
            stream_errors: list[str] = []
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    event = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                err = event.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("type") or "inception stream error"
                    if isinstance(msg, str):
                        stream_errors.append(msg)

                for choice in event.get("choices", []) if isinstance(event.get("choices"), list) else []:
                    delta = choice.get("delta")
                    if isinstance(delta, dict):
                        text = delta.get("content")
                        if isinstance(text, str) and text:
                            contents.append(text)

            parsed = extract_json_object("".join(contents))
            if not isinstance(parsed, dict):
                if stream_errors:
                    return {"edits": [], "diagnostics": stream_errors}
                return {"edits": [], "diagnostics": ["inception stream returned no JSON edits"]}
            return parse_structured_payload(parsed, stream_errors)

    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:600]
        except Exception:
            detail = ""
        return {
            "edits": [],
            "diagnostics": [f"inception_http={e.code}", detail],
        }
    except urllib.error.URLError as e:
        return {
            "edits": [],
            "diagnostics": [f"inception_network={e.reason}"],
        }
    except subprocess.TimeoutExpired:
        return {"edits": [], "diagnostics": [f"inception timeout ({timeout_sec}s)"]}


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
    run_timeout_sec = run_timeout_seconds(payload)

    session_id = load_cached_session_id(cwd, session_scope, target_file)
    prompt = build_prompt(payload)

    opencode_bin = shutil.which("opencode")
    if not opencode_bin:
        home_bin = Path.home() / ".opencode" / "bin" / "opencode"
        if home_bin.exists():
            opencode_bin = str(home_bin)
    if not opencode_bin:
        return {"edits": [], "diagnostics": ["opencode CLI not found in PATH"]}

    def run_once(use_session: bool, use_model: bool):
        cmd = [opencode_bin, "run", "--format", "json", "--dir", cwd]
        if use_model and model:
            cmd.extend(["--model", model])
        if use_session and isinstance(session_id, str) and session_id:
            cmd.extend(["--session", session_id])
        cmd.append(prompt)

        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=run_timeout_sec,
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
        return {"edits": [], "diagnostics": [f"opencode run timeout ({run_timeout_sec}s)"]}

    if event_errors and any("Model not found:" in e for e in event_errors):
        clear_cached_session_id(cwd, session_scope, target_file)
        try:
            proc, text_parts, event_errors, new_session_id = run_once(False, False)
        except subprocess.TimeoutExpired:
            return {"edits": [], "diagnostics": [f"opencode run timeout ({run_timeout_sec}s)"]}

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

    return parse_structured_payload(parsed)


def main() -> int:
    payload = read_payload()
    try:
        provider = resolve_provider(payload)
        if provider == "inception":
            result = call_inception(payload)
        else:
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
