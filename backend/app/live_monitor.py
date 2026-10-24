"""Capture simulator fault telemetry as validated synthetic incidents."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from collections import deque
from datetime import datetime, timezone
from math import isfinite
from uuid import uuid4

from pydantic import ValidationError

from .schemas import Incident
from .settings import INCIDENT_DIR, SIMULATOR_URL


def simulator_json(path: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{SIMULATOR_URL}{path}", timeout=0.5) as response:
            value = json.load(response)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _readings(packets: list[dict], component: str) -> list[dict]:
    fields = {
        "power": {"battery_v": "V", "battery_current_a": "A", "rail_5v_v": "V"},
        "motor": {"rpm": "RPM", "target_rpm": "RPM", "pwm": "duty",
                  "current_a": "A", "temp_c": "degC"},
        "servo": {"actual_deg": "deg", "target_deg": "deg", "current_a": "A"},
    }
    readings = []
    for packet in packets:
        timestamp = packet.get("ts")
        if not isinstance(timestamp, str):
            continue
        sources = [("power", packet.get("power"), fields["power"])]
        if component.startswith("n20_"):
            motors = packet.get("motors")
            motor = next((item for item in motors if isinstance(item, dict)
                          and item.get("id") == component), None) if isinstance(motors, list) else None
            sources.append((component, motor, fields["motor"]))
        elif component == "servo_arm":
            sources.append((component, packet.get("servo"), fields["servo"]))
        for sensor, values, metrics in sources:
            if not isinstance(values, dict):
                continue
            for metric, unit in metrics.items():
                value = values.get(metric)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value):
                    readings.append({"sensor": f"{sensor}.{metric}", "value": value,
                                     "unit": unit, "origin": "synthetic", "time": timestamp})
    return readings


def build_incident(packets: list[dict], component: str, fault: str) -> Incident:
    if not packets or not component or not fault:
        raise ValueError("Simulator incident requires packets and a fault")
    latest = packets[-1]
    if latest.get("schema") != "robot.telemetry.v1":
        raise ValueError("Unsupported simulator packet schema")
    readings = _readings(packets, component)
    if not readings:
        raise ValueError("Simulator fault has no valid readings")
    code = f"SIM_{component}_{fault}".upper().replace("-", "_")
    action = "Simulator telemetry snapshot"
    if component.startswith("n20_"):
        motors = latest.get("motors")
        motor = next((item for item in motors if isinstance(item, dict)
                      and item.get("id") == component), None) if isinstance(motors, list) else None
        if motor:
            action = f"{component} target_rpm={motor.get('target_rpm', 'unknown')}"
    elif component == "servo_arm":
        servo = latest.get("servo")
        action = f"servo_arm target_deg={servo.get('target_deg', 'unknown')}" if isinstance(servo, dict) else action
    return Incident(
        schema_version="1.0",
        id=f"SIM-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}",
        robot_type=str(latest.get("robot_id") or "simulator"),
        time_window=f"{packets[0].get('ts', 'unknown')} to {latest.get('ts', 'unknown')}",
        commanded_action=action,
        readings=readings,
        fault_codes=[code],
        technician_note=f"Simulator reported {fault} on {component}; synthetic telemetry, not a physical inspection.",
        source_type="synthetic",
    )


class SimulatorLiveMonitor:
    def __init__(self) -> None:
        self.packets: deque[dict] = deque(maxlen=12)
        self.last_seq: tuple[object, object] | None = None
        self.recorded: set[tuple[str, str]] = set()
        self.online = False

    async def poll(self) -> None:
        state, packet = await asyncio.gather(
            asyncio.to_thread(simulator_json, "/api/state"),
            asyncio.to_thread(simulator_json, "/api/packet"),
        )
        self.online = state is not None and packet is not None and packet.get("schema") == "robot.telemetry.v1"
        if not self.online:
            return
        seq = (packet.get("boot_id"), packet.get("seq"))
        if seq != self.last_seq:
            if self.last_seq is not None and seq[0] != self.last_seq[0]:
                self.packets.clear()
                self.recorded.clear()
            self.packets.append(packet)
            self.last_seq = seq
        active = {
            (item.get("component"), item.get("fault"))
            for item in state.get("active_faults", []) if isinstance(item, dict)
            and isinstance(item.get("component"), str)
            and isinstance(item.get("fault"), str)
        }
        self.recorded.intersection_update(active)
        for component, fault in active - self.recorded:
            if len(self.packets) < 2:
                continue
            try:
                incident = build_incident(list(self.packets), component, fault)
            except (ValueError, TypeError, ValidationError):
                continue
            INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
            path = INCIDENT_DIR / f"{incident.id}.json"
            with path.open("x", encoding="utf-8") as output:
                output.write(incident.model_dump_json(indent=2) + "\n")
            self.recorded.add((component, fault))

    async def run(self) -> None:
        while True:
            try:
                await self.poll()
            except (OSError, ValueError, TypeError):
                self.online = False
            await asyncio.sleep(0.5)


live_monitor = SimulatorLiveMonitor()
