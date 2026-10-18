"""Build with the runner's existing proxy/CA when Docker cannot resolve its DNS.

Only build-time networking changes. Never prints credentials or copies the CA into
the image. For an ordinary workstation, use `docker compose build api` instead.
"""

import argparse
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("services", nargs="*", choices=("api", "web"))
    arguments = parser.parse_args()
    proxy = urlsplit(os.environ.get("HTTPS_PROXY", ""))
    if not proxy.hostname or not os.environ.get("SSL_CERT_FILE"):
        raise SystemExit("The cloud build requires an existing HTTPS_PROXY and SSL_CERT_FILE")
    environment = os.environ.copy()
    environment["CYCLESCOPE_PROXY_HOST"] = proxy.hostname
    environment["CYCLESCOPE_PROXY_IP"] = socket.gethostbyname(proxy.hostname)
    environment.setdefault("DOCKER_CONFIG", "/workspace/.cache/docker")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "compose.cloud.yml",
            "build",
            *(arguments.services or ["api"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        check=False,
    )
    raise SystemExit(result.returncode)
