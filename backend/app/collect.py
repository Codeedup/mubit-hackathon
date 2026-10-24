"""Prepare varied synthetic classifier cases; send only with an explicit call limit."""

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .diagnosis import build_diagnosis
from .provider import MubitProvider, ProviderFailure, ProviderResponse, ProviderTimeout, serialize_incident
from .schemas import Incident
from .settings import MUBIT_API_KEY, MUBIT_BASE_URL, MUBIT_MODEL, ROOT


LEDGER = ROOT / "data" / "collection" / "sent.local.jsonl"
ANSWER_KEYS = ROOT / "data" / "collection" / "answer_keys.local.json"
PRIOR_LIVE_ATTEMPTS = 2
MAX_LIVE_ATTEMPTS = 25
GROUP_LABELS = ("wheel obstruction", "motor power/driver path", "encoder/reporting fault", "unknown")


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


def read_ledger(path: Path | None = None) -> list[dict]:
    path = path or LEDGER
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_ledger(row: dict, path: Path | None = None) -> None:
    path = path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(row, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())


def write_answer_keys(cases: list[Incident], path: Path | None = None) -> None:
    path = path or ANSWER_KEYS
    expected = {case.id: GROUP_LABELS[index % 4] for index, case in enumerate(cases)}
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != expected:
            raise ValueError("Existing collection answer key differs; resolve it before sending")
        return
    with path.open("x", encoding="utf-8") as output:
        json.dump(expected, output, indent=2, sort_keys=True)
        output.write("\n")


class SingleResponseProvider:
    """Run the API parser and advisory without making a second live call."""

    def __init__(self, response: ProviderResponse):
        self.response = response

    def diagnose(self, _incident: Incident) -> ProviderResponse:
        return self.response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Make real Mubit calls")
    parser.add_argument("--limit", type=int, default=0, help="Maximum new calls in this run")
    parser.add_argument("--other-attempts", type=int,
                        help="Additional live diagnosis calls outside this CLI since the two baseline calls")
    parser.add_argument("--review-case", help="Record a console review observation for a collection case")
    parser.add_argument("--task-observed", help="Task name seen in the Mubit console")
    parser.add_argument("--reviewer-state", choices=("queued", "kept", "rejected", "unknown"),
                        help="Reviewer state seen in the Mubit console")
    args = parser.parse_args()
    if args.other_attempts is not None and args.other_attempts < 0:
        parser.error("--other-attempts cannot be negative")
    if args.send and args.other_attempts is None:
        parser.error("--send requires --other-attempts, including zero if none")
    cases = collection_cases()
    write_answer_keys(cases)
    events = read_ledger()
    attempted_ids = {row["incident_id"] for row in events if row.get("event") == "attempt" or
                     "event" not in row}  # Older successful rows remain protected.
    if args.review_case:
        if args.send or args.review_case not in attempted_ids or not args.task_observed or not args.reviewer_state:
            parser.error("review requires an attempted case, --task-observed and --reviewer-state, without --send")
        append_ledger({"event": "review", "incident_id": args.review_case,
                       "observed_at": datetime.now(timezone.utc).isoformat(),
                       "task_observed": args.task_observed, "reviewer_state": args.reviewer_state})
        print(json.dumps({"incident_id": args.review_case, "task_observed": args.task_observed,
                          "reviewer_state": args.reviewer_state}))
        return
    pending = [case for case in cases if case.id not in attempted_ids]
    remaining_budget = MAX_LIVE_ATTEMPTS - PRIOR_LIVE_ATTEMPTS - len(attempted_ids) - (args.other_attempts or 0)
    if not args.send:
        print(json.dumps({"prepared": len(cases), "attempted": len(attempted_ids),
                          "pending": len(pending), "remaining_budget": max(0, remaining_budget),
                          "sample_case_text": serialize_incident(cases[0])}, indent=2))
        return
    if args.limit < 1 or args.limit > remaining_budget:
        parser.error(f"--send requires --limit from 1 to {max(0, remaining_budget)}")
    if not MUBIT_API_KEY or not MUBIT_MODEL:
        parser.error("Set MUBIT_API_KEY and MUBIT_MODEL")
    provider = MubitProvider(MUBIT_API_KEY, MUBIT_MODEL, MUBIT_BASE_URL)
    for case in pending[:args.limit]:
        case_text = serialize_incident(case)
        base = {"incident_id": case.id, "input_hash": hashlib.sha256(case_text.encode()).hexdigest(),
                "call_timestamp": datetime.now(timezone.utc).isoformat(), "model_id": MUBIT_MODEL,
                "task_observed": None, "reviewer_state": "unverified", "diagnosis_saved": False}
        # Persist before sending so a crash or timeout cannot silently resend a case.
        append_ledger({**base, "event": "attempt"})
        start = time.perf_counter()
        response = None
        try:
            response = provider.diagnose(case)
            record = build_diagnosis(case, SingleResponseProvider(response))
            outcome = {"http_outcome": 200, "request_reference": record.request_reference,
                       "raw_reply": response.raw_response, "parsed_label": record.model_label,
                       "advisory_label": record.diagnosis.cause_label, "error": None}
        except (ProviderFailure, ProviderTimeout) as exc:
            outcome = {"http_outcome": (200 if response else exc.trace.get("http_status"))
                       if isinstance(exc, ProviderFailure) else None,
                       "request_reference": getattr(exc, "request_reference", "") or
                       (response.request_reference if response else ""),
                       "raw_reply": response.raw_response if response else None,
                       "parsed_label": None, "advisory_label": None, "error": str(exc)}
        row = {**base, **outcome, "event": "result", "latency_ms": round((time.perf_counter() - start) * 1000)}
        append_ledger(row)
        print(json.dumps(row))
        if row["error"]:
            break


if __name__ == "__main__":
    main()
