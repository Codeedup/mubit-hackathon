"""Start the built local app and optional simulator: python run.py --open."""

import argparse
import os
from pathlib import Path
import socket
import threading
import webbrowser


ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--simulator-port", type=int, default=8001)
    parser.add_argument("--no-simulator", action="store_true")
    parser.add_argument("--provider", choices=["local_fixture", "mubit", "openrouter", "unavailable"])
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    args = parser.parse_args()
    if not (ROOT / "frontend/dist/index.html").exists():
        parser.error("Build the UI first: cd frontend, then npm ci and npm run build.")
    for port in [args.port] + ([] if args.no_simulator else [args.simulator_port]):
        if not 1 <= port <= 65535:
            parser.error("Ports must be between 1 and 65535.")
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                parser.error(f"Port {port} is already in use. Stop the other process or choose another port.")
    if not args.no_simulator and args.port == args.simulator_port:
        parser.error("App and simulator need different ports.")
    if args.provider:
        os.environ["ROBO_MEDIC_PROVIDER"] = args.provider
    if not args.no_simulator:
        os.environ["ROBO_MEDIC_SIMULATOR_URL"] = f"http://127.0.0.1:{args.simulator_port}"
    try:
        import uvicorn
        from backend.app.main import app
    except ModuleNotFoundError as exc:
        parser.error(f"Missing dependency {exc.name}. Install backend/requirements.txt in your virtual environment.")
    simulator_server = None
    simulator_thread = None
    try:
        if not args.no_simulator:
            simulator_server = uvicorn.Server(
                uvicorn.Config("simulator.server:app", host="127.0.0.1", port=args.simulator_port, log_level="warning")
            )
            simulator_thread = threading.Thread(target=simulator_server.run, name="robot-simulator", daemon=True)
            simulator_thread.start()
        print(f"\nRobo Medic: http://127.0.0.1:{args.port}", flush=True)
        print(f"API reference: http://127.0.0.1:{args.port}/docs", flush=True)
        if simulator_server:
            print(f"Simulator: http://127.0.0.1:{args.simulator_port}", flush=True)
        if args.open:
            threading.Timer(1.0, webbrowser.open, args=(f"http://127.0.0.1:{args.port}",)).start()
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False)
    finally:
        if simulator_server and simulator_thread:
            simulator_server.should_exit = True
            simulator_thread.join(timeout=5)


if __name__ == "__main__":
    main()
