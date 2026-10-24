"""Protect the simulator-to-backend contract and synthetic outcome boundary."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import db, incidents, live_monitor
from backend.app.main import app, provider_dependency
from backend.app.provider import LocalFixtureProvider
from simulator.robot import Robot


class SimulatorIntakeTests(unittest.TestCase):
    def test_simulator_incident_uses_backend_contract_and_stays_synthetic(self):
        robot = Robot()
        packets = [robot.build_packet(), robot.build_packet()]
        self.assertTrue(all(packets))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_dir = root / "incidents"
            case_dir.mkdir()
            with patch.object(db, "DB_PATH", root / "records.sqlite3"), \
                 patch.object(incidents, "INCIDENT_DIR", case_dir), \
                 patch.object(live_monitor, "INCIDENT_DIR", case_dir):
                captured = live_monitor.build_incident(packets, "n20_fl")
                self.assertEqual(captured.source_type, "synthetic")
                self.assertTrue(all(reading.origin == "synthetic" for reading in captured.readings))
                self.assertTrue(any(reading.sensor == "n20_fl.rpm" for reading in captured.readings))
                self.assertEqual(captured.fault_codes, [])
                self.assertNotIn("jam", captured.model_dump_json().lower())
                (case_dir / f"{captured.id}.json").write_text(
                    captured.model_dump_json(), encoding="utf-8"
                )
                app.dependency_overrides[provider_dependency] = LocalFixtureProvider
                try:
                    with TestClient(app) as client:
                        response = client.post("/api/diagnose", json={"incident_id": captured.id})
                        self.assertEqual(response.status_code, 201, response.text)
                        result = response.json()
                        self.assertEqual(result["diagnosis"]["cause_label"], "unknown")
                        self.assertEqual(result["diagnosis"]["supporting_evidence"][0]["field"], "readings[0].value")
                        outcome = client.post("/api/confirm", json={
                            "diagnosis_id": result["id"],
                            "incident_id": captured.id,
                            "actual_cause": "wheel obstruction",
                            "fix_performed": "Cleared the injected jam in the simulator.",
                            "inspection_note": "Simulator state showed an injected jam.",
                            "verifier": "simulator operator",
                            "timestamp": "2026-10-24T12:00:00Z",
                        })
                        self.assertEqual(outcome.status_code, 200, outcome.text)
                        self.assertEqual(outcome.json()["verification_kind"], "synthetic_simulation")
                        self.assertEqual(client.get("/api/evaluation/confirmed").json()["groups"], [])
                finally:
                    app.dependency_overrides.clear()

    def test_missing_packet_time_cannot_be_made_up(self):
        robot = Robot()
        packet = robot.build_packet()
        packet.pop("ts")
        with self.assertRaises(ValueError):
            live_monitor.build_incident([packet], "n20_fl")

    def test_injected_label_is_saved_only_in_separate_answer_key(self):
        robot = Robot()
        first = robot.build_packet()
        second = {**robot.build_packet(), "seq": first["seq"] + 1,
                  "_ground_truth": {"active_faults": [{"component": "n20_fl", "fault": "jam"}]}}
        third = {**second, "seq": first["seq"] + 2}
        state = {"active_faults": [{"component": "n20_fl", "fault": "jam"}]}
        monitor = live_monitor.SimulatorLiveMonitor()
        packets = iter([first, second, third])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(live_monitor, "INCIDENT_DIR", root / "incidents"), \
                 patch.object(live_monitor, "CAPTURED_KEYS_DIR", root / "keys"), \
                 patch.object(live_monitor, "simulator_json",
                              side_effect=lambda path: state if path == "/api/state" else next(packets)):
                asyncio.run(monitor.poll())
                asyncio.run(monitor.poll())
                asyncio.run(monitor.poll())
            incident_path, = (root / "incidents").glob("*.json")
            key_path, = (root / "keys").glob("*.json")
            incident_text = incident_path.read_text(encoding="utf-8")
            self.assertNotIn("jam", incident_text.lower())
            self.assertNotIn("ground_truth", incident_text)
            self.assertEqual(json.loads(incident_text)["source_type"], "synthetic")
            self.assertEqual(json.loads(key_path.read_text(encoding="utf-8"))["injected_fault"], "jam")


if __name__ == "__main__":
    unittest.main()
