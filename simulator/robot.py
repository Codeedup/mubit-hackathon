"""
Robot physics + firmware model.

The simulated robot ("bot-01") is a small 4-wheel skid-steer rover:

  * 2S Li-ion battery pack (7.4 V nominal, 8.4 V full) with internal resistance,
    so the voltage sags when current is drawn.
  * 5 V buck regulator feeding the MCU, sensors and the servo.
  * 4x N20 micro gear motors (6 V rated, 1:100 gearbox, ~300 RPM no-load) with
    hall quadrature encoders, driven by an H-bridge. The firmware runs a PI speed
    loop per motor (or plain manual PWM).
  * 1x feedback hobby servo (MG90S-class with an analog position feedback wire),
    so the robot actually *knows* where the arm is.
  * 6-axis IMU (accelerometer + gyro).

Everything advances with a fixed physics step (PHYS_DT, 100 Hz). Faults can be
injected from the dashboard; their effects emerge from the physics (e.g. a jammed
motor draws stall current -> heats -> burns out if nobody reacts).
"""

from __future__ import annotations

import math
import random
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Helpers / constants
# --------------------------------------------------------------------------- #


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


# N20 motor model (values referenced to the gearbox OUTPUT shaft)
N20_R = 8.0  # winding resistance [ohm]  -> ~0.95 A stall at 7.6 V
N20_I0 = 0.06  # no-load friction current [A]
N20_KE = 0.0184  # back-EMF constant [V per output RPM]  (300 RPM @ 6 V no-load)
N20_ACCEL = 8700.0  # RPM/s per amp of net "torque current" (gives ~50 ms time constant)
N20_GEAR = 100
N20_CPR = 7 * 4 * N20_GEAR  # 7 PPR hall encoder, quadrature x4, 1:100 -> 2800 counts / wheel rev
N20_RTH = 15.0  # thermal resistance winding->ambient [degC/W]
N20_CTH = 1.0  # thermal capacity [J/degC]
N20_BURNOUT_C = 115.0  # winding insulation dies above this

WHEEL_D = 0.043  # wheel diameter [m]
TRACK_W = 0.12  # distance between left and right wheels [m]

# Open-circuit voltage per Li-ion cell vs state of charge
OCV_TABLE = [
    (0.00, 3.00), (0.05, 3.30), (0.10, 3.50), (0.20, 3.62), (0.30, 3.70), (0.40, 3.75),
    (0.50, 3.80), (0.60, 3.86), (0.70, 3.93), (0.80, 4.00), (0.90, 4.08), (1.00, 4.20),
]

BROWNOUT_V = 4.25  # MCU resets if the 5 V rail drops below this for > 20 ms
BOOT_TIME_S = 0.8

# Human-readable description of every injectable fault (also shown in the UI and docs).
FAULT_INFO: dict[str, dict[str, str]] = {
    "motor": {
        "jam": "Wheel/gearbox mechanically jammed: ~0 RPM while drawing stall current (~0.9 A) and heating fast. "
               "Software fix: drive briefly in REVERSE (>30% PWM for ~0.4 s) to free it.",
        "encoder_failure": "Hall encoder stopped producing pulses: reported RPM = 0 and ticks freeze although the wheel turns. "
                           "The PI loop winds up to full power (runaway). Mitigation: switch the motor to manual PWM.",
        "overheat": "Degraded cooling + extra bearing friction: temperature keeps climbing. Above 115 degC the winding burns out. "
                    "Mitigation: lower PWM / set a current limit / disable until it cools.",
        "disconnected": "Motor wire broken: PWM is applied but ~0 A flows and RPM is 0. Not fixable in software - disable the motor.",
        "burned_out": "CONSEQUENCE (not injectable): the motor exceeded 115 degC and is permanently dead until replaced from the dashboard.",
    },
    "servo": {
        "jam": "Arm physically blocked at its current angle. Any other target makes it stall (~0.75 A) and heat up. "
               "Mitigation: command target = actual angle (stop pushing).",
        "jitter": "Noisy signal/feedback: the arm shakes +/-2-4 deg and current spikes. Hardware issue - mitigate by detaching when idle.",
        "calibration_drift": "Feedback potentiometer drifted: the arm settles at an offset from the target. "
                             "Software fix: set_trim = current_trim - (actual - target).",
        "signal_loss": "PWM signal output lost (pulse_us = 0): servo goes limp and the arm sags under load. Software fix: 'reattach'.",
    },
    "power": {
        "battery_aging": "Battery internal resistance x5: heavy voltage sag under load. Mitigation: reduce current (lower speeds / current limits).",
        "brownout": "Weak 5 V regulator: the rail sags with load; below 4.25 V the MCU resets (telemetry gap, seq/boot_id change). "
                    "Mitigation: reduce 5 V load (slow the servo with a speed limit, or detach it).",
    },
}

INJECTABLE = {
    "motor": {"jam", "encoder_failure", "overheat", "disconnected"},
    "servo": {"jam", "jitter", "calibration_drift", "signal_loss"},
    "power": {"battery_aging", "brownout"},
}

Logger = Callable[[str, str, str], None]


# --------------------------------------------------------------------------- #
# Battery
# --------------------------------------------------------------------------- #


class Battery:
    CELLS = 2

    def __init__(self, ambient: float):
        self.capacity_mah = 2000.0
        self.soc = 0.85
        self.r_int = 0.09  # pack internal resistance [ohm]
        self.drain_mult = 1.0  # time-warp for discharge so you can watch the battery die
        self.temp = ambient

    def ocv(self) -> float:
        s = clamp(self.soc, 0.0, 1.0)
        for (s0, v0), (s1, v1) in zip(OCV_TABLE, OCV_TABLE[1:]):
            if s <= s1:
                return (v0 + (v1 - v0) * (s - s0) / (s1 - s0)) * self.CELLS
        return OCV_TABLE[-1][1] * self.CELLS

    def step(self, dt: float, current: float, ambient: float, aging: bool) -> float:
        """Advance and return the terminal voltage."""
        self.soc = clamp(
            self.soc - current * dt / 3600.0 / (self.capacity_mah / 1000.0) * self.drain_mult, 0.0, 1.0
        )
        r = self.r_int * (5.0 if aging else 1.0)
        self.temp += ((current**2) * r - (self.temp - ambient) / 6.0) / 40.0 * dt
        return max(0.0, self.ocv() - current * r)


# --------------------------------------------------------------------------- #
# N20 gear motor + encoder + firmware PI loop
# --------------------------------------------------------------------------- #


class N20Motor:
    KP = 0.0015  # PWM per RPM of error
    KI = 0.006  # PWM per RPM*s of error

    def __init__(self, mid: str, position: str, side: str, ambient: float):
        self.id = mid
        self.position = position
        self.side = side
        self.load = 0.10  # external wheel load 0..1 (terrain / friction), sim parameter
        self.faults: dict[str, float] = {}  # fault -> sim time injected
        self.temp = ambient
        self.rpm = 0.0  # TRUE output shaft speed
        self.motor_current = 0.0  # winding current (signed)
        self.supply_current = 0.0  # what a current sensor on the H-bridge supply reads
        self.true_ticks = 0.0
        self.jam_dir = 0
        self.unjam_timer = 0.0
        self.firmware_reset()

    # -- firmware state (lost on MCU reboot) --------------------------------
    def firmware_reset(self) -> None:
        self.enabled = True
        self.mode = "pid"  # "pid" (closed-loop target RPM) | "manual" (raw PWM)
        self.target_rpm = 0.0
        self.manual_pwm = 0.0
        self.current_limit: float | None = None
        self.pwm = 0.0
        self.integral = 0.0
        self.enc_ticks = 0.0
        self._enc_prev = 0
        self.meas_rpm = 0.0
        self.limit_scale = 1.0

    @property
    def dead(self) -> bool:
        return "disconnected" in self.faults or "burned_out" in self.faults

    def firmware_step(self, dt: float, vbatt: float, mcu_on: bool, estop: bool) -> None:
        # Speed measurement from the encoder - this is all the MCU knows.
        q = math.floor(self.enc_ticks)
        inst = (q - self._enc_prev) / N20_CPR * 60.0 / dt
        self._enc_prev = q
        self.meas_rpm += 0.15 * (inst - self.meas_rpm)

        if not mcu_on or not self.enabled or estop or vbatt < 1.0:
            self.pwm = 0.0
            self.integral = 0.0
            return

        if self.mode == "manual":
            pwm = self.manual_pwm
        elif self.target_rpm == 0 and abs(self.meas_rpm) < 5:
            pwm = 0.0
            self.integral = 0.0
        else:
            ff = self.target_rpm * N20_KE / vbatt  # back-EMF feed-forward
            err = self.target_rpm - self.meas_rpm
            raw = ff + self.KP * err + self.integral
            if abs(raw) < 1.0 or sign(err) != sign(raw):  # anti-windup
                self.integral += self.KI * err * dt
            pwm = ff + self.KP * err + self.integral

        # Current-limit foldback (firmware feature, configurable over the link)
        if self.current_limit is not None:
            over = abs(self.motor_current) - self.current_limit
            if over > 0:
                self.limit_scale = max(0.0, self.limit_scale - 6.0 * dt * over / self.current_limit)
            else:
                self.limit_scale = min(1.0, self.limit_scale + 0.8 * dt)
        else:
            self.limit_scale = 1.0

        self.pwm = clamp(pwm, -1.0, 1.0) * self.limit_scale

    def physics_step(self, dt: float, vbatt: float, ambient: float, extra_load: float, now: float, log: Logger) -> None:
        v = self.pwm * vbatt  # averaged H-bridge output voltage
        friction = N20_I0 + 0.5 * self.load + extra_load + (0.35 if "overheat" in self.faults else 0.0)

        if self.dead:
            i = 0.0
            dec = N20_ACCEL * friction * dt
            self.rpm = 0.0 if abs(self.rpm) <= dec else self.rpm - math.copysign(dec, self.rpm)
        elif "jam" in self.faults:
            self.rpm = 0.0
            i = v / N20_R
            if abs(self.pwm) > 0.3:
                d = sign(self.pwm)
                if self.jam_dir == 0:
                    self.jam_dir = d
                self.unjam_timer = self.unjam_timer + dt if d == -self.jam_dir else 0.0
                if self.unjam_timer >= 0.4:
                    del self.faults["jam"]
                    self.unjam_timer = 0.0
                    self.jam_dir = 0
                    log("sim", "fault", f"{self.id}: jam CLEARED by reverse drive")
        else:
            i = (v - N20_KE * self.rpm) / N20_R
            if abs(self.rpm) > 0.5:
                new = self.rpm + N20_ACCEL * (i - math.copysign(friction, self.rpm)) * dt
                self.rpm = 0.0 if sign(new) != sign(self.rpm) else new
            elif abs(i) > friction:
                self.rpm += N20_ACCEL * (i - math.copysign(friction, i)) * dt
            else:
                self.rpm = 0.0

        self.motor_current = i
        self.supply_current = max(0.0, self.pwm * i) + 0.004  # + driver quiescent

        # Thermal model
        is_overheat = "overheat" in self.faults
        # When overheating: severe loss of heat dissipation + thermal runaway wattage
        rth = N20_RTH * (8.0 if is_overheat else 1.0)
        extra_heat = 1.6 if is_overheat else 0.0  # continuous runaway thermal dissipation
        heat_in = i * i * N20_R + extra_heat
        heat_out = (self.temp - ambient) / rth
        self.temp += (heat_in - heat_out) / N20_CTH * dt
        if self.temp > N20_BURNOUT_C and "burned_out" not in self.faults:
            self.faults["burned_out"] = now
            log("sim", "fault", f"{self.id}: BURNED OUT at {self.temp:.0f} degC (thermal runaway)")

        # Encoder
        d_ticks = self.rpm / 60.0 * N20_CPR * dt
        self.true_ticks += d_ticks
        if "encoder_failure" not in self.faults:
            self.enc_ticks += d_ticks

    def apply(self, action: str, value: Any, estop: bool) -> None:
        if action == "set_target_rpm":
            if self.mode != "pid":
                self.integral = 0.0
            self.mode = "pid"
            self.target_rpm = clamp(float(value), -400.0, 400.0)
        elif action == "set_pwm":
            self.mode = "manual"
            self.manual_pwm = clamp(float(value), -1.0, 1.0)
        elif action == "set_mode":
            if value not in ("pid", "manual"):
                raise ValueError("set_mode value must be 'pid' or 'manual'")
            if value == "manual" and self.mode != "manual":
                self.manual_pwm = self.pwm  # bumpless transfer
            if value == "pid":
                self.integral = 0.0
            self.mode = value
        elif action == "enable":
            if estop:
                raise ValueError("E-STOP active - send robot.resume first")
            self.enabled = True
        elif action == "disable":
            self.enabled = False
        elif action == "stop":
            self.target_rpm = 0.0
            self.manual_pwm = 0.0
        elif action == "set_current_limit":
            self.current_limit = None if value in (None, 0, 0.0) else clamp(float(value), 0.05, 2.0)
        else:
            raise ValueError(
                f"unknown motor action '{action}' (valid: set_target_rpm, set_pwm, set_mode, enable, disable, stop, set_current_limit)"
            )

    def telemetry(self, n: float) -> dict[str, Any]:
        g = random.gauss
        rpm = self.meas_rpm + (g(0, 0.6 * n) if abs(self.meas_rpm) > 0.5 else 0.0)
        return {
            "id": self.id,
            "position": self.position,
            "enabled": self.enabled,
            "mode": self.mode,
            "pwm": round(self.pwm, 3),
            "target_rpm": round(self.target_rpm, 1),
            "rpm": round(rpm, 1),
            "current_a": round(max(0.0, self.supply_current + g(0, 0.004 * n)), 3),
            "current_limit_a": self.current_limit,
            "encoder_ticks": int(math.floor(self.enc_ticks)),
            "temp_c": round(self.temp + g(0, 0.15 * n), 1),
        }


# --------------------------------------------------------------------------- #
# Feedback servo
# --------------------------------------------------------------------------- #


class Servo:
    MAX_SPEED_DPS = 600.0  # ~0.1 s / 60 deg at 5 V
    STALL_A = 0.75

    def __init__(self, sid: str, ambient: float):
        self.id = sid
        self.load = 0.20  # holding load 0..1 (what the arm is carrying), sim parameter
        self.faults: dict[str, float] = {}
        self.drift_offset = 0.0
        self.actual = 90.0  # TRUE arm angle
        self.temp = ambient
        self.current = 0.0
        self.moving = False
        self.blocked = False
        self.pulse_us = 1500
        self.commanded: float | None = 90.0
        self.firmware_reset()

    def firmware_reset(self) -> None:
        self.target = 90.0
        self.trim = 0.0
        self.speed_limit: float | None = None
        self.attached = True

    def step(self, dt: float, rail_v: float, ambient: float, mcu_on: bool) -> None:
        signal = mcu_on and self.attached and "signal_loss" not in self.faults and rail_v > 3.5
        self.blocked = False
        speed = 0.0
        if signal:
            self.commanded = clamp(self.target + self.trim, 0.0, 180.0)
            self.pulse_us = int(round(500 + self.commanded / 180.0 * 2000))
            goal = self.commanded + (self.drift_offset if "calibration_drift" in self.faults else 0.0)
            goal = clamp(goal, 0.0, 180.0)
            vmax = self.MAX_SPEED_DPS * clamp(rail_v / 5.0, 0.0, 1.2) * (1.0 - 0.6 * self.load)
            if self.speed_limit:
                vmax = min(vmax, self.speed_limit)
            err = goal - self.actual
            if "jam" in self.faults:
                self.blocked = abs(err) > 1.0
            else:
                step = clamp(err, -vmax * dt, vmax * dt)
                self.actual += step
                speed = abs(step) / dt
            current = 0.008 + 0.30 * self.load
            if speed > 0.5:
                current += 0.04 + 0.22 * speed / self.MAX_SPEED_DPS
            if self.blocked:
                current = self.STALL_A
            if "jitter" in self.faults:
                self.actual += random.gauss(0, 1.6)
                current += abs(random.gauss(0, 0.07))
                speed = max(speed, 10.0)
        else:
            self.commanded = None
            self.pulse_us = 0
            sag = 40.0 * self.load * dt  # limp arm falls toward 0 deg under its load
            speed = sag / dt if self.actual > 0 else 0.0
            self.actual -= sag
            current = 0.004
        self.actual = clamp(self.actual, 0.0, 180.0)
        self.moving = speed > 2.0
        self.current = current
        self.temp += (current * rail_v * 0.5 - (self.temp - ambient) / 25.0) / 4.0 * dt

    def apply(self, action: str, value: Any) -> None:
        if action == "set_target":
            self.target = clamp(float(value), 0.0, 180.0)
        elif action == "set_trim":
            self.trim = clamp(float(value), -30.0, 30.0)
        elif action == "set_speed_limit":
            self.speed_limit = None if value in (None, 0, 0.0) else clamp(float(value), 5.0, 600.0)
        elif action == "attach":
            self.attached = True
        elif action == "detach":
            self.attached = False
        elif action == "reattach":
            self.faults.pop("signal_loss", None)  # re-initialising the PWM peripheral restores the signal
            self.attached = True
        else:
            raise ValueError(
                f"unknown servo action '{action}' (valid: set_target, set_trim, set_speed_limit, attach, detach, reattach)"
            )

    def telemetry(self, n: float) -> dict[str, Any]:
        return {
            "id": self.id,
            "attached": self.attached,
            "target_deg": round(self.target, 1),
            "trim_deg": round(self.trim, 2),
            "commanded_deg": None if self.commanded is None else round(self.commanded, 1),
            "actual_deg": round(clamp(self.actual + random.gauss(0, 0.25 * n), 0, 180), 2),
            "pulse_us": self.pulse_us,
            "moving": self.moving,
            "speed_limit_dps": self.speed_limit,
            "current_a": round(max(0.0, self.current + random.gauss(0, 0.004 * n)), 3),
            "temp_c": round(self.temp + random.gauss(0, 0.15 * n), 1),
        }


# --------------------------------------------------------------------------- #
# Whole robot
# --------------------------------------------------------------------------- #


class Robot:
    PHYS_DT = 0.01
    ROBOT_ID = "bot-01"
    FIRMWARE = "1.4.2"

    def __init__(self) -> None:
        self.env = {"ambient_c": 22.0, "incline_deg": 0.0}
        self.comms = {
            "rate_hz": 10.0,
            "packet_loss_pct": 0.0,
            "noise": 1.0,
            "wifi_rssi_dbm": -55.0,
            "ground_truth": False,
        }
        self.events: deque[dict[str, Any]] = deque(maxlen=400)
        self.event_id = 0
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self) -> None:
        amb = self.env["ambient_c"]
        self.battery = Battery(amb)
        self.motors = [
            N20Motor("n20_fl", "front_left", "left", amb),
            N20Motor("n20_fr", "front_right", "right", amb),
            N20Motor("n20_rl", "rear_left", "left", amb),
            N20Motor("n20_rr", "rear_right", "right", amb),
        ]
        self.motor_by_id = {m.id: m for m in self.motors}
        self.servo = Servo("servo_arm", amb)
        self.power_faults: dict[str, float] = {}
        self.battery_v = self.battery.ocv()
        self.battery_current = 0.0
        self.rail_v = 5.0
        self.rail_current = 0.0
        self.sim_time = 0.0
        self.uptime = 0.0
        self.boot_id = 1
        self.reset_count = 0
        self.reset_reason = "power_on"
        self.booting = 0.0
        self.brownout_timer = 0.0
        self.estop = False
        self.seq = 0
        self.pose = {"x": 0.0, "y": 0.0, "h": 0.0}  # true pose
        self.odom = {"x": 0.0, "y": 0.0, "h": 0.0}  # encoder-based (what the robot believes)
        self.v = 0.0
        self.w = 0.0
        self.v_enc = 0.0
        self.w_enc = 0.0
        self.accel = 0.0
        self.gyro_bias = random.uniform(-0.4, 0.4)
        self.cpu_load = 30.0
        self.running = True
        self.log("sim", "system", "Simulation reset")

    def log(self, source: str, kind: str, text: str) -> None:
        self.event_id += 1
        self.events.append({"id": self.event_id, "t": round(self.sim_time, 2), "source": source, "kind": kind, "text": text})

    # ------------------------------------------------------------------ physics
    def step(self, dt: float) -> None:
        self.sim_time += dt
        amb = self.env["ambient_c"]
        incline = math.radians(self.env["incline_deg"])
        extra_load = 0.3 * abs(math.sin(incline))

        if self.booting > 0:
            self.booting -= dt
            if self.booting <= 0:
                if self.rail_v < BROWNOUT_V + 0.15:
                    self.booting = 0.2  # rail still too low, keep holding in reset
                else:
                    self.log("robot", "system", f"MCU booted (boot_id={self.boot_id}, reason={self.reset_reason})")
        mcu_on = self.booting <= 0
        if mcu_on:
            self.uptime += dt

        for m in self.motors:
            m.firmware_step(dt, self.battery_v, mcu_on, self.estop)
        for m in self.motors:
            m.physics_step(dt, self.battery_v, amb, extra_load, self.sim_time, self.log)
        self.servo.step(dt, self.rail_v, amb, mcu_on)

        # Power tree: battery -> (H-bridges) + (5 V buck -> MCU, sensors, servo)
        i5 = self.servo.current + (0.15 if mcu_on else 0.03)
        r_reg = 1.8 if "brownout" in self.power_faults else 0.08
        rail_nominal = min(5.0, max(0.0, self.battery_v - 0.5))
        self.rail_v = max(0.0, rail_nominal - i5 * r_reg)
        self.rail_current = i5
        logic_from_batt = self.rail_v * i5 / (0.88 * max(self.battery_v, 1.0))
        self.battery_current = sum(m.supply_current for m in self.motors) + logic_from_batt + 0.01
        self.battery_v = self.battery.step(dt, self.battery_current, amb, "battery_aging" in self.power_faults)

        # Brownout detector
        if mcu_on and self.rail_v < BROWNOUT_V:
            self.brownout_timer += dt
            if self.brownout_timer > 0.02:
                self._mcu_reset("brownout")
        else:
            self.brownout_timer = 0.0

        self._motion_step(dt)

        active = sum(1 for m in self.motors if abs(m.pwm) > 0.01)
        target_cpu = 28 + 4 * active + (6 if self.servo.moving else 0)
        self.cpu_load += (target_cpu - self.cpu_load) * 0.02 + random.gauss(0, 0.3)
        self.cpu_load = clamp(self.cpu_load, 5, 100)

    def _motion_step(self, dt: float) -> None:
        def wheel_v(rpm: float) -> float:
            return rpm / 60.0 * math.pi * WHEEL_D

        left = [m for m in self.motors if m.side == "left"]
        right = [m for m in self.motors if m.side == "right"]
        vl = sum(wheel_v(m.rpm) for m in left) / len(left)
        vr = sum(wheel_v(m.rpm) for m in right) / len(right)
        v, w = (vl + vr) / 2, (vr - vl) / TRACK_W
        self.accel += ((v - self.v) / dt - self.accel) * 0.05
        self.v, self.w = v, w
        self.pose["h"] += w * dt
        self.pose["x"] += v * math.cos(self.pose["h"]) * dt
        self.pose["y"] += v * math.sin(self.pose["h"]) * dt

        vl_e = sum(wheel_v(m.meas_rpm) for m in left) / len(left)
        vr_e = sum(wheel_v(m.meas_rpm) for m in right) / len(right)
        self.v_enc, self.w_enc = (vl_e + vr_e) / 2, (vr_e - vl_e) / TRACK_W
        self.odom["h"] += self.w_enc * dt
        self.odom["x"] += self.v_enc * math.cos(self.odom["h"]) * dt
        self.odom["y"] += self.v_enc * math.sin(self.odom["h"]) * dt

    def _mcu_reset(self, reason: str) -> None:
        self.reset_count += 1
        self.reset_reason = reason
        self.boot_id += 1
        self.booting = BOOT_TIME_S
        self.uptime = 0.0
        self.seq = 0
        self.estop = False
        self.brownout_timer = 0.0
        for m in self.motors:
            m.firmware_reset()
        self.servo.firmware_reset()
        self.odom = {"x": 0.0, "y": 0.0, "h": 0.0}
        self.log("robot", "warning", f"MCU RESET ({reason}) - firmware state lost, rebooting...")

    # ------------------------------------------------------------------ telemetry
    def effective_packet_loss(self) -> float:
        rssi_penalty = max(0.0, (-78.0 - self.comms["wifi_rssi_dbm"]) * 4.0)
        return clamp(self.comms["packet_loss_pct"] + rssi_penalty, 0.0, 100.0)

    def build_packet(self) -> dict[str, Any] | None:
        """Build the next telemetry packet (None while the MCU is booting)."""
        if self.booting > 0:
            return None
        self.seq += 1
        n = self.comms["noise"]
        g = random.gauss
        inc = math.radians(self.env["incline_deg"])
        pkt: dict[str, Any] = {
            "type": "telemetry",
            "schema": "robot.telemetry.v1",
            "robot_id": self.ROBOT_ID,
            "firmware": self.FIRMWARE,
            "boot_id": self.boot_id,
            "seq": self.seq,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "uptime_s": round(self.uptime, 2),
            "power": {
                "battery_v": round(self.battery_v + g(0, 0.01 * n), 3),
                "battery_current_a": round(max(0.0, self.battery_current + g(0, 0.01 * n)), 3),
                "battery_power_w": round(self.battery_v * self.battery_current, 2),
                "soc_pct": round(self.battery.soc * 100, 1),
                "battery_temp_c": round(self.battery.temp + g(0, 0.1 * n), 1),
                "rail_5v_v": round(self.rail_v + g(0, 0.006 * n), 3),
                "rail_5v_current_a": round(self.rail_current + g(0, 0.003 * n), 3),
            },
            "motors": [m.telemetry(n) for m in self.motors],
            "servo": self.servo.telemetry(n),
            "motion": {
                "speed_mps": round(self.v_enc, 3),
                "yaw_rate_dps": round(math.degrees(self.w_enc), 2),
                "odom_x_m": round(self.odom["x"], 3),
                "odom_y_m": round(self.odom["y"], 3),
                "odom_heading_deg": round(math.degrees(self.odom["h"]) % 360, 1),
            },
            "imu": {
                "accel_x_g": round(self.accel / 9.81 + math.sin(inc) + g(0, 0.01 * n), 3),
                "accel_y_g": round(self.v * self.w / 9.81 + g(0, 0.01 * n), 3),
                "accel_z_g": round(math.cos(inc) + g(0, 0.01 * n), 3),
                "gyro_x_dps": round(g(0, 0.3 * n), 2),
                "gyro_y_dps": round(g(0, 0.3 * n), 2),
                "gyro_z_dps": round(math.degrees(self.w) + self.gyro_bias + g(0, 0.3 * n), 2),
                "pitch_deg": round(self.env["incline_deg"] + g(0, 0.2 * n), 1),
                "roll_deg": round(g(0, 0.2 * n), 1),
            },
            "system": {
                "mcu_temp_c": round(self.env["ambient_c"] + 14 + 0.1 * self.cpu_load + g(0, 0.2 * n), 1),
                "cpu_load_pct": round(self.cpu_load, 1),
                "loop_dt_ms": round(10 + abs(g(0, 0.25)) * (1 + self.cpu_load / 50), 2),
                "wifi_rssi_dbm": round(self.comms["wifi_rssi_dbm"] + g(0, 1.5 * n)),
                "reset_count": self.reset_count,
                "last_reset_reason": self.reset_reason,
                "estop": self.estop,
            },
        }
        if self.comms["ground_truth"]:
            pkt["_ground_truth"] = self.ground_truth()
        return pkt

    def active_faults(self) -> list[dict[str, Any]]:
        out = []
        for m in self.motors:
            out += [{"component": m.id, "fault": f, "since_s": round(self.sim_time - t, 1)} for f, t in m.faults.items()]
        out += [{"component": self.servo.id, "fault": f, "since_s": round(self.sim_time - t, 1)} for f, t in self.servo.faults.items()]
        out += [{"component": "power", "fault": f, "since_s": round(self.sim_time - t, 1)} for f, t in self.power_faults.items()]
        return out

    def ground_truth(self) -> dict[str, Any]:
        faults = self.active_faults()
        return {
            "healthy": not faults,
            "active_faults": faults,
            "true_values": {
                "motor_rpm": {m.id: round(m.rpm, 1) for m in self.motors},
                "servo_actual_deg": round(self.servo.actual, 2),
                "battery_internal_resistance_ohm": round(self.battery.r_int * (5 if "battery_aging" in self.power_faults else 1), 3),
                "pose": {"x_m": round(self.pose["x"], 3), "y_m": round(self.pose["y"], 3),
                         "heading_deg": round(math.degrees(self.pose["h"]) % 360, 1)},
            },
        }

    # ------------------------------------------------------------------ commands (robot side)
    def apply_command(self, msg: dict[str, Any], source: str) -> tuple[bool, str]:
        """Commands the robot firmware understands. Allowed from listeners AND the dashboard."""
        target = str(msg.get("target", "robot"))
        action = msg.get("action")
        value = msg.get("value")
        reason = msg.get("reason")
        if not action:
            return False, "missing 'action'"
        try:
            if self.booting > 0 and not (target == "robot" and action == "estop"):
                raise ValueError("robot is rebooting, command ignored")
            if target == "robot":
                if action == "estop":
                    self.estop = True
                elif action == "resume":
                    self.estop = False
                    for m in self.motors:
                        m.enabled = True
                elif action == "reboot":
                    self._mcu_reset("command")
                else:
                    raise ValueError(f"unknown robot action '{action}' (valid: estop, resume, reboot)")
            elif target == "all_motors" or target in self.motor_by_id:
                for m in self.motors if target == "all_motors" else [self.motor_by_id[target]]:
                    m.apply(action, value, self.estop)
            elif target in (self.servo.id, "servo"):
                self.servo.apply(action, value)
            else:
                raise ValueError(f"unknown target '{target}' (valid: robot, all_motors, {', '.join(self.motor_by_id)}, {self.servo.id})")
        except (ValueError, TypeError) as e:
            self.log(source, "rejected", f"{target}.{action}({value}) rejected: {e}")
            return False, str(e)
        if not msg.get("quiet"):
            txt = f"{target}.{action}" + (f"({value})" if value is not None else "")
            if reason:
                txt += f"  - {reason}"
            self.log(source, "command", txt)
        return True, f"applied {target}.{action}"

    # ------------------------------------------------------------------ sim controls (dashboard only)
    def _fault_store(self, component: str) -> tuple[dict[str, float], set[str]]:
        if component in self.motor_by_id:
            return self.motor_by_id[component].faults, INJECTABLE["motor"] | {"burned_out"}
        if component == self.servo.id:
            return self.servo.faults, INJECTABLE["servo"]
        if component == "power":
            return self.power_faults, INJECTABLE["power"]
        raise ValueError(f"unknown component '{component}'")

    def apply_sim(self, msg: dict[str, Any]) -> tuple[bool, str]:
        action = msg.get("action")
        comp = msg.get("component")
        fault = msg.get("fault")
        try:
            if action == "inject_fault":
                store, allowed = self._fault_store(comp)
                if fault not in allowed or fault == "burned_out":
                    raise ValueError(f"fault '{fault}' not injectable on {comp}")
                store[fault] = self.sim_time
                extra = ""
                if comp in self.motor_by_id and fault == "jam":
                    m = self.motor_by_id[comp]
                    m.jam_dir, m.unjam_timer = sign(m.pwm), 0.0
                if comp == self.servo.id and fault == "calibration_drift":
                    v = msg.get("value")
                    self.servo.drift_offset = float(v) if v else random.choice([-1, 1]) * random.uniform(8, 15)
                    extra = f" (offset {self.servo.drift_offset:+.1f} deg)"
                self.log("sim", "fault", f"Injected '{fault}' on {comp}{extra}")
            elif action == "clear_fault":
                store, _ = self._fault_store(comp)
                if store.pop(fault, None) is not None:
                    if fault == "burned_out":
                        m = self.motor_by_id[comp]
                        m.temp = self.env["ambient_c"]
                        self.log("sim", "fault", f"{comp}: motor REPLACED")
                    else:
                        self.log("sim", "fault", f"Cleared '{fault}' on {comp}")
            elif action == "clear_all_faults":
                for m in self.motors:
                    m.faults.clear()
                self.servo.faults.clear()
                self.power_faults.clear()
                self.log("sim", "fault", "All faults cleared")
            elif action == "set":
                self.set_param(str(msg.get("key")), msg.get("value"))
            elif action == "pause":
                self.running = False
                self.log("sim", "system", "Simulation paused")
            elif action == "resume":
                self.running = True
                self.log("sim", "system", "Simulation resumed")
            elif action == "reset":
                self.reset()
            else:
                raise ValueError(f"unknown sim action '{action}'")
        except (ValueError, TypeError, KeyError) as e:
            return False, str(e)
        return True, "ok"

    def set_param(self, key: str, value: Any) -> None:
        if key == "comms.ground_truth":
            self.comms["ground_truth"] = bool(value)
            return
        v = float(value)
        if key == "battery.soc":
            self.battery.soc = clamp(v, 0, 100) / 100
        elif key == "battery.capacity_mah":
            self.battery.capacity_mah = clamp(v, 200, 10000)
        elif key == "battery.r_int_mohm":
            self.battery.r_int = clamp(v, 10, 1000) / 1000
        elif key == "battery.drain_mult":
            self.battery.drain_mult = clamp(v, 1, 500)
        elif key == "env.ambient_c":
            self.env["ambient_c"] = clamp(v, -10, 50)
        elif key == "env.incline_deg":
            self.env["incline_deg"] = clamp(v, 0, 30)
        elif key == "comms.rate_hz":
            self.comms["rate_hz"] = clamp(v, 1, 50)
        elif key == "comms.packet_loss_pct":
            self.comms["packet_loss_pct"] = clamp(v, 0, 100)
        elif key == "comms.noise":
            self.comms["noise"] = clamp(v, 0, 5)
        elif key == "comms.wifi_rssi_dbm":
            self.comms["wifi_rssi_dbm"] = clamp(v, -95, -30)
        elif key == "servo.load":
            self.servo.load = clamp(v, 0, 100) / 100
        elif key.startswith("motor.load:"):
            self.motor_by_id[key.split(":", 1)[1]].load = clamp(v, 0, 100) / 100
        else:
            raise ValueError(f"unknown parameter '{key}'")

    def params(self) -> dict[str, Any]:
        p: dict[str, Any] = {
            "battery.soc": round(self.battery.soc * 100, 1),
            "battery.capacity_mah": self.battery.capacity_mah,
            "battery.r_int_mohm": round(self.battery.r_int * 1000),
            "battery.drain_mult": self.battery.drain_mult,
            "env.ambient_c": self.env["ambient_c"],
            "env.incline_deg": self.env["incline_deg"],
            "comms.rate_hz": self.comms["rate_hz"],
            "comms.packet_loss_pct": self.comms["packet_loss_pct"],
            "comms.noise": self.comms["noise"],
            "comms.wifi_rssi_dbm": self.comms["wifi_rssi_dbm"],
            "comms.ground_truth": self.comms["ground_truth"],
            "servo.load": round(self.servo.load * 100),
        }
        for m in self.motors:
            p[f"motor.load:{m.id}"] = round(m.load * 100)
        return p

    # ------------------------------------------------------------------ dashboard state
    def ui_state(self) -> dict[str, Any]:
        s = self.servo
        return {
            "t": round(self.sim_time, 2),
            "running": self.running,
            "booting": self.booting > 0,
            "estop": self.estop,
            "uptime": round(self.uptime, 1),
            "seq": self.seq,
            "boot_id": self.boot_id,
            "reset_count": self.reset_count,
            "reset_reason": self.reset_reason,
            "power": {
                "battery_v": round(self.battery_v, 3),
                "battery_current_a": round(self.battery_current, 3),
                "power_w": round(self.battery_v * self.battery_current, 2),
                "soc_pct": round(self.battery.soc * 100, 1),
                "rail_5v_v": round(self.rail_v, 3),
                "rail_5v_current_a": round(self.rail_current, 3),
                "faults": list(self.power_faults),
            },
            "motors": [
                {
                    "id": m.id, "position": m.position, "enabled": m.enabled, "mode": m.mode,
                    "pwm": round(m.pwm, 3), "target_rpm": m.target_rpm, "manual_pwm": m.manual_pwm,
                    "rpm": round(m.meas_rpm, 1), "rpm_true": round(m.rpm, 1),
                    "current_a": round(m.supply_current, 3), "temp_c": round(m.temp, 1),
                    "ticks": int(math.floor(m.enc_ticks)), "current_limit_a": m.current_limit,
                    "faults": list(m.faults),
                }
                for m in self.motors
            ],
            "servo": {
                "id": s.id, "attached": s.attached, "target_deg": s.target, "trim_deg": s.trim,
                "commanded_deg": s.commanded, "actual_deg": round(s.actual, 2), "pulse_us": s.pulse_us,
                "current_a": round(s.current, 3), "temp_c": round(s.temp, 1), "moving": s.moving,
                "blocked": s.blocked, "speed_limit_dps": s.speed_limit, "faults": list(s.faults),
            },
            "motion": {
                "speed_mps": round(self.v_enc, 3),
                "yaw_rate_enc_dps": round(math.degrees(self.w_enc), 2),
                "gyro_z_dps": round(math.degrees(self.w), 2),
            },
            "system": {"cpu_load_pct": round(self.cpu_load, 1)},
            "params": self.params(),
            "packet_loss_effective": round(self.effective_packet_loss(), 1),
            "active_faults": self.active_faults(),
        }
