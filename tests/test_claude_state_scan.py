import importlib.util
import json
import os
import tempfile
import unittest
from datetime import timedelta


def load_usage_module():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "usage.30s.py")
    spec = importlib.util.spec_from_file_location("tokei_usage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClaudeStateScanTest(unittest.TestCase):
    def setUp(self):
        self.module = load_usage_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects = os.path.join(self.tmp.name, "projects")
        os.makedirs(self.projects)
        self.module.CLAUDE_DIR = self.projects
        self.module.CLAUDE_STATE = os.path.join(self.tmp.name, ".claude.json")
        self.module.CLAUDE_HISTORY = os.path.join(self.tmp.name, "history.jsonl")
        self.bounds = self.module.range_bounds()
        self.sample_dt = self.bounds["year"] + timedelta(days=7, hours=10)

    def write_state(self, session_id, modified=0, cost=2.5):
        payload = {
            "projects": {
                "/repo": {
                    "lastSessionId": session_id,
                    "lastSessionModified": modified,
                    "lastCost": cost,
                    "lastTotalInputTokens": 100,
                    "lastTotalOutputTokens": 20,
                    "lastTotalCacheReadInputTokens": 300,
                    "lastTotalCacheCreationInputTokens": 40,
                    "lastModelUsage": {
                        "claude-opus-4-6": {
                            "inputTokens": 100,
                            "outputTokens": 20,
                            "cacheReadInputTokens": 300,
                            "cacheCreationInputTokens": 40,
                            "costUSD": cost,
                        }
                    },
                }
            }
        }
        with open(self.module.CLAUDE_STATE, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def write_history(self, session_id):
        payload = {
            "sessionId": session_id,
            "project": "/repo",
            "timestamp": int(self.sample_dt.timestamp() * 1000),
        }
        with open(self.module.CLAUDE_HISTORY, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def test_claude_state_fallback_uses_history_date_when_modified_missing(self):
        self.write_state("state-only", modified=0, cost=2.5)
        self.write_history("state-only")

        result = self.module.scan_claude(self.bounds, {})

        year = result["ranges"]["year"]
        self.assertEqual(year["sessions"], {"state:state-only"})
        self.assertEqual(year["in"], 100)
        self.assertEqual(year["out"], 20)
        self.assertEqual(year["cr"], 300)
        self.assertEqual(year["cw"], 40)
        self.assertEqual(year["cost"], 2.5)
        self.assertEqual(year["models"]["claude-opus-4-6"]["cost"], 2.5)

    def test_claude_state_fallback_skips_sessions_already_in_jsonl(self):
        session_dir = os.path.join(self.projects, "repo")
        os.makedirs(session_dir)
        line = {
            "type": "assistant",
            "timestamp": self.sample_dt.isoformat(),
            "sessionId": "dup",
            "message": {
                "id": "msg-1",
                "model": "<synthetic>",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }
        with open(os.path.join(session_dir, "dup.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        self.write_state("dup", modified=int(self.sample_dt.timestamp() * 1000), cost=2.5)

        result = self.module.scan_claude(self.bounds, {})

        year = result["ranges"]["year"]
        self.assertEqual(year["sessions"], {"dup"})
        self.assertEqual(year["in"], 10)
        self.assertEqual(year["out"], 2)
        self.assertEqual(year["cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
