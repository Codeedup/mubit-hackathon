"""Focused checks for evidence gating and durable outcome integrity."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import db, incidents
from backend.app.evaluate import evaluate_synthetic
from backend.app.main import app, provider_dependency
from backend.app.provider import LocalFixtureProvider, ProviderResponse


ROOT = Path(__file__).resolve().parents[2]


class BackendSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary.name)
        incident_dir = temporary_path / "incidents"
        incident_dir.mkdir()
        example = json.loads((ROOT / "data/incidents/DEV-001.json").read_text(encoding="utf-8"))
        (incident_dir / "DEV-001.json").write_text(json.dumps(example), encoding="utf-8")
        physical = {**example, "id": "INSPECTED-001", "source_type": "measured"}
        physical["readings"] = [{**reading, "origin": "measured"} for reading in example["readings"]]
        (incident_dir / "INSPECTED-001.json").write_text(json.dumps(physical), encoding="utf-8")
        self.db_patch = patch.object(db, "DB_PATH", temporary_path / "robo_medic.sqlite3")
        self.incident_patch = patch.object(incidents, "INCIDENT_DIR", incident_dir)
        self.db_patch.start()
        self.incident_patch.start()

    def tearDown(self):
        app.dependency_overrides.clear()
        self.incident_patch.stop()
        self.db_patch.stop()
        self.temporary.cleanup()

    def test_provider_cannot_save_citation_to_missing_evidence(self):
        class BadProvider:
            def diagnose(self, _incident):
                return ProviderResponse(json.dumps({
                    "cause_label": "unknown",
                    "supporting_evidence": [{
                        "field": "readings[99].value", "explanation": "This reading does not exist."
                    }],
                    "alternative": "wheel obstruction",
                    "next_check": "Inspect the wheel.",
                    "uncertainty": "high",
                }), "example-request", "example-model", "local_fixture")

        app.dependency_overrides[provider_dependency] = BadProvider
        with TestClient(app) as client:
            self.assertEqual(
                client.post("/api/diagnose", json={"incident_id": "DEV-001"}).status_code,
                502,
            )
            self.assertEqual(client.get("/api/diagnoses").json(), [])

    def test_outcomes_persist_and_synthetic_cases_stay_out_of_verified_accuracy(self):
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        with TestClient(app) as client:
            physical_ids = [
                client.post("/api/diagnose", json={"incident_id": "INSPECTED-001"}).json()["id"]
                for _ in range(2)
            ]
            synthetic_id = client.post(
                "/api/diagnose", json={"incident_id": "DEV-001"}
            ).json()["id"]

            def confirm(diagnosis_id, incident_id, actual_cause):
                return client.post("/api/confirm", json={
                    "diagnosis_id": diagnosis_id,
                    "incident_id": incident_id,
                    "actual_cause": actual_cause,
                    "fix_performed": "Repaired the case fixture.",
                    "inspection_note": "Inspected the case fixture and recorded the cause.",
                    "verifier": "test technician",
                    "timestamp": "2026-10-24T12:00:00Z",
                })

            self.assertEqual(confirm(physical_ids[0], "INSPECTED-001", "wheel obstruction").status_code, 200)
            self.assertEqual(confirm(physical_ids[1], "INSPECTED-001", "motor power/driver path").status_code, 200)
            simulation = confirm(synthetic_id, "DEV-001", "wheel obstruction")
            self.assertEqual(simulation.json()["verification_kind"], "synthetic_simulation")
            self.assertEqual(len(client.get("/api/repairs").json()), 3)
            metrics = client.get("/api/metrics").json()
            self.assertEqual(metrics["confirmation_count"], 3)
            group = client.get("/api/evaluation/confirmed").json()["groups"][0]
            self.assertEqual((group["total"], group["confirmed_diagnosis_count"]), (1, 2))
            self.assertEqual((group["matched"], group["accuracy"]), (0, 0.0))
            self.assertEqual(
                client.get(f"/api/diagnoses/{physical_ids[1]}").json()["diagnosis"]["cause_label"],
                "wheel obstruction",
            )

        with TestClient(app) as restarted:
            self.assertEqual(len(restarted.get("/api/repairs").json()), 3)

    def test_synthetic_score_uses_prediction_before_saved_correction(self):
        class CorrectedProvider:
            def diagnose(self, _incident):
                return ProviderResponse(json.dumps({
                    "cause_label": "motor power/driver path",
                    "supporting_evidence": [{"field": "readings[0].value", "explanation": "Current reading."}],
                    "alternative": "wheel obstruction",
                    "next_check": "Inspect the driver supply.",
                    "uncertainty": "medium",
                }), "later-request", "local-rule-fixture-v1", "local_fixture")

        keys_path = Path(self.temporary.name) / "keys.json"
        keys_path.write_text(json.dumps({
            "schema_version": "1.0", "description": "Evaluation boundary fixture",
            "cases": [{"incident_id": "DEV-001", "split": "held_out",
                       "actual_cause": "motor power/driver path", "rationale": "Test correction leakage."}],
        }), encoding="utf-8")
        with TestClient(app) as client:
            app.dependency_overrides[provider_dependency] = LocalFixtureProvider
            first = client.post("/api/diagnose", json={"incident_id": "DEV-001"}).json()
            client.post("/api/confirm", json={
                "diagnosis_id": first["id"], "incident_id": "DEV-001",
                "actual_cause": "motor power/driver path", "fix_performed": "Checked wiring.",
                "inspection_note": "Synthetic answer revealed the cause.",
                "verifier": "test operator", "timestamp": "2026-10-24T12:00:00Z",
            })
            app.dependency_overrides[provider_dependency] = CorrectedProvider
            later = client.post("/api/diagnose", json={"incident_id": "DEV-001"}).json()
            self.assertEqual(later["diagnosis"]["cause_label"], "motor power/driver path")
            score = evaluate_synthetic(keys_path, "held_out", "local_fixture")
            self.assertEqual(score["cases"][0]["diagnosis_id"], first["id"])
            self.assertEqual(score["matched"], 0)

    def test_synthetic_score_excludes_legacy_label_codes(self):
        incident_path = Path(self.temporary.name) / "incidents" / "DEV-001.json"
        incident = json.loads(incident_path.read_text(encoding="utf-8"))
        incident["fault_codes"] = ["SIM_N20_FL_JAM"]
        incident_path.write_text(json.dumps(incident), encoding="utf-8")
        keys_path = Path(self.temporary.name) / "keys.json"
        keys_path.write_text(json.dumps({
            "schema_version": "1.0", "description": "Leakage boundary fixture",
            "cases": [{"incident_id": "DEV-001", "split": "held_out",
                       "actual_cause": "wheel obstruction", "rationale": "Injected test fault."}],
        }), encoding="utf-8")
        app.dependency_overrides[provider_dependency] = LocalFixtureProvider
        with TestClient(app) as client:
            response = client.post("/api/diagnose", json={"incident_id": "DEV-001"})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["diagnosis"]["supporting_evidence"][0]["field"], "readings[1].value")
            score = evaluate_synthetic(keys_path, "held_out", "local_fixture")
            self.assertEqual(score["evaluated"], 0)
            self.assertEqual(score["excluded_leaky_incident_ids"], ["DEV-001"])


if __name__ == "__main__":
    unittest.main()
