"""
Protocol documentation: telemetry fields, commands, and faults.
"""

from __future__ import annotations
from typing import Any
from .robot import FAULT_INFO

FIELDS: dict[str, tuple[str, str, str]] = {
    "type": ("", "'telemetry'", "Message type."),
    "schema": ("", "robot.telemetry.v1", "Packet schema version."),
    "robot_id": ("", "bot-01", "Robot identifier."),
    "firmware": ("", "semver", "Firmware version."),
    "boot_id": ("", "increments", "Increments on reboot. Resets all trims/targets."),
    "seq": ("", "+1 per packet", "Packet sequence counter."),
    "ts": ("ISO-8601 UTC", "", "Timestamp."),
    "uptime_s": ("s", "", "Seconds since MCU boot."),
    "power.battery_v": ("V", "6.4 - 8.4", "2S Battery voltage (sags under load)."),
    "power.battery_current_a": ("A", "0.05 - 1.5", "Total battery current draw."),
    "power.rail_5v_v": ("V", "4.85 - 5.05", "5V regulator voltage (resets MCU if < 4.25V)."),
    "motors[].id": ("", "n20_fl|n20_fr|n20_rl|n20_rr", "Motor ID."),
    "motors[].pwm": ("-1..1", "", "Duty cycle applied."),
    "motors[].target_rpm": ("RPM", "-300..300", "Target RPM in pid mode."),
    "motors[].rpm": ("RPM", "", "Measured wheel RPM from encoder."),
    "motors[].current_a": ("A", "0.05 - 0.4", "Supply current. Stall is ~0.95A."),
    "motors[].temp_c": ("degC", "", "Motor winding temperature."),
    "servo.actual_deg": ("deg", "0..180", "Measured arm angle from potentiometer wire."),
    "servo.target_deg": ("deg", "0..180", "Commanded arm angle."),
    "servo.current_a": ("A", "0.01 - 0.35", "Servo current draw."),
}

COMMANDS: dict[str, Any] = {
    "format": {
        "type": "command",
        "target": "robot | all_motors | n20_fl | n20_fr | n20_rl | n20_rr | servo_arm",
        "action": "see actions",
        "value": "optional numeric/string value",
        "reason": "optional note",
    },
    "actions": {
        "robot": ["estop", "resume", "reboot"],
        "motor": ["set_target_rpm", "set_pwm", "set_current_limit", "enable", "disable", "stop"],
        "servo": ["set_target", "set_trim", "set_speed_limit", "attach", "detach", "reattach"],
    },
}

def schema() -> dict[str, Any]:
    return {
        "schema": "robot.telemetry.v1",
        "fields": {k: {"unit": u, "normal": n, "description": d} for k, (u, n, d) in FIELDS.items()},
        "commands": COMMANDS,
        "faults": FAULT_INFO,
    }
