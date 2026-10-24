"""Prepare varied synthetic classifier cases; send only with an explicit call limit."""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .diagnosis import build_diagnosis
from .provider import MubitProvider, ProviderFailure, ProviderTimeout, serialize_incident
from .schemas import Incident
from .settings import MUBIT_API_KEY, MUBIT_BASE_URL, MUBIT_MODEL, ROOT


LEDGER = ROOT / "data" / "collection" / "sent.local.jsonl"


def collection_cases() -> list[Incident]:
    cases = []
    start = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
    actions = ("Drive forward", "Drive backward", "Rotate left", "Rotate right")
    for variant in range(10):
        for group in ("wheel", "driver", "reporting", "unclear"):
            timestamp = start + timedelta(minutes=len(cases) * 3)
            at = timestamp.isoformat().replace("+00:00", "Z")
            side = ("left", "right")[variant % 2]
            if group == "wheel":
                readings = [
                    (f"{side}_wheel_speed", 0, "rpm"),
                    (f"{side}_motor_current", round(1.3 + variant * 0.11, 2), "A"),
                ]
                note = f"{side.title()} wheel did not turn during the command; current rose."
            elif group == "driver":
                readings = [
                    ("driver_supply", round(3.6 + variant * 0.09, 2), "V"),
                    (f"{side}_wheel_speed", 0, "rpm"),
                ]
                note = "No movement followed the drive command; supply reading was low."
            elif group == "reporting":
                readings = [
                    ("observed_wheel_motion", ("moving", "rotating")[variant % 2], "state"),
                    ("reported_encoder_ticks", variant % 2, "count"),
                ]
                note = "Independent motion observation disagreed with the reported count."
            else:
                readings = [
                    ("battery_charge", 50 + variant * 3, "%"),
                    ("ambient_temperature", 18 + variant, "C"),
                ]
                note = "Operator noticed a brief hesitation; no motor or motion measurement is available."
            cases.append(Incident.model_validate({
                "schema_version": "1.0",
                "id": f"COLLECT-{len(cases)+1:03d}",
                "robot_type": ("two-wheel rover", "four-wheel inspection rover")[variant % 2] + " (simulated)",
                "time_window": f"{at} to {(timestamp + timedelta(seconds=3)).isoformat().replace('+00:00', 'Z')}",
                "commanded_action": f"{actions[variant % 4]} for {2 + variant % 3} seconds",
                "readings": [
                    {"sensor": sensor, "value": value, "unit": unit, "origin": "synthetic", "time": at}
                    for sensor, value, unit in readings
                ],
                "fault_codes": [],
                "technician_note": note,
                "source_type": "synthetic",
            }))
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Make real Mubit calls")
    parser.add_argument("--limit", type=int, default=0, help="Maximum new calls in this run, 1 to 25")
    args = parser.parse_args()
    cases = collection_cases()
    sent = {}
    if LEDGER.exists():
        sent = {row["incident_id"]: row for row in
                (json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines())}
    pending = [case for case in cases if case.id not in sent]
    if not args.send:
        print(json.dumps({"prepared": len(cases), "previously_sent": len(sent),
                          "pending": len(pending), "sample_case_text": serialize_incident(cases[0])}, indent=2))
        return
    if not 1 <= args.limit <= 25:
        parser.error("--send requires --limit from 1 to 25")
    if not MUBIT_API_KEY or not MUBIT_MODEL:
        parser.error("Set MUBIT_API_KEY and MUBIT_MODEL")
    provider = MubitProvider(MUBIT_API_KEY, MUBIT_MODEL, MUBIT_BASE_URL)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    for case in pending[:args.limit]:
        try:
            record = build_diagnosis(case, provider)
        except (ProviderFailure, ProviderTimeout) as exc:
            print(json.dumps({"stopped_at": case.id, "error": str(exc),
                              "request_reference": getattr(exc, "request_reference", "")}))
            break
        row = {"incident_id": case.id, "request_reference": record.request_reference,
               "model_label": record.model_label, "advisory_label": record.diagnosis.cause_label}
        with LEDGER.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(row) + "\n")
        print(json.dumps(row))


if __name__ == "__main__":
    main()
