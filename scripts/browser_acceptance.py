"""Run real sandboxed Chromium with a test-only CA store. Never weakens TLS or reads API keys."""

import argparse
import json
import os
import secrets
import subprocess
import threading
from pathlib import Path

from release import ROOT, compose, image, run, source_identity, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commercial-fixtures", action="store_true")
    parser.add_argument("--billing-fixtures", action="store_true")
    args = parser.parse_args()
    folder, output = args.directory.resolve(), args.output.resolve()
    if not all(p.is_relative_to(ROOT / "artifacts") for p in (folder, output)):
        parser.error("Only isolated ignored rehearsal/evidence directories accepted")
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    compose(folder, manifest)  # Enforces generated project/database identity before execution.
    fixture = json.loads((folder / "journey.json").read_text(encoding="utf-8"))
    if args.commercial_fixtures:
        fixture["commercial"] = json.loads(
            run(
                compose(folder, manifest)
                + [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "migration",
                    "python",
                    "manage.py",
                    "prepare_commercial_acceptance",
                    "--owner",
                    fixture["owner"]["username"],
                    "--member",
                    fixture["outsider"]["username"],
                ]
            )
        )
    output.mkdir(parents=True, exist_ok=False)
    billing_result = {"status": "not_requested"}
    stop = threading.Event()
    processor = None
    if args.billing_fixtures:
        fixture["billing"] = json.loads(
            run(
                compose(folder, manifest)
                + [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "migration",
                    "python",
                    "manage.py",
                    "prepare_billing_acceptance",
                    "--owner",
                    fixture["owner"]["username"],
                    "--member",
                    fixture["outsider"]["username"],
                ]
            )
        )

        def process_confirmation():
            while not stop.wait(0.2):
                if not (output / "billing-confirmation-request.json").is_file():
                    continue
                try:
                    # Scope comes only from guarded fixture output, never a browser-supplied ID.
                    result = json.loads(
                        run(
                            compose(folder, manifest)
                            + [
                                "run",
                                "--rm",
                                "--no-deps",
                                "-T",
                                "migration",
                                "python",
                                "manage.py",
                                "billing",
                                "process",
                                "--actor",
                                fixture["billing"]["operator"],
                                "--organization",
                                fixture["billing"]["pending"]["org"],
                                "--reason",
                                "Synthetic delayed browser confirmation",
                                "--limit",
                                "10",
                                "--apply",
                            ],
                            timeout=90,
                        )
                    )
                    billing_result.update(status="passed", result=result)
                except Exception:
                    billing_result.update(status="failed", reason="bounded_processor_failed")
                write_json(output / "billing-processing.json", billing_result)
                if os.name == "posix":
                    (output / "billing-processing.json").chmod(
                        0o666
                    )  # Sanitized synthetic IDs/status only.
                return

        processor = threading.Thread(target=process_confirmation, daemon=True)
        processor.start()
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
    finally:
        stop.set()
        if processor:
            processor.join(timeout=2)
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
        code == 0
        and receipt.exists()
        and json.loads(receipt.read_text())["status"] == "passed"
        and (not args.billing_fixtures or billing_result["status"] == "passed")
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
            "real_payment_requests": 0,
            "billing_processor": billing_result,
        },
    )
    print(json.dumps({"status": "passed" if passed else "failed", "evidence": str(output)}))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
