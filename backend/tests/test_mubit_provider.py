"""The Mubit request contract and saved diagnosis provenance."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import db, incidents
from backend.app.main import app, provider_dependency
from backend.app.provider import MubitProvider


class MubitProviderTests(unittest.TestCase):
    def test_gateway_response_is_validated_and_saved_with_request_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(__file__).resolve().parents[2]
            incident_dir = Path(directory) / "incidents"
            incident_dir.mkdir()
            (incident_dir / "DEV-001.json").write_bytes(
                (root / "data/incidents/DEV-001.json").read_bytes()
            )

            class GatewayResponse(io.BytesIO):
                headers = {"x-middleware-request-id": "mreq_test"}

            answer = {
                "cause_label": "unknown",
                "supporting_evidence": [{
                    "field": "readings[0].value", "explanation": "This reading needs inspection."
                }],
                "alternative": "wheel obstruction",
                "next_check": "Inspect the wheel.",
                "uncertainty": "high",
            }
            gateway = GatewayResponse(json.dumps({
                "modelVersion": "gemini-3.8-flash",
                "candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}],
            }).encode())

            app.dependency_overrides[provider_dependency] = lambda: MubitProvider(
                "test-key", "gemini-3.8-flash", "https://api.mubit.ai/gemini"
            )
            try:
                with patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"), \
                     patch.object(incidents, "INCIDENT_DIR", incident_dir), \
                     patch("backend.app.provider.urlopen", return_value=gateway) as send:
                    with TestClient(app) as client:
                        response = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
                        self.assertEqual(response.status_code, 201)
                        saved = client.get(f"/api/diagnoses/{response.json()['id']}").json()
                        self.assertEqual(saved["provider_kind"], "mubit")
                        self.assertEqual(saved["request_reference"], "mreq_test")
                        self.assertEqual(saved["model_id"], "gemini-3.8-flash")
                        request = send.call_args.args[0]
                        self.assertEqual(request.full_url, "https://api.mubit.ai/gemini/v1beta/models/gemini-3.8-flash:generateContent")
                        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
                        payload = json.loads(request.data)
                        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
                        self.assertEqual(json.loads(payload["contents"][0]["parts"][0]["text"])["id"], "DEV-001")

                        missing_id = GatewayResponse(json.dumps({
                            "modelVersion": "gemini-3.8-flash",
                            "candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}],
                        }).encode())
                        missing_id.headers = {}
                        send.return_value = missing_id
                        rejected = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
                        self.assertEqual(rejected.status_code, 502)
                        self.assertEqual(len(client.get("/api/diagnoses").json()), 1)
            finally:
                app.dependency_overrides.clear()
