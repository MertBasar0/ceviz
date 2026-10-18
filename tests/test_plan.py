import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
sys.path.insert(0, str(DEPLOY_DIR))

import plan  # noqa: E402

FRONTIER = ["nvidia/nemotron-3-ultra-550b-a55b", "anthropic/claude-sonnet-5", "anthropic/claude-haiku-4-5"]


def facts(gpu_gb=16.0, gpu_status="ok", threads=16, ram=32.0, openclaw=True, models=FRONTIER,
          default="anthropic/claude-sonnet-5", python="3.12.3", wsl=True, ollama=True, tailscale=False,
          disk=500.0, network=None):
    """A machine description in the shape probe() returns."""
    devices = [{"name": "Test GPU", "total_gb": gpu_gb, "used_gb": 1.0, "driver": "1"}] if gpu_status == "ok" else []
    targets = [m for m in models if m != default and m.split("/")[0] in plan.FRONTIER_PROVIDERS]
    return {
        "platform": {"system": "Linux", "machine": "x86_64", "wsl": wsl, "python": python},
        "cpu": {"model": "Test CPU", "threads": threads},
        "memory_gb": {"total": ram, "available": ram / 2},
        "gpu": {"status": gpu_status, "devices": devices, "detail": ""},
        "disk_free_gb": disk,
        "software": {
            "openclaw": ({"present": True, "path": "/usr/local/bin/openclaw", "version": "2026.10.1",
                          "models": {"readable": True, "default": default, "configured": list(models),
                                     "escalation_targets": targets}} if openclaw else {"present": False}),
            "node": {"present": True, "version": "22.0.0"},
            "ollama": {"present": ollama, "server": False, "models": []},
            "tailscale": {"present": tailscale},
        },
        "ceviz": {"systemd_user": True, "installed": False},
        "network": network,
    }


def steps(recipe):
    return {item["module"]: item for item in recipe["steps"]}


class RecipeTests(unittest.TestCase):
    def test_16_gb_card_runs_large_v3_and_can_offer_pusula(self):
        recipe = plan.recommend(facts())
        by = steps(recipe)
        self.assertEqual((by["speech"]["whisper_model"], by["speech"]["device"]), ("large-v3", "cuda"))
        self.assertEqual(by["pusula"]["status"], "optional")
        self.assertEqual(by["pusula"]["needs"], ["download the decision model (~4.5 GB)"])
        self.assertEqual(recipe["blockers"], [])
        without_ollama = steps(plan.recommend(facts(ollama=False)))["pusula"]["needs"]
        self.assertEqual(without_ollama[0], "install Ollama")

    def test_only_large_v3_is_planned_and_a_smaller_card_leaves_speech_to_the_iphone(self):
        # The desktop keeps 1.5 GB of a shared card and each plan leaves 0.6 GB of headroom.
        expected = {8.0: ("large-v3", "cuda"), 6.6: ("large-v3", "cuda"), 6.5: (None, None), 3.4: (None, None)}
        for card, (model, device) in expected.items():
            by = steps(plan.recommend(facts(gpu_gb=card, threads=8)))
            self.assertEqual((by["speech"]["whisper_model"], by["speech"]["device"]), (model, device), card)
            self.assertEqual(by["speech"]["engine"], "local" if model else "phone", card)
            self.assertEqual(by["pusula"]["status"], "not_recommended", card)
        phone = steps(plan.recommend(facts(gpu_gb=2.0, threads=8)))["speech"]
        self.assertEqual(phone["choice"], "Transcribe on the iPhone")
        self.assertIn("large-v3 needs about 5.1 GB", phone["reasons"][0])
        self.assertIn("no Whisper model is downloaded", phone["reasons"][-1])

    def test_unreachable_gpu_is_reported_and_planned_as_cpu(self):
        by = steps(plan.recommend(facts(gpu_status="blocked")))
        self.assertEqual((by["speech"]["whisper_model"], by["speech"]["device"]), ("large-v3", "cpu"))
        self.assertIn("wsl --shutdown", by["speech"]["reasons"][0])
        self.assertEqual(by["pusula"]["status"], "not_recommended")

    def test_a_strong_cpu_gets_large_v3_timed_and_a_weaker_one_the_iphone(self):
        by = steps(plan.recommend(facts(gpu_status="absent", threads=16, ram=32)))
        self.assertEqual((by["speech"]["whisper_model"], by["speech"]["device"]), ("large-v3", "cpu"))
        self.assertIn("the iPhone transcribes instead", by["speech"]["reasons"][-1])
        for threads, ram in ((8, 32), (16, 8), (2, 4)):
            weaker = steps(plan.recommend(facts(gpu_status="absent", threads=threads, ram=ram)))
            self.assertEqual(weaker["speech"]["engine"], "phone", (threads, ram))

    def test_installer_output_is_model_and_device_only(self):
        for machine, expected in ((facts(gpu_gb=5.0), "large-v3 cpu"), (facts(), "large-v3 cuda"),
                                  (facts(gpu_gb=5.0, threads=8), "phone none")):
            with mock.patch.object(plan, "probe", return_value=machine), \
                 mock.patch("builtins.print") as printed:
                self.assertEqual(plan.main(["--speech", "--offline"]), 0)
            stdout = [call.args[0] for call in printed.call_args_list if call.kwargs.get("file") is None]
            self.assertEqual(stdout, [expected])

    def test_transcribing_on_the_iphone_needs_no_model_disk_space(self):
        self.assertEqual(plan.recommend(facts(gpu_status="absent", threads=8, disk=6.0))["warnings"], [])
        low = plan.recommend(facts(disk=6.0))["warnings"]
        self.assertTrue(any("GB free" in line for line in low))

    def test_missing_openclaw_is_needed_and_pusula_waits_for_it(self):
        by = steps(plan.recommend(facts(openclaw=False)))
        self.assertEqual(by["executor"]["status"], "blocked")
        self.assertIn("subscription", " ".join(by["executor"]["reasons"]))
        self.assertEqual(by["pusula"]["status"], "later")

    def test_non_frontier_default_gets_a_quality_note(self):
        by = steps(plan.recommend(facts(default="nvidia/nemotron-3-ultra-550b-a55b")))
        self.assertIn("frontier default", by["executor"]["choice"])

    def test_pusula_needs_a_model_to_escalate_to(self):
        by = steps(plan.recommend(facts(models=["anthropic/claude-sonnet-5"])))
        self.assertEqual(by["pusula"]["status"], "not_recommended")
        self.assertIn("nothing to escalate to", by["pusula"]["reasons"][-1])

    def test_old_python_blocks_the_install(self):
        recipe = plan.recommend(facts(python="3.10.12"))
        self.assertTrue(any("3.11" in line for line in recipe["blockers"]))
        with mock.patch.object(plan, "probe", return_value=facts(python="3.10.12")), \
             mock.patch("builtins.print"):
            self.assertEqual(plan.main(["--offline"]), 1)

    def test_network_filtering_and_low_disk_are_warned(self):
        network = {"push_relay": {"ok": False, "error": "connection_reset"},
                   "huggingface": {"ok": True, "status": 200}, "ollama_registry": {"ok": True, "status": 200}}
        recipe = plan.recommend(facts(network=network, disk=6.0))
        text = " ".join(recipe["warnings"])
        self.assertIn("network filtering", text)
        self.assertIn("GB free", text)

    def test_network_choice_follows_what_is_installed(self):
        self.assertEqual(steps(plan.recommend(facts(tailscale=True)))["network"]["choice"], "Tailscale")
        self.assertIn("relay", steps(plan.recommend(facts()))["network"]["choice"])
        self.assertEqual(steps(plan.recommend(facts(wsl=False)))["network"]["choice"], "Manual address")

    def test_windows_openclaw_inside_wsl_is_flagged(self):
        machine = facts()
        machine["software"]["openclaw"]["path"] = "/mnt/c/Users/me/AppData/Roaming/npm/openclaw"
        self.assertTrue(any("Windows install" in line for line in plan.recommend(machine)["warnings"]))

    def test_installed_speech_recognition_that_differs_from_the_plan_is_reported(self):
        def installed(machine, settings):
            machine["ceviz"] = {"systemd_user": True, "installed": True, "active": True, "settings": settings}
            return plan.recommend(machine)["differences_from_current"]

        self.assertEqual(installed(facts(gpu_gb=5.0, threads=8), {"WATCH_CEVIZ_WHISPER_MODEL": "large-v3"}),
                         ["Speech recognition uses Whisper large-v3; the plan for this machine is "
                          "transcription on the iPhone."])
        self.assertEqual(installed(facts(), {"WATCH_CEVIZ_STT_ENGINE": "phone"}),
                         ["Speech recognition uses transcription on the iPhone; the plan for this machine is "
                          "Whisper large-v3."])
        self.assertEqual(installed(facts(), {"WATCH_CEVIZ_WHISPER_MODEL": "large-v3"}), [])

    def test_render_and_json_carry_the_recipe(self):
        machine = facts()
        recipe = plan.recommend(machine)
        self.assertIn("[RECOMMENDED] speech: Whisper large-v3 on the GPU", plan.render(machine, recipe))
        json.dumps({"facts": machine, "recipe": recipe})


class ParserTests(unittest.TestCase):
    def test_nvidia_output_and_lost_gpu_access(self):
        gpu = plan.parse_nvidia(0, "NVIDIA GeForce RTX 5070 Ti, 16303, 2057, 617.42")
        self.assertEqual(gpu["devices"][0]["total_gb"], 15.9)
        lost = plan.parse_nvidia(255, "Failed to initialize NVML: GPU access blocked by the operating system")
        self.assertEqual(lost["status"], "blocked")

    def test_only_configured_models_count_and_the_default_is_no_target(self):
        stdout = json.dumps({"models": [
            {"key": "nvidia/nemotron-3-ultra-550b-a55b", "tags": ["default", "configured"]},
            {"key": "anthropic/claude-sonnet-5", "tags": ["configured"]},
            {"key": "anthropic/claude-haiku-4-5", "tags": ["fallback#2", "configured"]},
            {"key": "openai/gpt-5.5", "tags": []},
        ]})
        models = plan.parse_openclaw_models(stdout)
        self.assertEqual(models["default"], "nvidia/nemotron-3-ultra-550b-a55b")
        self.assertEqual(models["escalation_targets"], ["anthropic/claude-sonnet-5", "anthropic/claude-haiku-4-5"])
        self.assertEqual(plan.parse_openclaw_models('{"ok": false, "error": {}}'), {"readable": False})
        self.assertEqual(plan.parse_openclaw_models("[openclaw] Could not start the CLI."), {"readable": False})

    def test_service_environment_never_keeps_the_pairing_token(self):
        line = ("Environment=WATCH_CEVIZ_AUTH_TOKEN=secret-pairing-token WATCH_CEVIZ_WHISPER_MODEL=large-v3 "
                "PATH=/usr/bin OPENCLAW_HOME=/home/me/.openclaw HOME=/home/me")
        settings = plan.parse_service_environment(line)
        self.assertEqual(settings, {"WATCH_CEVIZ_WHISPER_MODEL": "large-v3", "OPENCLAW_HOME": "/home/me/.openclaw"})
        self.assertEqual(plan.parse_service_environment(line, plan.SERVICE_RUNTIME), {"PATH": "/usr/bin"})
        self.assertNotIn("secret-pairing-token", json.dumps(settings))


if __name__ == "__main__":
    unittest.main()
