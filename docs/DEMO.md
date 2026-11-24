# Two-minute demo

Start `python run.py --provider local_fixture --open` after installing backend
dependencies and building the frontend. Confirm the **Offline demo** badge.

| Time | Show |
| --- | --- |
| 0–20 s | Create a **Stopped wheel** demo case. Explain that its readings are synthetic. |
| 20–45 s | Inspect zero wheel speed and 1.8 A current. Select **Run offline diagnosis**. Show the cause, medium uncertainty, and cited reading. |
| 45–70 s | Follow the evidence link and read the next check. A technician decides what to inspect; the diagnosis does not control the robot. |
| 70–95 s | Record the accurately described simulated cause, check, fix, and your name. Show the saved outcome. |
| 95–110 s | Open **History & evaluation**, reload, and reopen the exact run from its ledger. Export the workspace. |
| 110–120 s | Explain the optional Mubit classification, reviewed feedback, and task status. No adapter improvement has been measured. |

For an ambiguous example, create **Missing evidence**. Expect **Cause unknown**,
high uncertainty, and a request for another measurement.

For simulator capture, open its dashboard and inject an N20 motor jam. A new
`SIM-*` case appears after fresh fault packets arrive. The injected label stays
in a separate answer key. Clear/reset the fault from the simulator dashboard
after observing it: a prolonged simulated stall can burn out the virtual motor.

For a live Mubit demo, rehearse one synthetic case first. Show the raw reply,
model ID, and request reference. Successful inference does not establish that a
call was kept for training. If the provider is unavailable, restart explicitly
in offline mode and identify that route to the audience.
