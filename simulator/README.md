# 🤖 Robot Telemetry Simulator

A simple robot hardware simulator with an interactive web dashboard.

---

## 🚀 How to Run

```bash
python3 -m simulator.server --port 8000
```

---

## 🖥️ How to See the JSON (3 Simple Ways)

1. **Directly in the Web Dashboard UI:**
   Open **[http://localhost:8000](http://localhost:8000)** in your browser.
   On the right-hand side is the **"Latest Telemetry Packet"** box. It updates in real-time as you move sliders or click fault buttons.

2. **In your Browser via URL:**
   Open **[http://localhost:8000/api/packet](http://localhost:8000/api/packet)** in any browser tab to view the live JSON snapshot.

3. **In the Terminal via curl:**
   ```bash
   curl -s http://localhost:8000/api/packet
   ```

---

## 📦 What the JSON Contains

- **`power`**: Battery voltage (`battery_v`), current (`battery_current_a`), 5V regulator rail (`rail_5v_v`), and state of charge (`soc_pct`).
- **`motors`**: 4 N20 gear motors (`n20_fl`, `n20_fr`, `n20_rl`, `n20_rr`): `rpm`, `target_rpm`, `pwm`, `current_a`, `temp_c`.
- **`servo`**: Measured arm angle (`actual_deg`, 0–180°), `target_deg`, `current_a`.
- **`imu`**: 6-axis `accel` (x, y, z) and `gyro` (x, y, z).
- **`system`**: Microcontroller temperature, CPU load, and Wi-Fi signal.
