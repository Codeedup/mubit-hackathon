import asyncio
import json
import websockets

# 1. The simulation address (ws = websocket protocol)
URL = "ws://localhost:8000/ws/telemetry"


async def run():
  print("Connecting to robot...")

  # 2. Open the phone call
  async with websockets.connect(URL) as ws:
    print("Connected! Waiting for robot data...\n")

    # 3. As long as the robot sends data, this loop runs automatically
    async for message in ws:
      data = json.loads(message)

      # Check if it's a telemetry packet
      if data.get("type") == "telemetry":
        battery = data["power"]["battery_v"]
        servo_angle = data["servo"]["actual_deg"]
        front_left_rpm = data["motors"][0]["rpm"]
        front_left_temp = data["motors"][0]["temp_c"]

        print(
            f"Batt: {battery:.2f}V | Servo: {servo_angle:.1f}° | FL Motor:"
            f" {front_left_rpm:.0f} RPM | Temp: {front_left_temp:.1f}°C"
        )


# Start the script
asyncio.run(run())