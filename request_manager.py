import os
import asyncio

from .config import DEFAULT_MODEL, MAX_PARALLEL_REQUESTS, PROVIDER_SERVERS
from .types import Edit, RequestContext, RequestResult


def parse_provider_model(model: str) -> tuple[str, str]:
    # Expected format: provider/model-name
    provider, model_name = model.split("/", 1)
    return provider, model_name


class RequestManager:
    """
    Can read/research/run tools in full project context.
    Can only return writable edits for current file.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.in_flight: dict[str, object] = {}
        self.parallel_limit = MAX_PARALLEL_REQUESTS

        provider, _ = parse_provider_model(model)
        cfg = PROVIDER_SERVERS[provider]
        self.base_url = cfg.base_url
        self.api_key = os.getenv(cfg.api_key_env)

        # Real implementation:
        # self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        self.client = ...

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
        response = await self._run_model_call(prompt)
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

    async def _run_model_call(self, prompt: str):
        _ = prompt
        # Real implementation should call provider client asynchronously.
        await asyncio.sleep(0)
        return {}

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
        # Parse structured model output into Edit[]
        _ = response
        return []
