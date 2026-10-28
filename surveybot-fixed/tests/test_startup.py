"""Offline startup regressions. No paid APIs, account sign-ins or live surveys."""
import ast
import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "📁 Project Structure"
sys.path.insert(0, str(PROJECT))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StartupTests(unittest.TestCase):
    def test_help_works_without_site_packages_from_another_directory(self):
        result = subprocess.run([sys.executable, "-S", str(ROOT / "🎯 Main Files to Run" / "run_bot.py"), "--help"], cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--smoke-test", result.stdout)

    def test_all_project_python_sources_parse(self):
        count = 0
        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT)
            if any(part in {"venv", ".venv", ".git"} for part in relative.parts):
                continue
            ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            count += 1
        self.assertGreaterEqual(count, 10)

    def test_setup_can_run_before_dependencies_and_preserves_failure_status(self):
        launcher = load("startup_launcher", "🎯 Main Files to Run/run_bot.py")
        with patch.object(launcher, "check_dependencies", side_effect=AssertionError("must not run before setup")), patch.object(launcher.subprocess, "call", return_value=17) as call:
            self.assertEqual(launcher.main(["--setup"]), 17)
        self.assertEqual(call.call_args.kwargs["cwd"], ROOT)

    def test_default_visibility_does_not_override_configured_headless_mode(self):
        from config import Config
        launcher = load("visibility_launcher", "🎯 Main Files to Run/run_bot.py")
        with patch.object(Config, "HEADLESS", True), patch.object(launcher, "check_dependencies", return_value=True):
            self.assertEqual(launcher.main(["--config"]), 0)
            self.assertTrue(Config.HEADLESS)
            self.assertEqual(launcher.main(["--headed", "--config"]), 0)
            self.assertFalse(Config.HEADLESS)

    def test_missing_key_fails_before_browser_startup(self):
        from config import Config
        launcher = load("credentials_launcher", "🎯 Main Files to Run/run_bot.py")
        with patch.object(Config, "GOOGLE_API_KEY", ""), patch.object(launcher, "check_dependencies", return_value=True), patch.object(launcher, "run_bot", side_effect=AssertionError("browser must not start")):
            self.assertEqual(launcher.main([]), 2)

    def test_setup_preserves_existing_environment_file(self):
        setup = load("bootstrap_setup", "🔧 Tools and Scripts/setup.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / ".env"
            destination.write_text("USER_SETTING=keep-this\n")
            with patch.object(setup, "ROOT", root):
                setup.create_env_file()
            self.assertEqual(destination.read_text(), "USER_SETTING=keep-this\n")

    def test_relative_local_paths_are_anchored_to_project(self):
        from config import local_path
        with patch.dict(os.environ, {"SURVEY_TEST_PATH": "custom/auth.json"}):
            self.assertEqual(local_path("SURVEY_TEST_PATH", "unused"), ROOT / "custom" / "auth.json")

    def test_requirement_files_do_not_have_conflicting_exact_pins(self):
        pins = {}
        def read(path):
            for line in path.read_text().splitlines():
                line = line.strip()
                if line.startswith("-r "):
                    read(path.parent / line[3:].strip())
                elif line and not line.startswith("#") and "==" in line:
                    name, version = line.split("==", 1)
                    if name in pins:
                        self.assertEqual(pins[name], version, f"Conflicting versions of {name}")
                    pins[name] = version
        read(ROOT / "⚙️ Configurations" / "requirements.txt")

    def test_gemini_sdk_serializes_screenshot_and_decodes_response_over_rest(self):
        import httpx
        from google import genai
        from google.genai import types
        from gemini_support import GeminiModel
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": "Local SDK fixture response"}]}, "finishReason": "STOP"}]})
        original_client = genai.Client
        def client(**kwargs):
            kwargs["http_options"] = types.HttpOptions(client_args={"transport": httpx.MockTransport(respond), "trust_env": False})
            return original_client(**kwargs)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-only-not-a-real-key", "GEMINI_API_KEY": ""}), patch("gemini_support.genai.Client", side_effect=client):
            model = GeminiModel(json_output=True)
            try:
                response = model.generate_content(["Explain this local fixture.", {"mime_type": "image/png", "data": b"fixture-image"}])
                self.assertEqual(response.text, "Local SDK fixture response")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].url.host, "generativelanguage.googleapis.com")
                body = json.loads(requests[0].content)
                self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
                image = body["contents"][0]["parts"][1]["inlineData"]
                # Protobuf JSON accepts the original field name and its JSON alias.
                self.assertEqual(image.get("mimeType", image.get("mime_type")), "image/png")
                self.assertEqual(base64.b64decode(image["data"]), b"fixture-image")
            finally:
                model.client.close()

    def test_personal_answer_generation_stops_without_ai(self):
        import personality_responses as responses
        generator = responses.PersonalityResponseGenerator({"about_you": {}})
        with patch.object(responses, "USE_GEMINI_API", False), patch.object(responses, "model", None):
            self.assertEqual(asyncio.run(generator.generate_response("What is your occupation?")), "")
        self.assertEqual(generator.personality_data, {"about_you": {}})

    def test_personal_answer_prompt_includes_only_supplied_profile_context(self):
        import personality_responses as responses
        captured = []
        def generate(prompt):
            captured.append(prompt)
            return SimpleNamespace(text="The fixture role is a librarian.")
        generator = responses.PersonalityResponseGenerator({"about_you": {"occupation": "fixture librarian"}})
        with patch.object(responses, "USE_GEMINI_API", True), patch.object(responses, "model", SimpleNamespace(generate_content=generate)):
            result = asyncio.run(generator.generate_response("What is your occupation?"))
        self.assertEqual(result, "The fixture role is a librarian.")
        self.assertIn('"occupation": "fixture librarian"', captured[0])
        self.assertIn("Do not invent", captured[0])


if __name__ == "__main__":
    unittest.main()
