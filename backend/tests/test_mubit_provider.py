"""Gateway failure boundaries and the stable classifier contract."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from backend.app import db, incidents
from backend.app.main import app, provider_dependency
from backend.app.provider import MubitProvider, TASK_INSTRUCTIONS, serialize_incident
from backend.app.schemas import Incident


ROOT = Path(__file__).resolve().parents[2]


class GatewayResponse(io.BytesIO):
    def __init__(self, body: bytes, request_id: str = "mreq_test"):
        super().__init__(body)
        self.headers = {"x-middleware-request-id": request_id} if request_id else {}


def answer(text: str) -> bytes:
    return json.dumps({
        "modelVersion": "gemini-3.8-flash",
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}],
    }).encode()


class MubitProviderTests(unittest.TestCase):
    def test_classifier_contract_and_saved_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            incident_dir = Path(directory) / "incidents"
            incident_dir.mkdir()
            (incident_dir / "DEV-001.json").write_bytes(
                (ROOT / "data/incidents/DEV-001.json").read_bytes()
            )
            app.dependency_overrides[provider_dependency] = lambda: MubitProvider(
                "test-key", "gemini-3.8-flash", "https://api.mubit.ai/gemini"
            )
            try:
                with patch.object(db, "DB_PATH", Path(directory) / "test.sqlite3"), \
                     patch.object(incidents, "INCIDENT_DIR", incident_dir), \
                     patch("backend.app.provider.urlopen", return_value=GatewayResponse(answer("wheel obstruction"))) as send:
                    with TestClient(app) as client:
                        response = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
                        self.assertEqual(response.status_code, 201, response.text)
                        saved = client.get(f"/api/diagnoses/{response.json()['id']}").json()
                        self.assertEqual(saved["model_label"], "wheel obstruction")
                        self.assertEqual(saved["diagnosis"]["cause_label"], "wheel obstruction")
                        self.assertEqual(saved["advisory_source"], "application_rules")
                        self.assertEqual(saved["raw_response"], "wheel obstruction")
                        self.assertEqual(saved["request_reference"], "mreq_test")
                        self.assertEqual(saved["diagnosis"]["supporting_evidence"][0]["field"], "readings[1].value")
                        request = send.call_args.args[0]
                        payload = json.loads(request.data)
                        self.assertEqual(request.full_url, "https://api.mubit.ai/gemini/v1beta/models/gemini-3.8-flash:generateContent")
                        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], TASK_INSTRUCTIONS)
                        case_text = payload["contents"][0]["parts"][0]["text"]
                        incident = Incident.model_validate_json((incident_dir / "DEV-001.json").read_text())
                        self.assertEqual(case_text, serialize_incident(incident))
                        self.assertNotIn("generationConfig", payload)
                        self.assertNotIn("DEV-001", case_text)

                        failures = [
                            (GatewayResponse(answer("wheel obstruction and unknown")), "mreq_test"),
                            (GatewayResponse(json.dumps({"candidates": []}).encode()), "mreq_test"),
                            (GatewayResponse(b"{bad json"), "mreq_test"),
                            (GatewayResponse(answer("wheel obstruction"), request_id=""), "lacks a request ID"),
                            (HTTPError(request.full_url, 403, "denied", {"x-middleware-request-id": "mreq_error"}, io.BytesIO(b'{"error":"denied"}')), "mreq_error"),
                        ]
                        for gateway, detail in failures:
                            with self.subTest(gateway=type(gateway).__name__):
                                if isinstance(gateway, HTTPError):
                                    send.side_effect = gateway
                                else:
                                    send.side_effect = None
                                    send.return_value = gateway
                                rejected = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
                                self.assertEqual(rejected.status_code, 502, rejected.text)
                                self.assertIn(detail, rejected.json()["detail"])
                                if isinstance(gateway, HTTPError):
                                    gateway.close()
                        self.assertEqual(len(client.get("/api/diagnoses").json()), 1)
            finally:
                app.dependency_overrides.clear()

    def test_unsupported_model_clue_downgrades_advisory_without_losing_raw_label(self):
        from backend.app.diagnosis import build_diagnosis

        incident = Incident.model_validate_json((ROOT / "data/incidents/DEV-001.json").read_text())
        provider = MubitProvider("test-key", "gemini-3.8-flash", "https://api.mubit.ai/gemini")
        with patch("backend.app.provider.urlopen", return_value=GatewayResponse(answer("encoder/reporting fault"))):
            record = build_diagnosis(incident, provider)
        self.assertEqual(record.model_label, "encoder/reporting fault")
        self.assertEqual(record.diagnosis.cause_label, "unknown")
        self.assertEqual(record.diagnosis.uncertainty, "high")


if __name__ == "__main__":
    unittest.main()
