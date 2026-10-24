import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import db, incidents
from backend.app.evaluate import SyntheticKeys, evaluate_synthetic
from backend.app.main import app, provider_dependency
from backend.app.provider import (
    LocalFixtureProvider, ProviderResponse, ProviderTimeout, UnavailableProvider,
)
from backend.app.schemas import Incident


ROOT = Path(__file__).resolve().parents[2]


class BackendFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary.name)
        incident_dir = temporary_path / "incidents"
        incident_dir.mkdir()
        shutil.copy(ROOT / "data/incidents/DEV-001.json", incident_dir / "DEV-001.json")
        inspected = json.loads((ROOT / "data/incidents/DEV-001.json").read_text())
        inspected["id"] = "INSPECTED-001"
        inspected["source_type"] = "measured"
        for reading in inspected["readings"]:
            reading["origin"] = "measured"
        (incident_dir / "INSPECTED-001.json").write_text(json.dumps(inspected))
        self.db_patch = patch.object(db, "DB_PATH", temporary_path / "robo_medic.sqlite3")
        self.incident_patch = patch.object(incidents, "INCIDENT_DIR", incident_dir)
        self.db_patch.start()
        self.incident_patch.start()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.incident_patch.stop()
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_contract_rejects_incomplete_and_unlabelled_readings(self):
        data = json.loads((ROOT / "data/incidents/DEV-001.json").read_text())
        del data["readings"][0]["unit"]
        with self.assertRaises(ValidationError):
            Incident.model_validate(data)
        data["readings"][0]["unit"] = "rpm"
        data["readings"][0]["time"] = "2026-10-24T09:00:00"
        with self.assertRaises(ValidationError):
            Incident.model_validate(data)
        data["readings"][0]["time"] = "2026-10-24T09:00:00Z"
        data["readings"][0]["origin"] = "measured"
        with self.assertRaises(ValidationError):
            Incident.model_validate(data)

    def test_all_synthetic_cases_have_separate_unique_keys(self):
        cases = [
            Incident.model_validate_json(path.read_text(encoding="utf-8"))
            for path in (ROOT / "data/incidents").glob("*.json")
        ]
        keys = SyntheticKeys.model_validate_json(
            (ROOT / "data/evaluation/answer_keys.synthetic.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(cases), 11)
        self.assertEqual({case.id for case in cases}, {key.incident_id for key in keys.cases})
        self.assertEqual(sum(key.split == "held_out" for key in keys.cases), 8)
        self.assertTrue(all(case.source_type == "synthetic" for case in cases))

    def test_diagnose_confirm_history_and_restart(self):
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        with TestClient(app) as client:
            for _ in range(2):
                result = client.post("/api/diagnose", json={"incident_id": "INSPECTED-001"})
                self.assertEqual(result.status_code, 201, result.text)
                diagnosis = result.json()
                self.assertEqual(diagnosis["provider_kind"], "local_fixture")
                self.assertTrue(diagnosis["request_reference"].startswith("local-fixture:"))
                self.assertEqual(
                    client.get(f"/api/diagnoses/{diagnosis['id']}").json(), diagnosis
                )
                confirmation = client.post("/api/confirm", json={
                    "diagnosis_id": diagnosis["id"],
                    "incident_id": "INSPECTED-001",
                    "actual_cause": "wheel obstruction",
                    "fix_performed": "Removed the simulated obstruction.",
                    "inspection_note": "Inspected the simulated left wheel and found a blockage.",
                    "verifier": "test technician",
                    "timestamp": "2026-10-24T12:00:00Z",
                })
                self.assertEqual(confirmation.status_code, 200, confirmation.text)
            history = client.get("/api/repairs").json()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["predicted_cause"], "wheel obstruction")
            self.assertEqual(history[0]["verification_kind"], "inspection")
            self.assertTrue(history[0]["matched"])
            evaluation = client.get("/api/evaluation/confirmed").json()["groups"][0]
            self.assertEqual((evaluation["total"], evaluation["matched"]), (1, 1))
            self.assertEqual(evaluation["confirmed_diagnosis_count"], 2)
            self.assertEqual(client.get("/api/metrics").json()["diagnosis_count"], 2)
        with TestClient(app) as restarted:
            self.assertEqual(len(restarted.get("/api/diagnoses").json()), 2)
            self.assertEqual(len(restarted.get("/api/repairs").json()), 2)

    def test_provider_errors_and_invalid_citations_do_not_save(self):
        class TimedOut:
            def diagnose(self, _incident):
                raise ProviderTimeout()

        class Invalid:
            def __init__(self, raw_response):
                self.raw_response = raw_response

            def diagnose(self, _incident):
                return ProviderResponse(
                    self.raw_response, "example-request", "example-model", "local_fixture"
                )

        with TestClient(app) as client:
            for provider, status in [
                (UnavailableProvider(), 503),
                (TimedOut(), 504),
                (Invalid("not JSON"), 502),
                (Invalid(json.dumps({
                    "cause_label": "unknown",
                    "supporting_evidence": [{"field": "readings[99].value", "explanation": "bad"}],
                    "alternative": "wheel obstruction",
                    "next_check": "Inspect wheel movement.",
                    "uncertainty": "high",
                })), 502),
            ]:
                app.dependency_overrides[provider_dependency] = lambda p=provider: p
                response = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
                self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(client.get("/api/metrics").json()["diagnosis_count"], 0)

    def test_synthetic_keys_are_separate_from_confirmed_accuracy(self):
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        with TestClient(app) as client:
            response = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
            self.assertEqual(response.status_code, 201)
            simulation = client.post("/api/confirm", json={
                "diagnosis_id": response.json()["id"],
                "incident_id": "DEV-001",
                "actual_cause": "wheel obstruction",
                "fix_performed": "Removed a simulated blockage.",
                "inspection_note": "Simulated inspection found an obstruction.",
                "verifier": "test technician",
                "timestamp": "2026-10-24T12:00:00Z",
            })
            self.assertEqual(simulation.status_code, 200)
            self.assertEqual(simulation.json()["verification_kind"], "synthetic_simulation")
            self.assertEqual(client.get("/api/evaluation/confirmed").json()["groups"], [])
        keys = ROOT / "data/evaluation/answer_keys.synthetic.json"
        development = evaluate_synthetic(keys, "development", "local_fixture")
        held_out = evaluate_synthetic(keys, "held_out", "local_fixture")
        self.assertEqual((development["key_count"], development["evaluated"]), (3, 1))
        self.assertEqual((held_out["key_count"], held_out["evaluated"]), (8, 0))
        self.assertIsNone(held_out["accuracy"])

    def test_confirmation_requires_inspection_and_reports_mismatch(self):
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        with TestClient(app) as client:
            diagnosis = client.post(
                "/api/diagnose", json={"incident_id": "INSPECTED-001"}
            ).json()
            request = {
                "diagnosis_id": diagnosis["id"],
                "incident_id": "INSPECTED-001",
                "actual_cause": "motor power/driver path",
                "fix_performed": "Replaced a simulated driver lead.",
                "verifier": "test technician",
                "timestamp": "2026-10-24T12:00:00Z",
            }
            self.assertEqual(client.post("/api/confirm", json=request).status_code, 422)
            request["inspection_note"] = "Inspected the simulated driver lead and found it open."
            self.assertEqual(client.post("/api/confirm", json=request).status_code, 200)
            self.assertEqual(client.post("/api/confirm", json=request).status_code, 409)
            self.assertEqual(
                client.get(f"/api/diagnoses/{diagnosis['id']}").json()["diagnosis"],
                diagnosis["diagnosis"],
            )
            self.assertFalse(client.get("/api/repairs").json()[0]["matched"])
            group = client.get("/api/evaluation/confirmed").json()["groups"][0]
            self.assertEqual((group["total"], group["matched"], group["accuracy"]), (1, 0, 0.0))


if __name__ == "__main__":
    unittest.main()
