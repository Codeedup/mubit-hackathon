"""Fresh synthetic cases for a repeatable demo, without an external service."""

from datetime import datetime, timezone
from uuid import uuid4

from .schemas import Incident


SCENARIOS = {
    "stalled-wheel": ("Drive forward for 3 seconds", "The left wheel stopped while the command was active.",
                      [("left_wheel_speed", 0, "rpm"), ("left_motor_current", 1.8, "A")]),
    "low-voltage": ("Drive forward for 3 seconds", "Both motors failed to turn during the command.",
                    [("driver_supply", 4.1, "V"), ("wheel_speed", 0, "rpm")]),
    "encoder-mismatch": ("Rotate right for 2 seconds", "Wheel motion was observed in the simulation while the count stayed at zero.",
                         [("observed_wheel_motion", "rotating", "state"), ("reported_encoder_ticks", 0, "count")]),
    "incomplete-evidence": ("Drive forward for 3 seconds", "The robot stopped. No independent motion or current observation is available.",
                            [("commanded_speed", 150, "rpm")]),
}


def demo_incident(scenario: str) -> Incident:
    action, note, readings = SCENARIOS[scenario]
    now = datetime.now(timezone.utc)
    return Incident(
        schema_version="1.0", id=f"DEMO-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:6]}",
        robot_type="two-wheel rover (simulated)", time_window=now.isoformat(),
        commanded_action=action, technician_note=note, source_type="synthetic", fault_codes=[],
        readings=[{"sensor": sensor, "value": value, "unit": unit, "origin": "synthetic", "time": now}
                  for sensor, value, unit in readings],
    )
