"""Run real sandboxed Chromium with a test-only CA store. Never weakens TLS or reads API keys."""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

from release import ROOT, compose, image, source_identity, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder, output = args.directory.resolve(), args.output.resolve()
    if not all(p.is_relative_to(ROOT / "artifacts") for p in (folder, output)):
        parser.error("Only isolated ignored rehearsal/evidence directories accepted")
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    compose(folder, manifest)  # Enforces generated project/database identity before execution.
    fixture = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    if os.name == "posix":
        output.chmod(
            0o777
        )  # Fresh synthetic results only; credentials travel on stdin, never here.
    name = "ppi-browser-" + secrets.token_hex(5)
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "-i",
        "--name",
        name,
        "--network",
        manifest["project"] + "_default",
        "--shm-size=512m",
        "--memory=2g",
        "--cpus=2",
        "--security-opt",
        "seccomp=" + str(ROOT / "browser-tests/seccomp_profile.json"),
        "-v",
        str(folder / "ca.crt") + ":/rehearsal-ca.crt:ro",
        "-v",
        str(output) + ":/results",
        "ppi-phase8b-browser",
    ]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(fixture),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        code, log = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "stop", "-t", "5", name], capture_output=True, check=False)
        code, log = 1, "Browser acceptance exceeded its ten-minute bound."
    private = [fixture[role]["password"] for role in ("owner", "outsider")]
    for password in private:
        log = log.replace(password, "[redacted-synthetic-password]")
    (output / "browser.log").write_text(log, encoding="utf-8")
    raw_report = output / "browser.json"
    if raw_report.exists():
        text = raw_report.read_text(encoding="utf-8")
        for password in private:
            text = text.replace(password, "[redacted-synthetic-password]")
        sanitized = output / "sanitized-browser.json"
        sanitized.write_text(text, encoding="utf-8")
        sanitized.replace(raw_report)
    receipt = output / "acceptance.json"
    passed = (
        code == 0 and receipt.exists() and json.loads(receipt.read_text())["status"] == "passed"
    )
    write_json(
        output / "execution.json",
        {
            "status": "passed" if passed else "failed",
            "exit_code": code,
            "source": source_identity(),
            "release_images": manifest["images"],
            "browser_runner_image": image("ppi-phase8b-browser"),
            "base_url": "https://edge:8443",
            "certificate_errors_ignored": False,
            "chromium_sandbox": True,
            "live_ai_calls": 0,
        },
    )
    print(json.dumps({"status": "passed" if passed else "failed", "evidence": str(output)}))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
