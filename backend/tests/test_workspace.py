"""Import, replay, and external-feedback boundaries for the local product."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from backend.app import db, incidents, mubit, settings
from backend.app.main import app, provider_dependency
from backend.app.provider import LocalFixtureProvider, ProviderFailure, ProviderResponse, serialize_incident


ROOT = Path(__file__).resolve().parents[2]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        directory = root / "incidents"
        directory.mkdir()
        self.incident = json.loads((ROOT / "data/incidents/DEV-001.json").read_text())
        (directory / "DEV-001.json").write_text(json.dumps(self.incident))
        for target, name, value in [
            (db, "DB_PATH", root / "test.sqlite3"), (incidents, "INCIDENT_DIR", directory),
            (settings, "MUBIT_PROJECT_ID", "prj_test"),
            (settings, "MUBIT_MANAGEMENT_KEY", "test-management-key"),
        ]:
            context = patch.object(target, name, value)
            context.start()
            self.addCleanup(context.stop)
        monitor = patch("backend.app.main.live_monitor.run", new=AsyncMock())
        monitor.start()
        self.addCleanup(monitor.stop)
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        self.addCleanup(app.dependency_overrides.clear)
        self.client = self.enterContext(TestClient(app))

    def confirm(self, record):
        response = self.client.post("/api/confirm", json={
            "diagnosis_id": record["id"], "incident_id": record["incident_id"],
            "actual_cause": "motor power/driver path", "fix_performed": "Checked the synthetic wiring.",
            "inspection_note": "The simulator confirmed a disconnected wire.",
            "verifier": "test technician", "timestamp": "2026-11-24T12:00:00Z",
        })
        self.assertEqual(response.status_code, 200, response.text)

    def test_import_is_immutable_bounded_and_keeps_source_labels(self):
        example = {**self.incident, "id": "IMPORT-test"}
        self.assertEqual(self.client.post("/api/incidents", json=example).status_code, 201)
        self.assertEqual(self.client.post("/api/incidents", json=example).status_code, 409)
        for invalid in [
            {**example, "id": "../outside"},
            {**example, "id": "measured-case", "source_type": "measured"},
        ]:
            self.assertEqual(self.client.post("/api/incidents", json=invalid).status_code, 422)
        self.assertEqual(self.client.post("/api/incidents", content=b"x" * (2 * 1024 * 1024 + 1)).status_code, 413)
        self.assertEqual(len(self.client.get("/api/incidents").json()), 2)

    def test_foreign_browser_origins_and_dns_rebinding_cannot_write(self):
        self.assertEqual(self.client.post("/api/demo/stalled-wheel", headers={"Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"Host": "other.example"}).status_code, 400)
        self.assertEqual(self.client.post("/api/demo/stalled-wheel", headers={"Origin": "http://testserver"}).status_code, 201)

    def test_request_replay_makes_one_provider_attempt_even_after_failure(self):
        provider = Mock(wraps=LocalFixtureProvider())
        app.dependency_overrides[provider_dependency] = lambda: provider
        payload = {"incident_id": "DEV-001", "request_id": "same-click"}
        first = self.client.post("/api/diagnose", json=payload)
        second = self.client.post("/api/diagnose", json=payload)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(provider.diagnose.call_count, 1)
        provider.diagnose.side_effect = ProviderFailure("uncertain external failure")
        failed = {**payload, "request_id": "failed-click"}
        self.assertEqual(self.client.post("/api/diagnose", json=failed).status_code, 502)
        self.assertEqual(self.client.post("/api/diagnose", json=failed).status_code, 409)
        self.assertEqual(provider.diagnose.call_count, 2)

    def test_demo_export_and_saved_outcomes_survive_reloading(self):
        demo = self.client.post("/api/demo/incomplete-evidence").json()
        self.assertEqual(demo["source_type"], "synthetic")
        self.assertEqual(demo["fault_codes"], [])
        record = self.client.post("/api/diagnose", json={"incident_id": "DEV-001"}).json()
        self.confirm(record)
        exported = self.client.get("/api/export")
        self.assertIn("attachment", exported.headers["content-disposition"])
        result = exported.json()
        self.assertEqual(result["diagnoses"][0]["diagnosis"]["cause_label"], "wheel obstruction")
        self.assertEqual(result["outcomes"][0]["actual_cause"], "motor power/driver path")
        self.assertNotIn("test-management-key", exported.text)
        self.assertEqual(len(self.client.get("/api/repairs").json()), 1)

    def test_feedback_checks_the_exact_call_and_preserves_external_acknowledgement(self):
        provider = Mock()
        provider.diagnose.return_value = ProviderResponse("wheel obstruction", "mreq_test", "test-model", "mubit")
        app.dependency_overrides[provider_dependency] = lambda: provider
        record = self.client.post("/api/diagnose", json={"incident_id": "DEV-001"}).json()
        endpoint = f"/api/diagnoses/{record['id']}/feedback"
        self.assertEqual(self.client.post(endpoint, json={"call_id": "call_test"}).status_code, 409)
        self.confirm(record)
        with patch.object(mubit, "management_request", return_value={"id": "call_wrong", "project": "prj_other"}) as gateway:
            rejected = self.client.post(endpoint, json={"call_id": "call_wrong"})
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(gateway.call_count, 1)  # No external POST.
        incident = incidents.get_incident("DEV-001")
        call = {"id": "call_test", "project": "prj_test",
                "request": {"contents": [{"parts": [{"text": serialize_incident(incident)}]}]},
                "response": {"content": "wheel obstruction"}}
        with patch.object(mubit, "management_request", side_effect=[call, {"id": "fb_test", "call_id": "call_test", "rating": "down"}]) as gateway:
            accepted = self.client.post(endpoint, json={"call_id": "call_test"})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["feedback_id"], "fb_test")
            self.assertEqual(gateway.call_args.args[1]["correction"], "motor power/driver path")
            self.assertEqual(gateway.call_args.kwargs["key"], f"robo-medic-{record['id']}")
            self.assertEqual(self.client.post(endpoint, json={"call_id": "call_test"}).json(), accepted.json())
            self.assertEqual(gateway.call_count, 2)  # Retry is a local read.

    def test_blank_or_mismatched_console_content_never_receives_feedback(self):
        provider = Mock()
        provider.diagnose.return_value = ProviderResponse("wheel obstruction", "mreq_test", "test-model", "mubit")
        app.dependency_overrides[provider_dependency] = lambda: provider
        record = self.client.post("/api/diagnose", json={"incident_id": "DEV-001"}).json()
        self.confirm(record)
        with patch.object(mubit, "management_request", return_value={"id": "call_test", "project": "prj_test", "request": {}, "response": None}) as gateway:
            self.assertEqual(self.client.post(f"/api/diagnoses/{record['id']}/feedback", json={"call_id": "call_test"}).status_code, 409)
            self.assertEqual(gateway.call_count, 1)

    def test_management_http_contract_and_live_status_do_not_expose_keys(self):
        class Reply(io.BytesIO):
            pass
        with patch("backend.app.mubit.urlopen", return_value=Reply(b'{"id":"fb_test"}')) as send:
            mubit.management_request("calls/call_test/feedback", {"rating": "down"}, key="replay-key")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.mubit.ai/api/v1/calls/call_test/feedback")
            self.assertEqual(request.get_header("Idempotency-key"), "replay-key")
            self.assertEqual(json.loads(request.data), {"rating": "down"})
        with patch.object(settings, "MUBIT_TASK_ID", "task_test"), patch.object(mubit, "management_request", side_effect=[
            {"id": "task_test", "name": "Classifier", "project": "prj_test", "stage": "collecting", "rows_count": 31, "active_version": None},
            {"data": []},
        ]):
            status = self.client.get("/api/mubit/status")
            self.assertEqual(status.json()["task"]["rows_count"], 31)
            self.assertEqual(status.json()["versions"], [])
            self.assertNotIn("test-management-key", status.text)


if __name__ == "__main__":
    unittest.main()
