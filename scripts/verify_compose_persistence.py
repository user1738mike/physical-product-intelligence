"""Compare catalog counts/private checksums across a normal project stop/start; no deletion."""

import argparse
import json
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-restart", action="store_true", required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    args = parser.parse_args()
    compose = ["docker", "compose"]
    for path in args.compose_file:
        compose += ["-f", path]
    code = (
        "import django; django.setup(); import hashlib,json; "
        "from operations.recovery import counts; from ingestion.models import ImportJob; "
        "from ingestion.storage import read_upload; "
        "print(json.dumps({'counts':counts(),'files':sorted("
        "hashlib.sha256(read_upload(j)).hexdigest() for j in "
        "ImportJob.objects.filter(mode='deterministic'))}))"
    )

    def snapshot():
        return json.loads(
            subprocess.check_output(
                compose + ["exec", "-T", "backend", "python", "-c", code],
                text=True,
                timeout=60,
            )
        )

    before = snapshot()
    subprocess.run(compose + ["stop"], check=True, timeout=120)
    subprocess.run(
        compose + ["up", "-d", "--wait", "--wait-timeout", "180"],
        check=True,
        timeout=240,
    )
    assert before == snapshot(), "Record counts or private bytes changed across restart"
    print(
        json.dumps(
            {
                "status": "restart_persistence_verified",
                "models": len(before["counts"]),
                "private_files": len(before["files"]),
                "deletions": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
