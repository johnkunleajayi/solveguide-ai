"""Check frozen localhost startup without inheriting credentials or a Python environment."""

import argparse
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    bundle = args.bundle.resolve()
    if not bundle.is_relative_to(root):
        parser.error("bundle must be inside the official project")
    if any(
        path.name.startswith(".env") for path in bundle.rglob("*") if path.is_file()
    ):
        raise RuntimeError("A dotenv file must not be included in the distribution")
    scratch = root / ".cache" / "backend-package" / "smoke"
    scratch.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC"}
    }
    env.update(
        TEMP=str(scratch),
        TMP=str(scratch),
        LOCALAPPDATA=str(scratch),
        CONTEXT_STORAGE_DIRECTORY=str(scratch / "documents"),
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with (scratch / "startup.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(bundle / "solveguide-backend.exe"), "--port", str(port)],
            cwd=bundle,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Executable exited; inspect .cache/backend-package/smoke/startup.log"
                    )
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=1
                    ) as response:
                        data = json.load(response)
                    assert data == {
                        "status": "ok",
                        "vision": {"provider": "openai", "configured": False},
                        "database": {"configured": False},
                        "authentication": {"configured": False},
                    }
                    print(
                        "PASS: frozen backend health OK; no Python environment or credentials inherited."
                    )
                    return
                except (OSError, URLError):
                    time.sleep(0.2)
            raise RuntimeError("Frozen backend startup exceeded 60 seconds")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
