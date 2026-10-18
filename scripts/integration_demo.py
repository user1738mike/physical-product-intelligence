"""Run only the guarded local integration demonstration; write a secret-free receipt."""

import argparse
import json

from release import ROOT, compose, exclusive, run, source_identity, write_json


def demonstrate(command, supervised):
    running = (
        supervised
        and "processors" in run(command + ["ps", "--status", "running", "--services"]).splitlines()
    )
    try:
        # The guarded demonstration owns a loopback sender for reserved.example;
        # the normal dispatcher must not race its deliberately local claim.
        if running:
            run(command + ["stop", "processors"], timeout=300)
        return json.loads(
            run(
                command
                + [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "migration",
                    "python",
                    "manage.py",
                    "demonstrate_integrations",
                    "--ca",
                    "/certs/ca.crt",
                ],
                timeout=180,
            ).splitlines()[-1]
        )
    finally:
        if running:
            run(
                command + ["up", "-d", "--wait", "--wait-timeout", "120", "processors"], timeout=180
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    folder, output = (ROOT / args.directory).resolve(), (ROOT / args.output).resolve()
    if not all(path.is_relative_to(ROOT / "artifacts") for path in (folder, output)):
        parser.error("Only isolated ignored rehearsal/evidence paths accepted")
    manifest = json.loads((folder / "release.json").read_text())
    command = compose(folder, manifest)
    output.mkdir(parents=True, exist_ok=False)
    with exclusive(folder):
        result = demonstrate(command, manifest.get("processors_enabled", False))
    write_json(
        output / "receipt.json",
        {"source": source_identity(), "images": manifest["images"], "demonstration": result},
    )
    print(json.dumps({"status": result["status"], "receipt": str(output / "receipt.json")}))


if __name__ == "__main__":
    main()
