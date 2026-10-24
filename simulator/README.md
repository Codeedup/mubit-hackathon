# 🤖 Mubit Robot Telemetry Simulator (`bot-01`)

A local, synthetic real-time physics and firmware simulator for a 4-wheel skid-steer rover with an interactive web dashboard, live telemetry streaming, and fault injection. Designed so AI agents or monitoring services can connect, detect hardware/firmware anomalies from telemetry, and send recovery commands in real time.

---

## 🚀 Quick Start

Run from the repository root (`mubit-hackathon/`):

```bash
python3 -m simulator.server --host 127.0.0.1 --port 8001
```

- **Interactive Dashboard:** [http://localhost:8001](http://localhost:8001)
- **Live Telemetry WebSocket (for Agents/Listeners):** `ws://localhost:8001/ws/telemetry?name=my-agent`
- **Live Telemetry Snapshot (HTTP):** [http://localhost:8001/api/packet](http://localhost:8001/api/packet)
- **Full Protocol & Fault Schema (HTTP):** [http://localhost:8001/api/schema](http://localhost:8001/api/schema)

---

## 🔌 Architecture & Endpoints

| Endpoint | Method / Protocol | Purpose |
| :--- | :--- | :--- |
| `/` | `GET` | Interactive web dashboard (`simulator/static/index.html`) for visualizing metrics, moving sliders, and injecting faults. |
| `/ws/telemetry` | `WebSocket` | **Agent / Listener stream.** Streams `robot.telemetry.v1` JSON packets at `rate_hz` (default `10 Hz`). Agents can send `command`, `note`, or `ping` JSON messages back on this socket. Optional query param: `?name=agent-01`. |
| `/ws/ui` | `WebSocket` | Internal dashboard control channel (streams UI state at `20 Hz` and accepts `command` and `sim` messages). |
| `/api/packet` | `GET` | Returns the latest `robot.telemetry.v1` JSON packet. |
| `/api/schema` | `GET` | Returns machine-readable documentation of all telemetry fields, valid commands, and faults. |
| `/api/command` | `POST` | Send a robot recovery command (or sim action) over HTTP JSON. |
| `/api/sim` | `POST` | Inject/clear faults or change simulation parameters over HTTP JSON. |

---

## 📦 Telemetry Packet Format (`robot.telemetry.v1`)

Every packet received on `/ws/telemetry` or `GET /api/packet` has the following structure:

```json
{
  "type": "telemetry",
  "schema": "robot.telemetry.v1",
  "robot_id": "bot-01",
  "firmware": "1.4.2",
  "boot_id": 1,
  "seq": 142,
  "ts": "2026-10-23T20:14:57.763Z",
  "uptime_s": 14.2,
  "power": {
    "battery_v": 8.014,
    "battery_current_a": 0.898,
    "battery_power_w": 7.21,
    "soc_pct": 85.0,
    "battery_temp_c": 21.9,
    "rail_5v_v": 4.995,
    "rail_5v_current_a": 0.216
  },
  "motors": [
    {
      "id": "n20_fl",
      "position": "front_left",
      "enabled": true,
      "mode": "pid",
      "pwm": 0.42,
      "target_rpm": 150.0,
      "rpm": 149.8,
      "current_a": 0.142,
      "current_limit_a": null,
      "encoder_ticks": 1650,
      "temp_c": 23.4
    }
  ],
  "servo": {
    "id": "servo_arm",
    "attached": true,
    "target_deg": 90.0,
    "trim_deg": 0.0,
    "commanded_deg": 90.0,
    "actual_deg": 90.0,
    "pulse_us": 1500,
    "moving": false,
    "speed_limit_dps": null,
    "current_a": 0.068,
    "temp_c": 22.1
  },
  "motion": {
    "speed_mps": 0.338,
    "yaw_rate_dps": 0.0,
    "odom_x_m": 1.24,
    "odom_y_m": 0.0,
    "odom_heading_deg": 0.0
  },
  "imu": {
    "accel_x_g": 0.012,
    "accel_y_g": -0.003,
    "accel_z_g": 0.998,
    "gyro_x_dps": 0.05,
    "gyro_y_dps": -0.11,
    "gyro_z_dps": 0.14,
    "pitch_deg": 0.0,
    "roll_deg": 0.1
  },
  "system": {
    "mcu_temp_c": 37.2,
    "cpu_load_pct": 34.1,
    "loop_dt_ms": 10.15,
    "wifi_rssi_dbm": -55,
    "reset_count": 0,
    "last_reset_reason": "power_on",
    "estop": false
  }
}
```

> **Ground Truth Mode:** If `comms.ground_truth` is enabled in the dashboard (or via `POST /api/sim`), packets also include a `_ground_truth` object with `healthy`, `active_faults`, and `true_values` (such as true un-encoded wheel RPM).

---

## 🛠️ Sending Commands to the Robot (Agent / Listener API)

Agents can send commands either over the `/ws/telemetry` WebSocket connection or via `POST http://localhost:8001/api/command`.

### Command Payload Format

```json
{
  "type": "command",
  "target": "robot | all_motors | n20_fl | n20_fr | n20_rl | n20_rr | servo_arm",
  "action": "<action_name>",
  "value": 0.5,
  "reason": "Optional diagnosis/explanation logged on dashboard"
}
```

### Supported Targets & Actions

| Target | Action | `value` | Description |
| :--- | :--- | :--- | :--- |
| `robot` | `estop` | `null` | Emergency-stops all motors immediately. |
| `robot` | `resume` | `null` | Clears E-STOP and re-enables all motors. |
| `robot` | `reboot` | `null` | Reboots the MCU (`boot_id` +1, resets volatile trims/targets). |
| `n20_fl`, `n20_fr`, `n20_rl`, `n20_rr`, or `all_motors` | `set_target_rpm` | `-400..400` | Sets closed-loop PI target speed (`mode = "pid"`). |
| *(motors)* | `set_pwm` | `-1.0..1.0` | Switches motor to open-loop manual duty cycle (`mode = "manual"`). |
| *(motors)* | `set_mode` | `"pid" \| "manual"` | Switches control mode (`manual` performs bumpless PWM transfer). |
| *(motors)* | `set_current_limit` | `0.05..2.0` (or `null`) | Sets current-limit foldback in Amps to prevent overheating/stall damage. |
| *(motors)* | `stop` | `null` | Sets target RPM and manual PWM to `0`. |
| *(motors)* | `enable` / `disable` | `null` | Enables or disables H-bridge driver for the motor. |
| `servo_arm` (or `servo`) | `set_target` | `0..180` | Commands arm target angle in degrees. |
| `servo_arm` | `set_trim` | `-30..30` | Adjusts calibration offset in degrees (`commanded = target + trim`). |
| `servo_arm` | `set_speed_limit` | `5..600` (or `null`) | Caps servo slew rate in deg/s to reduce 5V rail current spikes. |
| `servo_arm` | `attach` / `detach` | `null` | Enables or disables PWM output to the servo. |
| `servo_arm` | `reattach` | `null` | Re-initializes the PWM peripheral (clears `signal_loss` fault) and attaches. |

### Logging Agent Notes to the Dashboard

Over `/ws/telemetry`, an agent can also send a free-text diagnosis note that appears in the dashboard's **System & AI Repair Log**:

```json
{
  "type": "note",
  "text": "Detected stall on n20_fl (0.98A, 0 RPM). Reversing motor to clear mechanical jam."
}
```

---

## ⚠️ Fault Reference: Symptoms & Software Mitigations

Faults can be toggled in the web UI or injected programmatically via `POST /api/sim`. When a fault is injected on an idle actuator, the simulator automatically engages drive/load so its physical symptoms immediately appear in telemetry.

### 1. Motor Faults (`n20_fl`, `n20_fr`, `n20_rl`, `n20_rr`)

| Fault | Telemetry Symptoms | Recommended Agent Mitigation |
| :--- | :--- | :--- |
| `jam` | `rpm ≈ 0`, `pwm` saturates to `±1.0`, `current_a` spikes to stall (`~0.95A`), `temp_c` climbs rapidly toward `115°C` burnout. | Drive in **reverse** (`set_pwm` with `abs(pwm) > 0.3` in opposite sign of jam direction) for `>= 0.4s` to mechanically unjam, then restore normal drive. |
| `encoder_failure` | `rpm` drops to `0` and `encoder_ticks` freezes while `pwm` winds up to `±1.0` in `pid` mode (causing true wheel runaway and yaw/imu mismatch). | Switch motor from closed-loop PI to open-loop PWM: `set_pwm` (e.g. `0.3`–`0.5`) or `set_mode` to `"manual"`. |
| `overheat` | Elevated friction + degraded cooling causes `current_a` and `temp_c` to rise steadily toward `115°C` (where it permanently triggers `burned_out`). | Reduce load: apply `set_current_limit` (e.g. `0.25A`), lower `set_target_rpm` / `set_pwm`, or `disable` the motor until `temp_c` cools. |
| `disconnected` | Broken motor wire: `pwm` is non-zero (`~1.0`), but `current_a ≈ 0.004A` and `rpm == 0`. | Hardware wire break — send `disable` (or `stop`) on that motor. |
| `burned_out` *(consequence)* | Triggered automatically if `temp_c > 115°C`. Motor is permanently dead (`0A`, `0 RPM`). | Prevent by mitigating `jam`/`overheat` before `115°C`. Can be replaced from the dashboard (click `burned_out` badge or `clear_fault`). |

### 2. Servo Faults (`servo_arm`)

| Fault | Telemetry Symptoms | Recommended Agent Mitigation |
| :--- | :--- | :--- |
| `jam` | Arm physically blocked away from `target_deg` (`abs(target_deg - actual_deg) > 1°`), `current_a` jumps to stall (`0.75A`), `temp_c` rises. | Stop pushing against the obstacle: send `set_target` equal to `actual_deg`. |
| `jitter` | `actual_deg` oscillates (`±3–5°`), `pulse_us` fluctuates, and `current_a` spikes (`0.2–0.45A`). | Send `detach` when the arm is idle, or apply `set_speed_limit`. |
| `calibration_drift` | Potentiometer offset: arm settles at a constant offset (`actual_deg != target_deg`) with normal holding current. | Compensate trim: send `set_trim` with `trim_deg - (actual_deg - target_deg)`. |
| `signal_loss` | `pulse_us == 0`, `commanded_deg == null`, `current_a ≈ 0.004A`, and `actual_deg` sags toward `0°` under load. | Re-initialize servo PWM peripheral: send `reattach` to `servo_arm`. |

### 3. Power Faults (`power`)

| Fault | Telemetry Symptoms | Recommended Agent Mitigation |
| :--- | :--- | :--- |
| `battery_aging` | Degraded pack with high internal resistance: `battery_v` sags heavily (`< 7.0V`) under motor current load. | Reduce total current draw: lower motor speeds (`set_target_rpm`) or apply `set_current_limit` across `all_motors`. |
| `brownout` | Weak 5V buck regulator: `rail_5v_v` sags below `4.25V` under 5V load; after `1.5s` the MCU resets (`boot_id` increments, `last_reset_reason == "brownout"`). | Reduce 5V rail load: send `detach` (or `set_speed_limit`) on `servo_arm`. |

---

## 🧪 Programmatic Fault Injection (`POST /api/sim`)

You can inject or clear faults from scripts, tests, or other agents via HTTP:

```bash
# Inject a fault (motor: jam | encoder_failure | overheat | disconnected)
#                (servo_arm: jam | jitter | calibration_drift | signal_loss)
#                (power: battery_aging | brownout)
curl -X POST http://localhost:8001/api/sim \
  -H "Content-Type: application/json" \
  -d '{"action": "inject_fault", "component": "n20_fl", "fault": "jam"}'

# Clear a specific fault
curl -X POST http://localhost:8001/api/sim \
  -H "Content-Type: application/json" \
  -d '{"action": "clear_fault", "component": "n20_fl", "fault": "jam"}'

# Clear all active faults
curl -X POST http://localhost:8001/api/sim \
  -H "Content-Type: application/json" \
  -d '{"action": "clear_all_faults"}'

# Reset the entire simulation
curl -X POST http://localhost:8001/api/sim \
  -H "Content-Type: application/json" \
  -d '{"action": "reset"}'
```

---

## 🐍 Minimal Python Agent Example

See [`simulator/listen.py`](simulator/listen.py) for a basic listener, or use this template to both read telemetry and send repair commands:

```python
import asyncio
import json
import websockets

URL = "ws://localhost:8001/ws/telemetry?name=repair-agent"

async def main():
    async with websockets.connect(URL) as ws:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") != "telemetry":
                continue

            # Example: detect servo signal loss and fix it
            servo = msg["servo"]
            if servo["attached"] and servo["pulse_us"] == 0:
                await ws.send(json.dumps({
                    "type": "command",
                    "target": "servo_arm",
                    "action": "reattach",
                    "reason": "Restoring lost PWM signal on servo_arm"
                }))

asyncio.run(main())
```
