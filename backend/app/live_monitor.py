"""Real-time simulator telemetry listener and automatic incident generator."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any

import websockets

from .schemas import Incident
from .settings import EVAL_DIR, INCIDENT_DIR, SIMULATOR_URL


def _extract_readings_from_packets(packets: list[dict[str, Any]], focus_motor: str) -> list[dict[str, Any]]:
    readings: list[dict[str, Any]] = []
    for pkt in packets:
        ts = str(pkt.get("ts") or datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"))
        origin = str(pkt.get("robot_id", "bot-01"))
        pwr = pkt.get("power", {})
        if pwr:
            readings.extend([
                {"ts": ts, "sensor": "power", "metric": "battery_v", "value": float(pwr.get("battery_v", 7.6)), "unit": "V", "origin": origin},
                {"ts": ts, "sensor": "power", "metric": "battery_current_a", "value": float(pwr.get("battery_current_a", 0.1)), "unit": "A", "origin": origin},
                {"ts": ts, "sensor": "power", "metric": "rail_5v_v", "value": float(pwr.get("rail_5v_v", 5.0)), "unit": "V", "origin": origin},
            ])
        for m in pkt.get("motors", []):
            if str(m.get("id")) == focus_motor:
                readings.extend([
                    {"ts": ts, "sensor": focus_motor, "metric": "rpm", "value": float(m.get("rpm", 0.0)), "unit": "RPM", "origin": origin},
                    {"ts": ts, "sensor": focus_motor, "metric": "target_rpm", "value": float(m.get("target_rpm", 0.0)), "unit": "RPM", "origin": origin},
                    {"ts": ts, "sensor": focus_motor, "metric": "pwm", "value": float(m.get("pwm", 0.0)), "unit": "duty", "origin": origin},
                    {"ts": ts, "sensor": focus_motor, "metric": "current_a", "value": float(m.get("current_a", 0.0)), "unit": "A", "origin": origin},
                    {"ts": ts, "sensor": focus_motor, "metric": "temp_c", "value": float(m.get("temp_c", 22.0)), "unit": "degC", "origin": origin},
                ])
        sv = pkt.get("servo", {})
        if sv:
            readings.extend([
                {"ts": ts, "sensor": "servo_arm", "metric": "actual_deg", "value": float(sv.get("actual_deg", 90.0)), "unit": "deg", "origin": origin},
                {"ts": ts, "sensor": "servo_arm", "metric": "target_deg", "value": float(sv.get("target_deg", 90.0)), "unit": "deg", "origin": origin},
                {"ts": ts, "sensor": "servo_arm", "metric": "current_a", "value": float(sv.get("current_a", 0.02)), "unit": "A", "origin": origin},
            ])
    return readings


def _build_symptom_metadata(
    comp: str,
    fault: str,
    last_pkt: dict[str, Any],
    focus_motor: str,
) -> tuple[str, list[str], str, str]:
    """
    Build (commanded_action, fault_codes, technician_note, expected_cause_label)
    from the live telemetry snapshot.
    """
    motors_by_id = {str(m.get("id")): m for m in last_pkt.get("motors", [])}
    m = motors_by_id.get(focus_motor, {})
    sv = last_pkt.get("servo", {})
    pwr = last_pkt.get("power", {})

    m_rpm = float(m.get("rpm", 0.0))
    m_tgt = float(m.get("target_rpm", 0.0))
    m_pwm = float(m.get("pwm", 0.0))
    m_curr = float(m.get("current_a", 0.0))
    m_temp = float(m.get("temp_c", 22.0))

    sv_act = float(sv.get("actual_deg", 90.0))
    sv_tgt = float(sv.get("target_deg", 90.0))
    sv_curr = float(sv.get("current_a", 0.02))

    batt_v = float(pwr.get("battery_v", 7.6))
    rail_v = float(pwr.get("rail_5v_v", 5.0))

    tag = focus_motor.upper()

    if comp.startswith("n20_"):
        cmd = f"{focus_motor}.set_target_rpm({m_tgt:.0f}) [mode={m.get('mode', 'pid')}, pwm={m_pwm:.2f}]"
        if fault == "jam":
            codes = [f"ERR_MTR_{tag}_STALL", f"WARN_HIGH_CURRENT_{tag}"]
            note = (
                f"Live telemetry anomaly on {focus_motor}: wheel stalled at {m_rpm:.1f} RPM while commanded to "
                f"{m_tgt:.0f} RPM (PWM={m_pwm:.2f}), drawing {m_curr:.2f}A stall current and heating to {m_temp:.1f}°C."
            )
            expected = f"motor.jam ({focus_motor} mechanical gearbox/wheel jam)"
        elif fault == "encoder_failure":
            codes = [f"ERR_ENC_{tag}_ZERO_TICKS", "WARN_PID_INTEGRAL_SAT"]
            note = (
                f"Live telemetry anomaly on {focus_motor}: encoder reports {m_rpm:.1f} RPM despite PWM saturating at "
                f"{m_pwm:.2f} (target {m_tgt:.0f} RPM) with {m_curr:.2f}A running current."
            )
            expected = f"motor.encoder_failure ({focus_motor} hall encoder pulse loss causing PI windup)"
        elif fault == "overheat":
            codes = [f"WARN_MTR_{tag}_THERMAL_RISE", f"WARN_BEARING_DRAG_{tag}"]
            note = (
                f"Live telemetry anomaly on {focus_motor}: winding temperature climbing rapidly ({m_temp:.1f}°C) "
                f"with elevated load current ({m_curr:.2f}A at {m_rpm:.0f} RPM)."
            )
            expected = f"motor.overheat ({focus_motor} degraded cooling and bearing friction thermal rise)"
        elif fault == "disconnected":
            codes = [f"ERR_MTR_{tag}_OPEN_CIRCUIT", f"WARN_ZERO_CURRENT_{tag}"]
            note = (
                f"Live telemetry anomaly on {focus_motor}: PWM driven to {m_pwm:.2f} (target {m_tgt:.0f} RPM), "
                f"but wheel speed is {m_rpm:.1f} RPM and current is {m_curr:.3f}A (open circuit)."
            )
            expected = f"motor.disconnected ({focus_motor} broken motor wire / open-circuit winding)"
        else:  # burned_out
            codes = [f"CRIT_MTR_{tag}_BURNED_OUT", "ERR_WINDING_OVERTEMP_115C"]
            note = (
                f"Critical hardware failure on {focus_motor}: winding exceeded 115°C ({m_temp:.1f}°C) and burned out; "
                f"motor now draws {m_curr:.3f}A at 0 RPM."
            )
            expected = f"motor.burned_out ({focus_motor} winding insulation failure above 115°C)"
    elif comp == "servo_arm":
        cmd = f"servo_arm.set_target({sv_tgt:.1f}) [trim={sv.get('trim_deg', 0.0):.1f}°]"
        if fault == "jam":
            codes = ["ERR_SERVO_STALL_BLOCKED", "WARN_SERVO_HIGH_CURRENT"]
            note = (
                f"Live telemetry anomaly on servo_arm: arm blocked at {sv_act:.1f}° vs target {sv_tgt:.1f}°, "
                f"drawing {sv_curr:.2f}A stall current."
            )
            expected = "servo.jam (servo_arm mechanically blocked away from target angle)"
        elif fault == "jitter":
            codes = ["WARN_SERVO_FEEDBACK_JITTER", "WARN_SERVO_OSC"]
            note = (
                f"Live telemetry anomaly on servo_arm: position feedback oscillating around {sv_act:.1f}° "
                f"(target {sv_tgt:.1f}°) with current spikes ({sv_curr:.2f}A)."
            )
            expected = "servo.jitter (servo_arm noisy position feedback causing oscillation and current spikes)"
        elif fault == "calibration_drift":
            codes = ["WARN_SERVO_POS_OFFSET"]
            note = (
                f"Live telemetry anomaly on servo_arm: arm settled at {sv_act:.1f}° instead of commanded {sv_tgt:.1f}° "
                f"(offset {sv_act - sv_tgt:+.1f}°) with normal holding current ({sv_curr:.2f}A)."
            )
            expected = "servo.calibration_drift (servo_arm feedback potentiometer offset)"
        else:  # signal_loss
            codes = ["ERR_SERVO_PWM_LOSS"]
            note = (
                f"Live telemetry anomaly on servo_arm: PWM pulse lost (pulse_us=0), servo current dropped to "
                f"{sv_curr:.3f}A, and arm sagged to {sv_act:.1f}°."
            )
            expected = "servo.signal_loss (servo_arm PWM control signal lost, arm sagging under load)"
    else:  # power
        cmd = f"power_distribution [batt={batt_v:.2f}V, rail_5v={rail_v:.2f}V]"
        if fault == "brownout":
            codes = ["CRIT_5V_RAIL_SAG", "WARN_MCU_BROWNOUT_RISK"]
            note = (
                f"Live power anomaly: 5V buck regulator rail sagged to {rail_v:.2f}V (below 4.25V MCU brownout "
                f"threshold) under 5V rail load."
            )
            expected = "power.brownout (weak 5V buck regulator sagging below 4.25V MCU reset threshold)"
        else:  # battery_aging
            codes = ["WARN_BATT_INTERNAL_RES_SAG", "WARN_BATT_VOLTAGE_SAG"]
            note = (
                f"Live power anomaly: 2S battery voltage sagged to {batt_v:.2f}V under { float(pwr.get('battery_current_a', 0.0)):.2f}A "
                f"load (elevated pack internal resistance)."
            )
            expected = "power.battery_aging (elevated 2S battery internal resistance causing heavy voltage sag)"

    return cmd, codes, note, expected


class SimulatorLiveMonitor:
    """Monitors the live simulator at SIMULATOR_URL and creates incidents in real time when faults occur."""

    def __init__(self) -> None:
        self.packet_history: deque[dict[str, Any]] = deque(maxlen=16)
        self.recorded_anomalies: set[tuple[str, str]] = set()
        self.pending_anomalies: dict[tuple[str, str], float] = {}
        self.last_sim_time: float = 0.0
        self.incident_seq: int = 0
        self.ws_client: Any = None
        self.online: bool = False

    def reset_tracking(self) -> None:
        self.recorded_anomalies.clear()
        self.pending_anomalies.clear()

    def _fetch_sim_state(self) -> dict[str, Any] | None:
        try:
            req = urllib.request.Request(f"{SIMULATOR_URL}/api/state", method="GET")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    async def _ws_listener_loop(self) -> None:
        ws_url = SIMULATOR_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/telemetry?name=robo-medic"
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    self.ws_client = ws
                    self.online = True
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            if data.get("type") == "telemetry":
                                self.packet_history.append(data)
                        except Exception:
                            pass
            except Exception:
                self.ws_client = None
                await asyncio.sleep(1.0)

    async def _detector_loop(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            state = await asyncio.to_thread(self._fetch_sim_state)
            if state is None:
                self.online = False
                continue
            self.online = True

            sim_t = float(state.get("t", 0.0))
            if sim_t < self.last_sim_time - 0.5:
                # Simulator was reset!
                self.reset_tracking()
            self.last_sim_time = sim_t

            # Gather all active anomalies in the simulator right now
            current_anomalies: set[tuple[str, str]] = set()
            for item in state.get("active_faults", []):
                comp = str(item.get("component", ""))
                fault = str(item.get("fault", ""))
                if comp and fault:
                    current_anomalies.add((comp, fault))

            # Also check pure physical anomalies caused by sliders without fault tags
            pwr = state.get("power", {})
            if float(pwr.get("soc_pct", 85.0)) < 15.0 or (
                float(pwr.get("battery_v", 7.6)) < 6.60 and ("power", "battery_aging") not in current_anomalies
            ):
                current_anomalies.add(("power", "battery_aging"))

            for m in state.get("motors", []):
                mid = str(m.get("id", ""))
                if not m.get("faults") and float(m.get("current_a", 0.0)) > 0.72 and abs(float(m.get("rpm", 0.0))) < 8.0 and abs(float(m.get("pwm", 0.0))) > 0.5:
                    current_anomalies.add((mid, "jam"))

            # Clear any recorded/pending anomalies that have been resolved in the simulator
            for resolved in list(self.recorded_anomalies):
                if resolved not in current_anomalies:
                    self.recorded_anomalies.discard(resolved)
            for resolved in list(self.pending_anomalies):
                if resolved not in current_anomalies:
                    self.pending_anomalies.pop(resolved, None)

            now = time.monotonic()
            for anomaly in current_anomalies:
                if anomaly in self.recorded_anomalies:
                    continue
                if anomaly not in self.pending_anomalies:
                    self.pending_anomalies[anomaly] = now
                    continue
                # Wait ~0.9s after anomaly onset so packet_history contains pre-fault + during-fault waveform samples
                if now - self.pending_anomalies[anomaly] >= 0.9 and len(self.packet_history) >= 2:
                    self.pending_anomalies.pop(anomaly, None)
                    self.recorded_anomalies.add(anomaly)
                    await self._emit_incident(anomaly[0], anomaly[1])

    async def _emit_incident(self, comp: str, fault: str) -> Incident:
        packets = list(self.packet_history)[-12:]
        focus_motor = comp if comp.startswith("n20_") else "n20_fl"
        readings = _extract_readings_from_packets(packets, focus_motor=focus_motor)
        last_pkt = packets[-1]
        first_ts = str(packets[0].get("ts", ""))
        last_ts = str(last_pkt.get("ts", ""))

        cmd, codes, note, expected_label = _build_symptom_metadata(comp, fault, last_pkt, focus_motor)

        existing = list(INCIDENT_DIR.glob("*.json")) if INCIDENT_DIR.exists() else []
        self.incident_seq = max(self.incident_seq + 1, len(existing) + 1)
        ts_short = datetime.now(timezone.utc).strftime("%H%M%S")
        inc_id = f"INC-{self.incident_seq:03d}-{comp}-{ts_short}"

        incident = Incident(
            id=inc_id,
            robot_type="bot-01 (Live Simulator Telemetry)",
            time_window=f"{first_ts} → {last_ts} ({len(packets)} frames)",
            commanded_action=cmd,
            readings=readings,
            fault_codes=codes,
            technician_note=note,
            source_type="measured",
        )
        INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = INCIDENT_DIR / f"{inc_id}.json"
        out_path.write_text(incident.model_dump_json(indent=2) + "\n", encoding="utf-8")

        # Update answer_keys.json in data/evaluation/ (kept strictly outside model input files)
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        ans_path = EVAL_DIR / "answer_keys.json"
        ans_data: dict[str, Any] = {}
        if ans_path.exists():
            try:
                ans_data = json.loads(ans_path.read_text(encoding="utf-8"))
            except Exception:
                ans_data = {}
        ans_data[inc_id] = {
            "expected_cause_label": expected_label,
            "expected_component": comp,
            "expected_fault": fault,
        }
        ans_path.write_text(json.dumps(ans_data, indent=2) + "\n", encoding="utf-8")

        # Send a note back to the simulator's Event Log if WS is connected
        if self.ws_client is not None:
            try:
                await self.ws_client.send(
                    json.dumps({
                        "type": "note",
                        "text": f"Robo Medic auto-captured incident {inc_id} ({ ', '.join(codes) })",
                    })
                )
            except Exception:
                pass
        return incident

    async def run(self) -> None:
        await asyncio.gather(self._ws_listener_loop(), self._detector_loop())


live_monitor = SimulatorLiveMonitor()
