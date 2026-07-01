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


class CfuseScanTest(unittest.TestCase):
    def setUp(self):
        self.module = load_usage_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module.CFUSE_PROXY_STATS_DIR = self.tmp.name
        self.module.CFUSE_CC_PROJECT_DIRS = []
        self.bounds = self.module.range_bounds()
        self.today = self.bounds["today"]

    def write_stats(self, filename, requests, engine=None):
        payload = {
            "engine": engine,
            "totalRequests": len(requests),
            "successRequests": sum(1 for r in requests if int(r.get("statusCode") or 0) < 400),
            "errorRequests": sum(1 for r in requests if int(r.get("statusCode") or 0) >= 400),
            "recentRequests": requests,
        }
        if engine is None:
            payload.pop("engine")
        path = os.path.join(self.tmp.name, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def ms_at(self, hour, minute=0):
        dt = self.today + timedelta(hours=hour, minutes=minute)
        return int(dt.timestamp() * 1000)

    def test_missing_proxy_stats_directory_returns_empty_ranges(self):
        self.module.CFUSE_PROXY_STATS_DIR = os.path.join(self.tmp.name, "missing")

        result = self.module.scan_cfuse(self.bounds, {})

        today = result["ranges"]["today"]
        self.assertEqual(today["requests"], 0)
        self.assertEqual(today["success"], 0)
        self.assertEqual(today["errors"], 0)
        self.assertEqual(today["sessions"], set())
        self.assertEqual(today["models"], {})
        self.assertEqual(today["engines"], {})

    def test_scan_cfuse_aggregates_message_requests_by_engine_model_project(self):
        self.write_stats("cc-2026-06-30.json", [
            {
                "id": "req-1",
                "path": "/v1/messages?beta=true",
                "model": "antchat/GLM-5.1",
                "startTime": self.ms_at(10),
                "statusCode": 200,
                "requestSize": 100,
                "responseSize": 10,
                "sessionId": "s1",
                "cwd": "/repo",
                "duration": 1000,
                "ttftMs": 500,
            },
            {
                "id": "req-1",
                "path": "/v1/messages?beta=true",
                "model": "antchat/GLM-5.1",
                "startTime": self.ms_at(10, 1),
                "statusCode": 200,
                "requestSize": 999,
                "sessionId": "s1",
                "cwd": "/repo",
                "duration": 999,
                "ttftMs": 999,
            },
            {
                "id": "req-2",
                "path": "/v1/messages?beta=true",
                "model": "glink/claude-opus-4-6",
                "startTime": self.ms_at(11),
                "statusCode": 500,
                "error": "upstream",
                "requestSize": 200,
                "sessionId": "s2",
                "cwd": "/repo",
                "duration": 3000,
                "ttftMs": 1500,
            },
            {
                "id": "req-count",
                "path": "/count_tokens",
                "model": "antchat/GLM-5.1",
                "startTime": self.ms_at(12),
                "statusCode": 200,
                "requestSize": 1000,
                "sessionId": "s3",
                "cwd": "/repo",
                "duration": 100,
                "ttftMs": 50,
            },
        ], engine="cc")
        self.write_stats("other-2026-06-30.json", [
            {
                "id": "req-3",
                "path": "/v1/messages?beta=true",
                "model": "other/model",
                "startTime": self.ms_at(13),
                "statusCode": 200,
                "requestSize": 300,
                "sessionId": "s1",
                "cwd": "/other",
                "duration": 2000,
                "ttftMs": 1000,
            },
        ])

        result = self.module.scan_cfuse(self.bounds, {})

        today = result["ranges"]["today"]
        self.assertEqual(today["requests"], 3)
        self.assertEqual(today["success"], 2)
        self.assertEqual(today["errors"], 1)
        self.assertEqual(today["request_size"], 600)
        self.assertEqual(today["response_size"], 10)
        self.assertEqual(today["duration_sum"], 6000)
        self.assertEqual(today["ttft_sum"], 3000)
        self.assertEqual(today["ttft_count"], 3)
        self.assertEqual(today["sessions"], {"s1", "s2"})
        self.assertEqual(today["models"]["antchat/GLM-5.1"]["requests"], 1)
        self.assertEqual(today["models"]["glink/claude-opus-4-6"]["requests"], 1)
        self.assertEqual(today["models"]["other/model"]["requests"], 1)
        self.assertEqual(today["engines"]["cc"]["requests"], 2)
        self.assertEqual(today["engines"]["other"]["requests"], 1)
        self.assertEqual(today["engines"]["cc"]["models"]["antchat/GLM-5.1"]["requests"], 1)
        self.assertEqual(today["projects"]["/repo"]["requests"], 2)
        self.assertEqual(today["projects"]["/other"]["requests"], 1)

    def test_scan_cfuse_counts_cc_project_usage_once_per_message_id(self):
        projects = os.path.join(self.tmp.name, "projects")
        proj = os.path.join(projects, "-repo")
        os.makedirs(proj)
        self.module.CFUSE_CC_PROJECT_DIRS = [projects]

        def assistant(message_id, output_tokens, ts_offset=0, model="claude-opus-4-6"):
            return {
                "type": "assistant",
                "timestamp": (self.today + timedelta(hours=9, seconds=ts_offset)).isoformat(),
                "sessionId": "s-cc",
                "cwd": "/repo",
                "message": {
                    "id": message_id,
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "usage": {
                        "input_tokens": 100 if model.startswith("claude") else 10,
                        "output_tokens": output_tokens,
                        "cache_read_input_tokens": 200 if model.startswith("claude") else 0,
                        "cache_creation_input_tokens": 30 if model.startswith("claude") else 5,
                    },
                },
            }

        path = os.path.join(proj, "s-cc.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(assistant("msg-1", 10, 0)) + "\n")
            f.write(json.dumps(assistant("msg-1", 70, 1)) + "\n")
            f.write(json.dumps(assistant("msg-2", 20, 2, model="GLM-5.2")) + "\n")

        result = self.module.scan_cfuse(self.bounds, {})

        today = result["ranges"]["today"]
        self.assertEqual(today["requests"], 0)
        self.assertEqual(today["messages"], 2)
        self.assertEqual(today["in"], 110)
        self.assertEqual(today["out"], 90)
        self.assertEqual(today["cr"], 200)
        self.assertEqual(today["cw"], 35)
        self.assertGreater(today["cost"], 0)
        self.assertEqual(today["sessions"], {"s-cc"})
        self.assertEqual(today["models"]["claude-opus-4-6"]["messages"], 1)
        self.assertEqual(today["models"]["claude-opus-4-6"]["out"], 70)
        self.assertEqual(today["models"]["GLM-5.2"]["messages"], 1)
        self.assertEqual(today["engines"]["cc"]["messages"], 2)
        self.assertEqual(today["engines"]["cc"]["models"]["claude-opus-4-6"]["messages"], 1)
        self.assertEqual(today["projects"]["/repo"]["messages"], 2)


if __name__ == "__main__":
    unittest.main()
