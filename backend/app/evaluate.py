"""Score stored diagnoses against separate synthetic answer keys.

This is case accuracy. It is unrelated to Mubit adapter/provider agreement.
"""

import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .db import initialize_database, list_diagnoses
from .schemas import KnownCause
from .settings import ROOT


class SyntheticKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str = Field(min_length=1)
    split: Literal["development", "held_out"]
    actual_cause: KnownCause
    rationale: str = Field(min_length=1)


class SyntheticKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    description: str
    cases: list[SyntheticKey]


def evaluate_synthetic(keys_path: Path, split: str, provider_kind: str) -> dict:
    keys = SyntheticKeys.model_validate_json(keys_path.read_text(encoding="utf-8"))
    selected = [key for key in keys.cases if key.split == split]
    if len({key.incident_id for key in selected}) != len(selected):
        raise ValueError("Duplicate incident IDs in synthetic answer keys")
    initialize_database()
    # Use the first prediction for a case. Later runs may have seen its saved
    # technician correction and must not improve an evaluation score.
    first = {}
    for record in reversed(list_diagnoses()):
        if record.incident_id not in first:
            first[record.incident_id] = record
    cases = []
    missing = []
    excluded_leaky = []
    for key in selected:
        record = first.get(key.incident_id)
        if record is None or record.provider_kind != provider_kind:
            missing.append(key.incident_id)
            continue
        if record.incident.source_type != "synthetic" or record.incident.fault_codes:
            excluded_leaky.append(key.incident_id)
            continue
        cases.append({
            "incident_id": key.incident_id,
            "diagnosis_id": record.id,
            "model_id": record.model_id,
            "predicted_cause": record.diagnosis.cause_label,
            "actual_cause": key.actual_cause,
            "matched": record.diagnosis.cause_label == key.actual_cause,
        })
    matched = sum(case["matched"] for case in cases)
    return {
        "source": "synthetic_answer_key",
        "split": split,
        "provider_kind": provider_kind,
        "selection_policy": "first_stored_diagnosis_per_incident_across_providers",
        "key_count": len(selected),
        "evaluated": len(cases),
        "matched": matched,
        "accuracy": matched / len(cases) if cases else None,
        "missing_incident_ids": missing,
        "excluded_leaky_incident_ids": excluded_leaky,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["development", "held_out"], required=True)
    parser.add_argument("--provider-kind", choices=["local_fixture", "mubit"], required=True)
    parser.add_argument(
        "--keys", type=Path,
        default=ROOT / "data/evaluation/answer_keys.synthetic.json",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_synthetic(args.keys, args.split, args.provider_kind), indent=2))


if __name__ == "__main__":
    main()
