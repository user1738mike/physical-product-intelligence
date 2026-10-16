"""Build prior application code with a patched runtime, without changing the checkout."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

from release import ROOT, image, run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{7,40}", args.revision):
        parser.error("Explicit existing commit SHA required")
    folder = args.directory.resolve()
    if not folder.is_relative_to(ROOT / "artifacts"):
        parser.error("Source export must remain in ignored artifacts")
    folder.mkdir(mode=0o700, parents=True)
    revision = run(["git", "rev-parse", "--verify", args.revision + "^{commit}"])
    archive = subprocess.check_output(["git", "archive", revision, "backend"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        if any(not (item.isfile() or item.isdir()) for item in source.getmembers()):
            parser.error("Only ordinary tracked files/directories accepted")
        source.extractall(folder, filter="data")
    dockerfile = folder / "backend" / "Dockerfile"
    text = dockerfile.read_text().replace("python:3.13.12-slim", "python:3.13.16-slim")
    text = text.replace(
        "WORKDIR /app",
        "WORKDIR /app\nRUN apt-get update && "
        "apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*",
    )
    dockerfile.write_text(text, encoding="utf-8")
    run(
        ["docker", "build", "-t", "ppi-phase8-previous", str(folder / "backend")],
        timeout=600,
    )
    result = {
        "source_revision": revision,
        "runtime_patch_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "image": image("ppi-phase8-previous"),
        "purpose": "isolated_prior_code_compatibility",
    }
    write_json(folder / "previous.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
