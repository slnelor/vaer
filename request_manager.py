import asyncio
import importlib
import json
from pathlib import Path

from .config import (
    DEFAULT_AGENT_MODE,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MAX_PARALLEL_REQUESTS,
    REQUEST_TIMEOUT_SEC,
    SESSION_SCOPE,
)
from .types import Edit, Range, RequestContext, RequestResult


def parse_provider_model(model: str) -> tuple[str, str]:
    # Preferred format: provider/model-name
    if "/" not in model:
        return DEFAULT_PROVIDER, model
    provider, model_name = model.split("/", 1)
    return provider, model_name


class RequestManager:
    """
    Can read/research/run tools in full project context.
    Can only return writable edits for current file.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        provider: str = DEFAULT_PROVIDER,
        mode: str = DEFAULT_AGENT_MODE,
        session_scope: str = SESSION_SCOPE,
    ):
        self.model = model
        self.provider = provider
        self.mode = mode
        self.session_scope = session_scope
        self.in_flight: dict[str, object] = {}
        self.parallel_limit = MAX_PARALLEL_REQUESTS
        opencode_cls = self._load_opencode_class()
        self.client = opencode_cls(timeout=REQUEST_TIMEOUT_SEC) if opencode_cls else None
        self._session_cache: dict[str, str] = {}

    def _load_opencode_class(self):
        try:
            mod = importlib.import_module("opencode_ai")
            return getattr(mod, "Opencode", None)
        except Exception:
            return None

    def cancel(self, request_id: str):
        handle = self.in_flight.get(request_id)
        if not handle:
            return
        # handle.cancel() or handle.kill()
        ...

    def cancel_all(self):
        for request_id in list(self.in_flight.keys()):
            self.cancel(request_id)

    def request(self, ctx: RequestContext, file_text: str, project_context: str) -> RequestResult:
        # Sync shim for tests/proto callers.
        return asyncio.run(self.request_async(ctx, file_text, project_context))

    async def request_async(
        self,
        ctx: RequestContext,
        file_text: str,
        project_context: str,
    ) -> RequestResult:
        prompt = self._build_prompt(ctx, file_text, project_context)
        response = await self._run_model_call(ctx, prompt)
        edits = self._extract_edits(response)

        for edit in edits:
            if edit.target_file != ctx.target_file:
                return RequestResult(
                    request_id=ctx.request_id,
                    status="failed",
                    blocked_reason="blocked_non_current_file_edit",
                    diagnostics=["AI attempted cross-file write; blocked"],
                )

        return RequestResult(
            request_id=ctx.request_id,
            status="success",
            edits=edits,
        )

    async def _run_model_call(self, ctx: RequestContext, prompt: str):
        await asyncio.sleep(0)
        if self.client is None:
            return {
                "diagnostics": [
                    "opencode_ai dependency missing",
                    "install with: pip install --pre opencode-ai",
                ],
                "text": "",
            }

        provider_id, model_id = parse_provider_model(self.model)
        if self.provider:
            provider_id = self.provider

        session_id = self._get_or_create_session_id(ctx)
        if not session_id:
            return {"diagnostics": ["failed to create opencode session"], "text": ""}

        try:
            response = self.client.session.chat(
                id=session_id,
                provider_id=provider_id,
                model_id=model_id,
                mode=self.mode,
                parts=[{"type": "text", "text": prompt}],
            )
        except Exception as e:
            return {"diagnostics": [f"opencode chat failed: {e}"], "text": ""}

        text_parts: list[str] = []
        for part in getattr(response, "parts", []) or []:
            ptype = getattr(part, "type", None)
            if ptype == "text":
                text_parts.append(getattr(part, "text", ""))

        return {
            "diagnostics": [],
            "text": "\n".join(x for x in text_parts if x),
        }

    def _session_cache_key(self, ctx: RequestContext) -> str:
        if self.session_scope == "buffer":
            return f"buf:{ctx.bufnr}"
        project_root = str(Path(ctx.target_file).parent)
        return f"project:{project_root}"

    def _get_or_create_session_id(self, ctx: RequestContext) -> str | None:
        key = self._session_cache_key(ctx)
        existing = self._session_cache.get(key)
        if existing:
            return existing

        try:
            session = self.client.session.create()  # type: ignore[union-attr]
        except Exception:
            return None

        sid = getattr(session, "id", None)
        if isinstance(sid, str) and sid:
            self._session_cache[key] = sid
            return sid
        return None

    def _build_prompt(self, ctx: RequestContext, file_text: str, project_context: str) -> str:
        return f"""
You are Vaer inline editor.
Mode: VAER.
You may read/research whole project and run tools, but may modify only: {ctx.target_file}
Only edit user-progress regions.
Return structured edits (range + replacement), no prose.

Current file:\n{file_text}

Project context:\n{project_context}
"""

    def _extract_edits(self, response) -> list[Edit]:
        text = ""
        diagnostics = response.get("diagnostics", []) if isinstance(response, dict) else []
        if isinstance(response, dict):
            text = response.get("text", "")

        parsed = self._extract_json_object(text)
        if not parsed:
            return []

        raw_edits = parsed.get("edits", [])
        if not isinstance(raw_edits, list):
            return []

        edits: list[Edit] = []
        for item in raw_edits:
            if not isinstance(item, dict):
                continue
            target = item.get("target_file")
            start = item.get("start_line")
            end = item.get("end_line")
            replacement = item.get("replacement_lines")
            if (
                not isinstance(target, str)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or not isinstance(replacement, list)
            ):
                continue
            if not all(isinstance(line, str) for line in replacement):
                continue

            edits.append(
                Edit(
                    target_file=target,
                    range=Range(start_line=start, end_line=end),
                    replacement_lines=replacement,
                    reason=item.get("reason", "") if isinstance(item.get("reason"), str) else "",
                )
            )

        _ = diagnostics
        return edits

    def _extract_json_object(self, text: str) -> dict | None:
        text = (text or "").strip()
        if not text:
            return None

        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return None

        chunk = text[first : last + 1]
        try:
            value = json.loads(chunk)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
