import json
import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import router_plugin  # noqa: E402
from openclaw_client import OpenClawClient  # noqa: E402
from router_plugin import ROUTER_API_VERSION, RouterHost  # noqa: E402


class FakeRouter:
    api_version = ROUTER_API_VERSION

    def __init__(self, answer=None, error=None, delay=0.0):
        self.answer = answer
        self.error = error
        self.delay = delay
        self.requests = []

    def route(self, request):
        self.requests.append(request)
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.answer


def host_with(router, name="fake", hosts=None):
    """A RouterHost whose entry-point lookup returns a factory for `router`."""
    seen = hosts if hosts is not None else []

    def factory(host):
        seen.append(host)
        return router

    return RouterHost(agent="cevizmain", name=name, loader=lambda _name: factory)


class RouterHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"WATCH_CEVIZ_STATE_DIR": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("WATCH_CEVIZ_ROUTER", None)
        os.environ.pop("WATCH_CEVIZ_ROUTER_TIMEOUT_MS", None)

    def test_unset_router_never_looks_for_plugins(self) -> None:
        loader = mock.Mock(side_effect=AssertionError("must not look up plugins"))
        host = RouterHost(agent="cevizmain", loader=loader)
        self.assertFalse(host.enabled)
        self.assertIsNone(host.choose("Selam"))
        loader.assert_not_called()
        self.assertIn("disabled", host.status())

    def test_enabled_router_receives_v1_request_and_host_info(self) -> None:
        jobs = [
            {"transcript": "eski", "status": "completed", "outcome": "done", "created_at": time.time() - 3600},
            {"transcript": "logları özetle", "status": "completed", "outcome": "blocked", "created_at": time.time() - 60},
            {"transcript": "çalışıyor", "status": "running", "created_at": time.time() - 10},
        ]
        (Path(self.tmp.name) / "jobs.json").write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        router = FakeRouter({"model": "anthropic/claude-sonnet-5", "thinking": "medium", "reason": "correction"})
        hosts = []
        choice = host_with(router, hosts=hosts).choose("tekrar dene", continuation="önceki iş", locale="tr-TR")

        self.assertEqual(choice.argv(), ["--model", "anthropic/claude-sonnet-5", "--thinking", "medium"])
        self.assertEqual(choice.reason, "correction")
        self.assertEqual(hosts, [{"api_version": 1, "agent": "cevizmain", "state_dir": self.tmp.name}])
        request = router.requests[0]
        self.assertEqual(request["api_version"], 1)
        self.assertEqual(request["transcript"], "tekrar dene")
        self.assertEqual(request["continuation"], "önceki iş")
        self.assertEqual(request["locale"], "tr-TR")
        # Only finished jobs from the last 15 minutes form the trajectory.
        self.assertEqual([job["transcript"] for job in request["recent_jobs"]], ["logları özetle"])
        self.assertEqual(request["recent_jobs"][0]["outcome"], "blocked")

    def test_none_or_empty_answers_keep_the_agent_default(self) -> None:
        for answer in (None, {}, {"reason": "light"}, {"model": None, "thinking": None}):
            with self.subTest(answer=answer):
                self.assertIsNone(host_with(FakeRouter(answer)).choose("Selam"))

    def test_invalid_values_never_reach_argv(self) -> None:
        cases = [
            {"model": "--config=/tmp/x"},
            {"model": "anthropic/claude sonnet"},
            {"model": 42},
            {"thinking": "--yolo"},
            {"thinking": "HIGH; rm"},
            ["anthropic/claude-sonnet-5"],
        ]
        for answer in cases:
            with self.subTest(answer=answer):
                self.assertIsNone(host_with(FakeRouter(answer)).choose("Selam"))
        partial = host_with(FakeRouter({"model": "openai/gpt-5.2", "thinking": "--bad"})).choose("Selam")
        self.assertEqual(partial.argv(), ["--model", "openai/gpt-5.2"])

    def test_router_failures_keep_the_agent_default(self) -> None:
        self.assertIsNone(host_with(FakeRouter(error=RuntimeError("boom"))).choose("Selam"))

    def test_slow_router_times_out_to_the_agent_default(self) -> None:
        os.environ["WATCH_CEVIZ_ROUTER_TIMEOUT_MS"] = "50"
        router = FakeRouter({"model": "anthropic/claude-sonnet-5"}, delay=0.5)
        started = time.monotonic()
        self.assertIsNone(host_with(router).choose("Selam"))
        self.assertLess(time.monotonic() - started, 0.4)

    def test_contract_mismatch_or_missing_plugin_disables_routing(self) -> None:
        class OldRouter(FakeRouter):
            api_version = 0

        self.assertIsNone(host_with(OldRouter({"model": "anthropic/claude-sonnet-5"})).choose("Selam"))
        missing = RouterHost(agent="cevizmain", name="pusula")
        with mock.patch.object(router_plugin, "entry_points", return_value=[]):
            self.assertIsNone(missing.choose("Selam"))
            self.assertIn("unavailable", missing.status())

    def test_router_loads_once(self) -> None:
        loads = []
        router = FakeRouter({"model": "anthropic/claude-sonnet-5"})

        def loader(name):
            loads.append(name)
            return lambda host: router

        host = RouterHost(agent="cevizmain", name="fake", loader=loader)
        host.choose("bir")
        host.choose("iki")
        self.assertEqual(loads, ["fake"])

    def test_entry_point_lookup_uses_the_ceviz_routers_group(self) -> None:
        entry = mock.Mock()
        entry.load.return_value = lambda host: FakeRouter({"thinking": "high"})
        with mock.patch.object(router_plugin, "entry_points", return_value=[entry]) as lookup:
            choice = RouterHost(agent="cevizmain", name="pusula").choose("Selam")
        lookup.assert_called_once_with(group="ceviz.routers", name="pusula")
        self.assertEqual(choice.argv(), ["--thinking", "high"])

    def test_installed_distribution_is_discovered_through_its_entry_point(self) -> None:
        # A real (if minimal) installed distribution: no mocking of importlib.metadata.
        site = Path(self.tmp.name) / "site"
        (site / "fake_ceviz_router").mkdir(parents=True)
        (site / "fake_ceviz_router" / "__init__.py").write_text(
            textwrap.dedent(
                """
                class Router:
                    api_version = 1
                    def __init__(self, host):
                        self.host = host
                    def route(self, request):
                        return {"model": "anthropic/claude-haiku-4-5", "reason": self.host["agent"]}

                def create(host):
                    return Router(host)
                """
            ),
            encoding="utf-8",
        )
        dist = site / "fake_ceviz_router-0.0.1.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: fake-ceviz-router\nVersion: 0.0.1\n", encoding="utf-8")
        (dist / "entry_points.txt").write_text("[ceviz.routers]\nfake = fake_ceviz_router:create\n", encoding="utf-8")
        sys.path.insert(0, str(site))
        self.addCleanup(sys.path.remove, str(site))
        self.addCleanup(sys.modules.pop, "fake_ceviz_router", None)

        choice = RouterHost(agent="cevizmain", name="fake").choose("Selam")
        self.assertEqual(choice.argv(), ["--model", "anthropic/claude-haiku-4-5"])
        self.assertEqual(choice.reason, "cevizmain")
        self.assertIsNone(RouterHost(agent="cevizmain", name="not-installed").choose("Selam"))


class OpenClawClientRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ.pop("WATCH_CEVIZ_ROUTER", None)

    def invoke(self, client, payload):
        with mock.patch.object(client, "_assert_source_runtime_ready"), mock.patch.object(
            client, "_build_prompt", return_value="test prompt"
        ), mock.patch("openclaw_client.subprocess.Popen", return_value=mock.Mock()) as popen:
            client.invoke_watch_command(payload)
        return popen.call_args.args[0]

    def test_without_a_router_commands_never_pin_a_model(self) -> None:
        client = OpenClawClient(agent="cevizmain", runtime_dir=self.tmp.name)
        command = self.invoke(client, {"transcript": "Hayır bunu kastetmedim, tekrar dene"})
        self.assertNotIn("--model", command)
        self.assertNotIn("--thinking", command)

    def test_enabled_router_choice_is_appended_to_the_command(self) -> None:
        client = OpenClawClient(agent="cevizmain", runtime_dir=self.tmp.name)
        client.router = host_with(FakeRouter({"model": "anthropic/claude-sonnet-5", "thinking": "high"}))
        command = self.invoke(client, {"transcript": "yine olmadı", "locale": "tr-TR"})
        self.assertEqual(command[-4:], ["--model", "anthropic/claude-sonnet-5", "--thinking", "high"])
        self.assertTrue(client.is_pinned(command))

    def test_router_failure_still_starts_the_command_unpinned(self) -> None:
        client = OpenClawClient(agent="cevizmain", runtime_dir=self.tmp.name)
        client.router = host_with(FakeRouter(error=RuntimeError("boom")))
        command = self.invoke(client, {"transcript": "Selam"})
        self.assertEqual(command[:3], ["openclaw", "agent", "--agent"])
        self.assertNotIn("--model", command)


if __name__ == "__main__":
    unittest.main()
