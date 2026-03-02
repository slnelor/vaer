#!/usr/bin/env python3
"""Default Vaer adapter.

Reads JSON payload from stdin and writes JSON result to stdout:
{
  "edits": [{"target_file", "start_line", "end_line", "replacement_lines"}],
  "diagnostics": ["..."]
}

Env vars:
- VAER_MODEL: provider/model (default: openai/gpt-4.1-mini)
- OPENAI_API_KEY / OPENROUTER_API_KEY
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
}


def load_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def parse_model() -> tuple[str, str]:
    model = os.getenv("VAER_MODEL", "openai/gpt-4.1-mini")
    if "/" not in model:
        return "openai", model
    provider, model_name = model.split("/", 1)
    return provider, model_name


def build_prompt(payload: dict) -> str:
    target_file = payload.get("target_file", "")
    file_text = payload.get("file_text", "")
    progress_ranges = payload.get("progress_ranges", [])

    return (
        "You are a strict coding edit engine.\n"
        "You may read/reason about project context but can only output edits for target_file.\n"
        "Return only JSON with this schema:\n"
        "{\"edits\":[{\"target_file\":string,\"start_line\":number,\"end_line\":number,\"replacement_lines\":string[]}],\"diagnostics\":string[]}\n"
        "Rules:\n"
        "- Keep edits within progress_ranges when possible.\n"
        "- Do not include markdown or prose.\n"
        f"target_file: {target_file}\n"
        f"progress_ranges: {json.dumps(progress_ranges)}\n"
        "file_text:\n"
        f"{file_text}\n"
    )


def extract_json(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            return None

    brace = re.search(r"(\{.*\})", text, re.S)
    if brace:
        try:
            return json.loads(brace.group(1))
        except json.JSONDecodeError:
            return None
    return None


def call_chat_completions(provider: str, model_name: str, prompt: str) -> dict:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return {"edits": [], "diagnostics": [f"unsupported provider: {provider}"]}

    api_key = os.getenv(cfg["api_key_env"], "")
    if not api_key:
        return {
            "edits": [],
            "diagnostics": [
                f"missing API key env: {cfg['api_key_env']}",
                "set VAER_MODEL and provider key to enable AI edits",
            ],
        }

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    body = {
        "model": model_name,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. No markdown.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    }

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return {"edits": [], "diagnostics": [f"http_error={e.code}", err_body[:400]]}
    except Exception as e:
        return {"edits": [], "diagnostics": [f"request_error={e}"]}

    try:
        decoded = json.loads(raw)
        content = decoded["choices"][0]["message"]["content"]
    except Exception:
        return {"edits": [], "diagnostics": ["invalid_provider_response", raw[:400]]}

    parsed = extract_json(content)
    if not isinstance(parsed, dict):
        return {"edits": [], "diagnostics": ["model_output_not_json", content[:400]]}

    edits = parsed.get("edits", [])
    diagnostics = parsed.get("diagnostics", [])
    if not isinstance(edits, list):
        edits = []
    if not isinstance(diagnostics, list):
        diagnostics = []
    return {"edits": edits, "diagnostics": diagnostics}


def main() -> int:
    payload = load_payload()
    provider, model_name = parse_model()
    prompt = build_prompt(payload)
    result = call_chat_completions(provider, model_name, prompt)
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
