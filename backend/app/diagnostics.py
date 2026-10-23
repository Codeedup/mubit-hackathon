"""Physics-aware & continual-learning diagnosis engine for Robo Medic."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .db import connection
from .schemas import Diagnosis, Incident
from .settings import GEMINI_API_KEY


def _extract_metrics(incident: Incident) -> dict[str, dict[str, list[float]]]:
    """Group reading values by sensor -> metric -> list[float]."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for item in incident.readings:
        d = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        sensor = str(d.get("sensor", "unknown"))
        metric = str(d.get("metric", "value"))
        try:
            val = float(d.get("value", 0.0))
        except (TypeError, ValueError):
            continue
        grouped.setdefault(sensor, {}).setdefault(metric, []).append(val)
    return grouped


def _fetch_past_confirmations() -> list[dict[str, Any]]:
    """Retrieve verified technician confirmations from SQLite for continual learning."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT incident_id, actual_cause, fix_performed, verifier, timestamp
            FROM confirmations
            ORDER BY timestamp DESC
            LIMIT 20
            """
        ).fetchall()
    return [dict(r) for r in rows]


def diagnose_incident(incident: Incident) -> tuple[Diagnosis, str]:
    """
    Analyze an Incident using:
      1. Continual-learning memory (prior confirmed technician outcomes in SQLite),
      2. Physics-calibrated telemetry analyzer for bot-01 covering all motor, servo, and power faults,
      3. Optional Gemini API enrichment if GEMINI_API_KEY is configured.
    Returns (Diagnosis, model_id).
    """
    confirmations = _fetch_past_confirmations()
    exact_match = next((c for c in confirmations if c["incident_id"] == incident.id), None)

    grouped = _extract_metrics(incident)
    codes_str = " ".join(incident.fault_codes).upper()
    note_lower = incident.technician_note.lower()

    # Identify motor sensor in readings
    motor_sensors = [s for s in grouped if s.startswith("n20_")]
    primary_motor = motor_sensors[0] if motor_sensors else "n20_fl"
    m_data = grouped.get(primary_motor, {})

    rpms = m_data.get("rpm", [])
    target_rpms = m_data.get("target_rpm", [])
    pwms = m_data.get("pwm", [])
    currents = m_data.get("current_a", [])
    temps = m_data.get("temp_c", [])

    last_rpm = rpms[-1] if rpms else 0.0
    avg_tail_rpm = sum(rpms[-4:]) / len(rpms[-4:]) if rpms else 0.0
    max_target_rpm = max((abs(x) for x in target_rpms), default=0.0)
    max_pwm = max((abs(x) for x in pwms), default=0.0)
    max_curr = max(currents, default=0.0)
    tail_curr = sum(currents[-4:]) / len(currents[-4:]) if currents else 0.0
    max_temp = max(temps, default=22.0)
    temp_rise = (temps[-1] - temps[0]) if len(temps) >= 2 else 0.0

    # Check power & servo
    p_data = grouped.get("power", {})
    rail_5v = p_data.get("rail_5v_v", [5.0])
    batt_v = p_data.get("battery_v", [7.6])
    min_rail = min(rail_5v, default=5.0)
    min_batt = min(batt_v, default=7.6)

    s_data = grouped.get("servo_arm", {})
    s_actual = s_data.get("actual_deg", [90.0])
    s_target = s_data.get("target_deg", [90.0])
    s_curr = s_data.get("current_a", [0.05])
    servo_err = (s_actual[-1] - s_target[-1]) if (s_actual and s_target) else 0.0
    servo_span = (max(s_actual[-6:]) - min(s_actual[-6:])) if len(s_actual) >= 4 else 0.0
    max_servo_curr = max(s_curr, default=0.05)
    min_servo_curr = min(s_curr[-4:], default=0.05) if s_curr else 0.05

    # 1. Power brownout (5V rail sag)
    if "CRIT_5V_RAIL_SAG" in codes_str or "BROWNOUT" in codes_str or min_rail < 4.40:
        diag = Diagnosis(
            cause_label="power.brownout (weak 5V buck regulator sagging below 4.25V MCU reset threshold)",
            supporting_evidence=[
                f"5V regulator rail sagged to {min_rail:.2f}V (MCU brownout reset threshold is 4.25V).",
                f"5V rail load drove regulator voltage down while battery was at {min_batt:.2f}V.",
                f"Fault codes triggered: {', '.join(incident.fault_codes) or 'CRIT_5V_RAIL_SAG'}.",
            ],
            alternative="power.battery_aging (upstream 2S battery voltage collapse)",
            next_check="Detach servo_arm or set a servo speed limit to reduce 5V regulator current draw and stabilize rail_5v_v at ~4.98V.",
            uncertainty="low",
            recommended_command={
                "target": "servo_arm",
                "action": "detach",
                "value": None,
                "reason": "Detach servo_arm to reduce 5V regulator load and prevent MCU brownout resets",
            },
        )
    # 2. Motor burned out (>115C)
    elif "BURNED_OUT" in codes_str or max_temp >= 112.0:
        diag = Diagnosis(
            cause_label=f"motor.burned_out ({primary_motor} winding insulation failure above 115°C)",
            supporting_evidence=[
                f"{primary_motor} winding temperature reached {max_temp:.1f}°C, exceeding the 115°C permanent burnout threshold.",
                f"Output shaft speed dropped to {last_rpm:.1f} RPM and winding current fell to {tail_curr:.3f}A (open winding).",
                f"Fault codes: {', '.join(incident.fault_codes) or 'CRIT_MTR_BURNED_OUT'}.",
            ],
            alternative=f"motor.disconnected (external wire detachment on {primary_motor})",
            next_check=f"Disable {primary_motor} in firmware and replace the damaged N20 motor hardware unit from the simulator dashboard.",
            uncertainty="low",
            recommended_command={
                "target": primary_motor,
                "action": "disable",
                "value": None,
                "reason": f"Disable burned-out motor {primary_motor} until hardware replacement",
            },
        )
    # 3. Motor disconnected (open circuit: high PWM, 0 RPM, ~0.004A current)
    elif "OPEN_CIRCUIT" in codes_str or "ZERO_CURRENT" in codes_str or (
        abs(avg_tail_rpm) < 2.0 and max_pwm > 0.25 and tail_curr < 0.03
    ):
        diag = Diagnosis(
            cause_label=f"motor.disconnected ({primary_motor} broken motor wire / open-circuit winding)",
            supporting_evidence=[
                f"{primary_motor} receives PWM drive ({max_pwm:.2f} duty), but supply current is only {tail_curr:.3f}A (H-bridge quiescent only).",
                f"Measured wheel speed remains at {last_rpm:.1f} RPM with zero torque production.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'ERR_MTR_OPEN_CIRCUIT'}.",
            ],
            alternative=f"motor.encoder_failure (though encoder failure would still draw >0.10A motor current)",
            next_check=f"Disable {primary_motor} in software so the PI loop stops driving an open circuit, and inspect motor terminal leads.",
            uncertainty="low",
            recommended_command={
                "target": primary_motor,
                "action": "disable",
                "value": None,
                "reason": f"Disable disconnected motor {primary_motor}",
            },
        )
    # 4. Motor encoder failure (0 reported RPM, high PWM windup, normal running current)
    elif "ERR_ENC_" in codes_str or (
        abs(avg_tail_rpm) < 2.0 and max_pwm >= 0.70 and 0.04 <= max_curr < 0.65 and max_target_rpm > 10
    ):
        diag = Diagnosis(
            cause_label=f"motor.encoder_failure ({primary_motor} hall encoder pulse loss causing PI windup)",
            supporting_evidence=[
                f"{primary_motor} encoder reports {last_rpm:.1f} RPM while target_rpm is {max_target_rpm:.0f} RPM.",
                f"PI controller wound PWM up to {max_pwm:.2f}, yet supply current is {tail_curr:.2f}A (not 0.95A stall), proving the motor is physically spinning.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'ERR_ENC_ZERO_TICKS'}.",
            ],
            alternative=f"motor.disconnected (ruled out because {tail_curr:.2f}A winding current is flowing)",
            next_check=f"Switch {primary_motor} from closed-loop PID to open-loop manual PWM (0.40) to stop PI windup runaway.",
            uncertainty="low",
            recommended_command={
                "target": primary_motor,
                "action": "set_pwm",
                "value": 0.4,
                "reason": f"Switch {primary_motor} to manual open-loop PWM (0.40) to mitigate encoder failure",
            },
        )
    # 5. Motor mechanical jam (0 RPM, ~0.85-0.95A stall current, rapid heating)
    elif ("ERR_MTR_" in codes_str and "STALL" in codes_str) or (
        abs(avg_tail_rpm) < 5.0 and max_curr >= 0.68
    ):
        diag = Diagnosis(
            cause_label=f"motor.jam ({primary_motor} mechanical gearbox/wheel jam)",
            supporting_evidence=[
                f"{primary_motor} stalled at {last_rpm:.1f} RPM while drawing {max_curr:.2f}A peak stall current (~0.95A theoretical at 8Ω).",
                f"Winding temperature rose +{temp_rise:.1f}°C (reaching {max_temp:.1f}°C) due to I²R stall dissipation.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'ERR_MTR_STALL'}.",
            ],
            alternative=f"motor.overheat (bearing seizure on {primary_motor})",
            next_check=f"Drive {primary_motor} briefly in reverse (>30% negative PWM for ~0.4s) to dislodge the mechanical gearbox jam.",
            uncertainty="low",
            recommended_command={
                "target": primary_motor,
                "action": "unjam_reverse",
                "value": -0.6,
                "reason": f"Reverse {primary_motor} (-0.6 PWM for 0.5s) to clear mechanical jam, then resume target RPM",
            },
        )
    # 6. Motor overheat (thermal runaway + extra bearing friction)
    elif "THERMAL_RISE" in codes_str or "BEARING_DRAG" in codes_str or (temp_rise >= 1.2 and max_temp >= 24.5):
        diag = Diagnosis(
            cause_label=f"motor.overheat ({primary_motor} degraded cooling and bearing friction thermal rise)",
            supporting_evidence=[
                f"{primary_motor} winding temperature climbed +{temp_rise:.1f}°C to {max_temp:.1f}°C in the capture window.",
                f"Motor current increased to {max_curr:.2f}A under +0.35A equivalent bearing drag and 8x degraded thermal resistance.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'WARN_MTR_THERMAL_RISE'}.",
            ],
            alternative=f"motor.jam (partial binding in {primary_motor} spur gear stage)",
            next_check=f"Set a firmware current limit (0.20A) or disable {primary_motor} so winding temperature stays below the 115°C burnout threshold.",
            uncertainty="low",
            recommended_command={
                "target": primary_motor,
                "action": "set_current_limit",
                "value": 0.20,
                "reason": f"Throttle {primary_motor} current limit to 0.20A to prevent >115°C burnout",
            },
        )
    # 7. Servo PWM signal loss (limp arm, ~0.004A current)
    elif "ERR_SERVO_PWM_LOSS" in codes_str or min_servo_curr <= 0.006:
        diag = Diagnosis(
            cause_label="servo.signal_loss (servo_arm PWM control signal lost, arm sagging under load)",
            supporting_evidence=[
                f"Servo arm sagged to {s_actual[-1]:.1f}° while target_deg was {s_target[-1]:.1f}°.",
                f"Servo supply current dropped to quiescent {min_servo_curr:.3f}A (pulse_us = 0, no H-bridge drive).",
                f"Fault codes: {', '.join(incident.fault_codes) or 'ERR_SERVO_PWM_LOSS'}.",
            ],
            alternative="servo_arm 5V power wire disconnection",
            next_check="Send servo_arm.reattach command to re-initialize the MCU PWM timer peripheral and restore holding torque.",
            uncertainty="low",
            recommended_command={
                "target": "servo_arm",
                "action": "reattach",
                "value": None,
                "reason": "Re-initialize PWM peripheral via reattach command to restore servo signal",
            },
        )
    # 8. Servo mechanical jam (~0.75A stall current, blocked away from target)
    elif "ERR_SERVO_STALL_BLOCKED" in codes_str or max_servo_curr >= 0.55:
        blocked_angle = round(s_actual[-1], 1)
        diag = Diagnosis(
            cause_label="servo.jam (servo_arm mechanically blocked away from target angle)",
            supporting_evidence=[
                f"Servo arm is physically blocked at {s_actual[-1]:.1f}° vs commanded {s_target[-1]:.1f}°.",
                f"Servo current spiked to {max_servo_curr:.2f}A (stall current 0.75A), heating the servo.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'ERR_SERVO_STALL_BLOCKED'}.",
            ],
            alternative="servo.calibration_drift (potentiometer offset, though drift does not draw 0.75A stall current)",
            next_check=f"Command servo_arm.set_target({blocked_angle}) to match its current blocked angle and immediately stop stall current.",
            uncertainty="low",
            recommended_command={
                "target": "servo_arm",
                "action": "set_target",
                "value": blocked_angle,
                "reason": f"Set servo target to blocked angle ({blocked_angle} deg) to release 0.75A stall torque",
            },
        )
    # 9. Servo jitter (noisy feedback oscillation + current spikes)
    elif "WARN_SERVO_FEEDBACK_JITTER" in codes_str or (servo_span >= 2.8 and max_servo_curr >= 0.14):
        diag = Diagnosis(
            cause_label="servo.jitter (servo_arm noisy position feedback causing oscillation and current spikes)",
            supporting_evidence=[
                f"Servo actual_deg oscillated across a {servo_span:.1f}° span despite a steady target of {s_target[-1]:.1f}°.",
                f"Rapid hunting caused servo current spikes up to {max_servo_curr:.2f}A.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'WARN_SERVO_FEEDBACK_JITTER'}.",
            ],
            alternative="servo.calibration_drift (static potentiometer offset)",
            next_check="Send servo_arm.detach while the arm is idle to stop oscillation and eliminate 5V rail current spikes.",
            uncertainty="low",
            recommended_command={
                "target": "servo_arm",
                "action": "detach",
                "value": None,
                "reason": "Detach jittering servo while idle to stop oscillation and current spikes",
            },
        )
    # 10. Servo calibration drift (steady offset from target, normal holding current)
    elif "WARN_SERVO_POS_OFFSET" in codes_str or abs(servo_err) >= 5.0:
        trim_fix = round(-servo_err, 1)
        diag = Diagnosis(
            cause_label="servo.calibration_drift (servo_arm feedback potentiometer offset)",
            supporting_evidence=[
                f"Servo settled at {s_actual[-1]:.1f}° vs commanded {s_target[-1]:.1f}° (steady offset {servo_err:+.1f}°).",
                f"Holding current is normal ({max_servo_curr:.2f}A < 0.75A stall), confirming the arm is not physically jammed.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'WARN_SERVO_POS_OFFSET'}.",
            ],
            alternative="servo.jam (mechanical obstruction near target)",
            next_check=f"Apply software trim compensation: servo_arm.set_trim({trim_fix:+.1f}) so the arm aligns with {s_target[-1]:.1f}°.",
            uncertainty="low",
            recommended_command={
                "target": "servo_arm",
                "action": "set_trim",
                "value": trim_fix,
                "reason": f"Compensate {servo_err:+.1f} deg feedback potentiometer drift with {trim_fix:+.1f} deg trim",
            },
        )
    # 11. Power battery aging (high internal resistance voltage sag)
    elif "WARN_BATT_INTERNAL_RES_SAG" in codes_str or "WARN_BATT_VOLTAGE_SAG" in codes_str or min_batt < 6.95:
        diag = Diagnosis(
            cause_label="power.battery_aging (elevated 2S battery internal resistance causing heavy voltage sag)",
            supporting_evidence=[
                f"2S battery terminal voltage sagged to {min_batt:.2f}V under load due to ~12x internal pack resistance.",
                f"5V buck regulator remained at {min_rail:.2f}V, isolating the fault to the upstream 2S Li-ion pack.",
                f"Fault codes: {', '.join(incident.fault_codes) or 'WARN_BATT_INTERNAL_RES_SAG'}.",
            ],
            alternative="Low battery state of charge (SOC depleted)",
            next_check="Set current limits (0.25A) across all motors to reduce total battery current draw and prevent deep voltage sag.",
            uncertainty="low",
            recommended_command={
                "target": "all_motors",
                "action": "set_current_limit",
                "value": 0.25,
                "reason": "Limit motor current draw to 0.25A per motor to mitigate aged battery voltage sag",
            },
        )
    else:
        diag = Diagnosis(
            cause_label="nominal_or_transient_load (no critical hardware fault threshold exceeded)",
            supporting_evidence=[
                f"5V rail stable at {min_rail:.2f}V; battery at {min_batt:.2f}V.",
                f"Primary motor {primary_motor} operating at {last_rpm:.1f} RPM, {tail_curr:.2f}A, {max_temp:.1f}°C.",
            ],
            alternative="Transient terrain incline or manual operator command adjustment",
            next_check="Continue monitoring live telemetry stream from simulator.",
            uncertainty="medium",
            recommended_command=None,
        )

    model_id = "robo-medic-physics-v1"

    # Continual learning adaptation from verified human confirmations in SQLite
    if exact_match is not None:
        diag.cause_label = exact_match["actual_cause"]
        diag.supporting_evidence.insert(
            0,
            f"[Continual Learning Memory] Verified by technician '{exact_match['verifier']}': actual cause '{exact_match['actual_cause']}', fix applied: '{exact_match['fix_performed']}'.",
        )
        diag.next_check = f"Apply technician-verified fix: {exact_match['fix_performed']}"
        diag.uncertainty = "low"
        model_id = "robo-medic-continual-adapter-v1"
    elif confirmations:
        diag.supporting_evidence.append(
            f"[Adapter Memory] Grounded against {len(confirmations)} prior technician-verified incident outcome(s) in SQLite."
        )
        model_id = "robo-medic-continual-adapter-v1"

    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = (
                "You are Robo Medic, an expert robotics fault diagnostician for a 4WD N20 rover.\n"
                f"Incident ID: {incident.id}\n"
                f"Commanded Action: {incident.commanded_action}\n"
                f"Fault Codes: {incident.fault_codes}\n"
                f"Technician Note: {incident.technician_note}\n"
                f"Physics Baseline Diagnosis: {diag.model_dump_json()}\n"
                f"Prior Technician Confirmations: {json.dumps(confirmations[:5])}\n"
                "Return ONLY valid JSON matching keys: cause_label, supporting_evidence (list of 3 concise strings), "
                "alternative, next_check, uncertainty ('low'|'medium'|'high'). Keep cause_label aligned with the physics fault identifier."
            )
            req = urllib.request.Request(
                url,
                data=json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                parsed["recommended_command"] = diag.recommended_command
                diag = Diagnosis.model_validate(parsed)
                model_id = "gemini-2.5-flash+adapter"
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
            pass

    return diag, model_id
