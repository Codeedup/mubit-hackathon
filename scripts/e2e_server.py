"""Give browser checks a temporary workspace, never the operator's local data."""

import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="robo-medic-e2e-") as directory:
        temporary = Path(directory)
        shutil.copytree(ROOT / "data/incidents", temporary / "incidents")
        os.environ.update({
            "ROBO_MEDIC_PROVIDER": "local_fixture",
            "ROBO_MEDIC_DB_PATH": str(temporary / "demo.sqlite3"),
            "ROBO_MEDIC_INCIDENT_DIR": str(temporary / "incidents"),
            "ROBO_MEDIC_CAPTURED_KEYS_DIR": str(temporary / "keys"),
            "ROBO_MEDIC_SIMULATOR_URL": "http://127.0.0.1:1",
            "MUBIT_API_KEY": "", "MUBIT_MANAGEMENT_KEY": "", "MUBIT_TASK_ID": "",
        })
        from run import main as run_app
        run_app()


if __name__ == "__main__":
    main()
