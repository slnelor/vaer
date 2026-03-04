import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "scripts" / "vaer_adapter.py"
SPEC = importlib.util.spec_from_file_location("vaer_adapter", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load scripts/vaer_adapter.py")
vaer_adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vaer_adapter)


class WebRoutingTests(unittest.TestCase):
    def test_explicit_web_intent_forces_route(self):
        payload = {
            "provider": {"task_intent": "web_research"},
            "file_text": "1| def search_web_reports(items):\n2|     return items",
        }

        self.assertTrue(vaer_adapter.looks_like_web_research_task(payload))
        should_route, reason = vaer_adapter.should_route_to_opencode_for_web_task(payload)
        self.assertTrue(should_route)
        self.assertEqual(reason, "explicit_task_intent")

    def test_explicit_code_intent_disables_route(self):
        payload = {
            "provider": {"task_intent": "code_edit"},
            "file_text": "1| Please research the latest web security news and prepare a report with sources.",
        }

        self.assertFalse(vaer_adapter.looks_like_web_research_task(payload))
        should_route, reason = vaer_adapter.should_route_to_opencode_for_web_task(payload)
        self.assertFalse(should_route)
        self.assertEqual(reason, "explicit_task_intent_disabled")

    def test_heuristic_ignores_code_like_content(self):
        payload = {
            "file_text": (
                "1| def search_latest_reports(sources):\n"
                "2|     current = sources.get(\"news\")\n"
                "3|     return current"
            )
        }

        self.assertFalse(vaer_adapter.looks_like_web_research_task(payload))
        should_route, reason = vaer_adapter.should_route_to_opencode_for_web_task(payload)
        self.assertFalse(should_route)
        self.assertEqual(reason, "not_web_task")

    def test_heuristic_matches_natural_language_research_task(self):
        payload = {
            "file_text": (
                "1| Please research the latest web security news and prepare a report with citations.\n"
                "2| Focus on incidents from the last 30 days."
            )
        }

        self.assertTrue(vaer_adapter.looks_like_web_research_task(payload))
        should_route, reason = vaer_adapter.should_route_to_opencode_for_web_task(payload)
        self.assertTrue(should_route)
        self.assertEqual(reason, "heuristic")

    def test_route_disable_flag_overrides_intent(self):
        payload = {
            "provider": {
                "task_intent": "web_research",
                "route_web_tasks_to_opencode": False,
            },
            "file_text": "1| Please research current online attacks and write a report.",
        }

        should_route, reason = vaer_adapter.should_route_to_opencode_for_web_task(payload)
        self.assertFalse(should_route)
        self.assertEqual(reason, "route_disabled")


class FallbackTests(unittest.TestCase):
    def test_fallback_for_timeout_error(self):
        payload = {"provider": {"route_fallback_to_inception_on_error": True}}
        routed = {
            "edits": [],
            "diagnostics": ["opencode run timeout (85s)"],
        }

        self.assertTrue(vaer_adapter.should_fallback_to_inception(payload, routed))

    def test_fallback_for_prefixed_event_error(self):
        payload = {"provider": {"route_fallback_to_inception_on_error": True}}
        routed = {
            "edits": [],
            "diagnostics": ["opencode_event_error=Model not found: foo/bar"],
        }

        self.assertTrue(vaer_adapter.should_fallback_to_inception(payload, routed))

    def test_no_fallback_when_edits_are_present(self):
        payload = {"provider": {"route_fallback_to_inception_on_error": True}}
        routed = {
            "edits": [{"target_file": "x", "start_line": 1, "end_line": 1, "replacement_lines": ["ok"]}],
            "diagnostics": ["opencode_exit=1"],
        }

        self.assertFalse(vaer_adapter.should_fallback_to_inception(payload, routed))

    def test_no_fallback_for_non_operational_no_edit(self):
        payload = {"provider": {"route_fallback_to_inception_on_error": True}}
        routed = {
            "edits": [],
            "diagnostics": ["model declined to edit current range"],
        }

        self.assertFalse(vaer_adapter.should_fallback_to_inception(payload, routed))

    def test_fallback_can_be_disabled(self):
        payload = {"provider": {"route_fallback_to_inception_on_error": False}}
        routed = {
            "edits": [],
            "diagnostics": ["opencode_exit=1"],
        }

        self.assertFalse(vaer_adapter.should_fallback_to_inception(payload, routed))


if __name__ == "__main__":
    unittest.main()
