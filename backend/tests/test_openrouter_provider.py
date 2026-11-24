"""The OpenRouter and Mubit-compatible transport contracts, without paid calls."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from backend.app import db, provider as providers
from backend.app.diagnosis import build_diagnosis
from backend.app.provider import OpenAICompatibleProvider, ProviderFailure, ProviderTimeout, ProviderUnavailable, TASK_INSTRUCTIONS, serialize_incident
from backend.app.schemas import Incident


ROOT = Path(__file__).resolve().parents[2]


class Reply(io.BytesIO):
    def __init__(self, body, reference=""):
        super().__init__(json.dumps(body).encode() if not isinstance(body, bytes) else body)
        self.headers = {"x-middleware-request-id": reference} if reference else {}


def answer(content="wheel obstruction"):
    return {"id": "gen_test", "model": "deepseek/example", "choices": [{"message": {"content": content}}]}


class OpenRouterProviderTests(unittest.TestCase):
    def setUp(self):
        self.incident = Incident.model_validate_json((ROOT / "data/incidents/DEV-001.json").read_text())
        self.provider = OpenAICompatibleProvider("test-openrouter-key", "deepseek/example", "https://openrouter.ai/api/v1")

    def test_direct_request_and_saved_provenance_are_not_mubit(self):
        with patch("backend.app.provider.urlopen", return_value=Reply(answer())) as send:
            record = build_diagnosis(self.incident, self.provider)
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-openrouter-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["messages"], [
            {"role": "system", "content": TASK_INSTRUCTIONS},
            {"role": "user", "content": serialize_incident(self.incident)},
        ])
        self.assertEqual(payload["max_tokens"], 128)
        self.assertFalse(payload["reasoning"]["enabled"])
        self.assertEqual(record.provider_kind, "openrouter")
        self.assertEqual(record.request_reference, "gen_test")
        self.assertEqual(record.advisory_source, "application_rules")
        with tempfile.TemporaryDirectory() as directory, patch.object(db, "DB_PATH", Path(directory) / "history.sqlite3"):
            db.initialize_database()
            db.save_diagnosis(record)
            saved = db.get_diagnosis(record.id)
            self.assertEqual(saved.provider_kind, "openrouter")
            self.assertEqual(saved.raw_response, "wheel obstruction")
            self.assertEqual(saved.model_id, "deepseek/example")

    def test_mubit_route_requires_gateway_reference_and_preserves_label(self):
        provider = OpenAICompatibleProvider("test-mubit-key", "deepseek/example", "https://api.mubit.ai/compat/openrouter/v1", "mubit")
        with patch("backend.app.provider.urlopen", return_value=Reply(answer(), "mreq_test")) as send:
            record = build_diagnosis(self.incident, provider)
        self.assertEqual(send.call_args.args[0].full_url, "https://api.mubit.ai/compat/openrouter/v1/chat/completions")
        self.assertEqual(record.provider_kind, "mubit")
        self.assertEqual(record.request_reference, "mreq_test")
        with patch("backend.app.provider.urlopen", return_value=Reply(answer())):
            with self.assertRaises(ProviderFailure):
                provider.diagnose(self.incident)

    def test_gateway_errors_and_invalid_answers_are_not_silently_retried(self):
        failures = [Reply(b"not json"), Reply({"error": {"message": "denied"}}),
                    Reply(answer(None)), Reply({**answer(), "id": ""}), Reply(answer("wheel obstruction or unknown"))]
        for reply in failures:
            with self.subTest(reply=reply.getvalue()), patch("backend.app.provider.urlopen", return_value=reply) as send:
                with self.assertRaises(ProviderFailure):
                    build_diagnosis(self.incident, self.provider)
                self.assertEqual(send.call_count, 1)
        with patch("backend.app.provider.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(ProviderTimeout):
                self.provider.diagnose(self.incident)
        error = HTTPError("https://openrouter.ai/api/v1/chat/completions", 402, "credit required", {}, io.BytesIO())
        with patch("backend.app.provider.urlopen", side_effect=error):
            with self.assertRaisesRegex(ProviderFailure, "HTTP 402"):
                self.provider.diagnose(self.incident)

    def test_factory_distinguishes_keys_and_protocols(self):
        with patch.object(providers, "PROVIDER_MODE", "openrouter"), patch.object(providers, "OPENROUTER_API_KEY", ""):
            with self.assertRaises(ProviderUnavailable):
                providers.configured_provider()
        with patch.object(providers, "PROVIDER_MODE", "mubit"), patch.object(providers, "MUBIT_API_KEY", "test-mubit"), patch.object(providers, "MUBIT_API_FORMAT", "openai"):
            result = providers.configured_provider()
            self.assertIsInstance(result, OpenAICompatibleProvider)
            self.assertEqual(result.provider_kind, "mubit")


if __name__ == "__main__":
    unittest.main()
