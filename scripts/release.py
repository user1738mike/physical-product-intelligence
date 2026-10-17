"""Data-preserving single-host release rehearsal; no remote transport/publish/live AI commands."""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(Exception):
    pass


def run(args, timeout=180, env=None):
    try:
        return subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError) as error:
        diagnostic = str(getattr(error, "stderr", "") or "").lower()
        category = next(
            (
                name
                for marker, name in (
                    ("improperlyconfigured", "configuration"),
                    ("operationalerror", "database_connection"),
                    ("modulenotfound", "application_import"),
                    ("permission denied", "permission"),
                    ("unhealthy", "dependency_health"),
                    ("commanderror", "command_guard"),
                )
                if marker in diagnostic
            ),
            "process_or_timeout",
        )
        raise ReleaseError(
            f"Step failed ({category}); sensitive subprocess output suppressed"
        ) from None


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def image(reference):
    return json.loads(run(["docker", "image", "inspect", "--format", "{{json .Id}}", reference]))


def source_identity():
    paths = run(["git", "ls-files", "--cached", "--others", "--exclude-standard"]).splitlines()
    hashed = hashlib.sha256()
    for name in sorted(set(paths)):
        path = ROOT / name
        if path.is_file():
            hashed.update(name.encode() + b"\0" + path.read_bytes())
    return {
        "revision": run(["git", "rev-parse", "HEAD"]),
        "dirty": bool(run(["git", "status", "--porcelain"])),
        "working_tree_sha256": hashed.hexdigest(),
        "lockfiles": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "backend/requirements.lock",
                "backend/requirements-ai.lock",
                "frontend/package-lock.json",
            )
        },
    }


@contextmanager
def exclusive(folder):
    lock = folder / "release.lock"
    try:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        raise ReleaseError(
            "Release lock exists; inspect owner, never automatically break it"
        ) from None
    try:
        yield
    finally:
        lock.unlink()


def envfile(path, values):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)


def available_port(port):
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise ReleaseError(
                "Requested loopback port is occupied; preserve its listener"
            ) from None


def prepare(folder, port=18443, processors=False):
    available_port(port)
    if folder.exists():
        raise ReleaseError("Preparation requires a new exclusive directory")
    folder.mkdir(mode=0o700, parents=True)
    token = secrets.token_hex(5)
    subnet_file = folder / "network.json"
    run([sys.executable, "scripts/compose_network.py", "--output", str(subnet_file)])
    network = json.loads(subnet_file.read_text())["networks"]["default"]["ipam"]["config"][0][
        "subnet"
    ]
    edge = str(ipaddress.ip_network(network).network_address + 10)
    override = json.loads(subnet_file.read_text())
    override["services"] = {"edge": {"networks": {"default": {"ipv4_address": edge}}}}
    write_json(subnet_file, override)
    runtime_password, admin_password = secrets.token_hex(32), secrets.token_hex(32)
    common = {
        "DJANGO_SECRET_KEY": secrets.token_hex(48),
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,edge",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://127.0.0.1:{port},https://localhost:{port}",
        "DJANGO_TRUST_PROXY": "true",
        "TRUSTED_PROXY_CIDRS": edge + "/32",
        "POSTGRES_DB": "ppi_rehearsal_" + token,
        "POSTGRES_HOST": "db",
        "POSTGRES_PORT": "5432",
        "POSTGRES_SSLROOTCERT": "/certs/ca.crt",
        "INGESTION_SCANNER": "ingestion.scanning.clamd_scan",
        "CLAMD_HOST": "scanner",
        "AI_EXTRACTION_ENABLED": "false",
        "PPI_REHEARSAL_FIXTURES": "synthetic-only",
    }
    if processors:
        common["PPI_PROCESSOR_ACTOR"] = "ppi-processor-" + token
    runtime_role = "ppi_runtime_" + token
    envfile(
        folder / "runtime.env",
        {
            **common,
            "POSTGRES_USER": runtime_role,
            "POSTGRES_PASSWORD": runtime_password,
        },
    )
    envfile(
        folder / "migration.env",
        {
            **common,
            "POSTGRES_USER": "ppi_migration",
            "POSTGRES_PASSWORD": admin_password,
            "PPI_RUNTIME_ROLE": runtime_role,
            "PPI_RUNTIME_PASSWORD": runtime_password,
        },
    )
    envfile(
        folder / "database.env",
        {
            "POSTGRES_DB": common["POSTGRES_DB"],
            "POSTGRES_USER": "ppi_migration",
            "POSTGRES_PASSWORD": admin_password,
        },
    )
    images = {
        "backend": image("physical-product-intelligence-backend"),
        "frontend": image("physical-product-intelligence-frontend"),
        "postgres": image("postgres:17.11-bookworm"),
        "ingress": image("nginx:1.30.4"),
        "scanner": image("clamav/clamav:stable"),
    }
    values = {"PPI_" + key.upper() + "_IMAGE": value for key, value in images.items()}
    values.update(
        {
            "PPI_PRODUCTION_ENV_FILE": (folder / "runtime.env").as_posix(),
            "PPI_MIGRATION_ENV_FILE": (folder / "migration.env").as_posix(),
            "PPI_DB_ENV_FILE": (folder / "database.env").as_posix(),
            "PPI_API_BACKEND_ORIGIN": "https://edge:8443",
            "PPI_HTTPS_PORT": str(port),
            "PPI_REHEARSAL_STATE_DIR": folder.as_posix(),
        }
    )
    if processors:
        values["PPI_PROCESSOR_ACTOR"] = common["PPI_PROCESSOR_ACTOR"]
        write_json(
            folder / "processors.json",
            {
                "services": {
                    "processors": {
                        "environment": {"DJANGO_SETTINGS_MODULE": "config.settings.rehearsal"},
                        "volumes": ["rehearsal_tls:/certs:ro"],
                    }
                }
            },
        )
    envfile(folder / "compose.env", values)
    manifest = {
        "format": "ppi-release-v1",
        "target": "isolated-local-rehearsal",
        "processors_enabled": processors,
        "project": "ppi-rehearsal-" + token,
        "database": common["POSTGRES_DB"],
        "created_at": datetime.now(UTC).isoformat(),
        "source": source_identity(),
        "images": images,
        "ai_mode": "recorded_synthetic_no_network",
        "hosted_ci_for_working_tree": "not_executed",
        "production_deployed": False,
        "events": [],
    }
    write_json(folder / "release.json", manifest)
    return manifest


def compose(folder, manifest):
    if not re.fullmatch(r"ppi-rehearsal-[a-f0-9]{10}", manifest["project"]):
        raise ReleaseError("Refusing unknown target identity")
    if manifest["database"] != "ppi_rehearsal_" + manifest["project"].removeprefix(
        "ppi-rehearsal-"
    ):
        raise ReleaseError("Project/database identity mismatch")
    command = [
        "docker",
        "compose",
        "--env-file",
        str(folder / "compose.env"),
        "-p",
        manifest["project"],
        "-f",
        "compose.production.yaml",
        "-f",
        "compose.rehearsal.yaml",
        "-f",
        str(folder / "network.json"),
    ]
    if manifest.get("processors_enabled"):
        command += ["-f", "compose.processors.yaml", "-f", str(folder / "processors.json")]
    if manifest.get("active_override"):
        name = manifest["active_override"]
        if not re.fullmatch(r"app-[a-f0-9]{12}\.json", name):
            raise ReleaseError("Invalid application override identity")
        command += ["-f", str(folder / name)]
    return command


def runtime_probe(folder, command, extra=None):
    values = dict(line.split("=", 1) for line in (folder / "runtime.env").read_text().splitlines())
    process_env = {**os.environ, "POSTGRES_PASSWORD": values["POSTGRES_PASSWORD"]}
    output = run(
        command
        + [
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-e",
            "POSTGRES_USER=" + values["POSTGRES_USER"],
            "-e",
            "POSTGRES_PASSWORD",
            *(extra or []),
            "migration",
            "python",
            "manage.py",
            "verify_release_access",
            "--context",
            "/release-state/journey.json",
        ],
        env=process_env,
    )
    return json.loads(output.splitlines()[-1])


def completed_backup(manifest):
    records = [
        event
        for event in manifest["events"]
        if event["action"] == "backup" and event["status"] == "passed"
    ]
    if not records:
        raise ReleaseError("A completed quiesced backup is required before release/restore")
    return records[-1]["bundle"]


def operate(folder, action, previous_image=None):
    manifest = json.loads((folder / "release.json").read_text(encoding="utf-8"))
    command = compose(folder, manifest)
    writers = ["edge", "frontend", "backend"] + (
        ["processors"] if manifest.get("processors_enabled") else []
    )
    stop_timeout = 300 if manifest.get("processors_enabled") else 120
    with exclusive(folder):
        run(command + ["config", "--quiet"])
        started = time.monotonic()
        event = {
            "action": action,
            "at": datetime.now(UTC).isoformat(),
            "status": "failed",
        }
        try:
            if action == "start":
                run(
                    command + ["up", "-d", "--wait", "--wait-timeout", "90", "db"],
                    timeout=120,
                )
                run(command + ["up", "-d", "scanner"], timeout=120)
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
                        "release_migrate",
                        "--confirm-database",
                        manifest["database"],
                    ]
                )
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
                        "bootstrap_rehearsal",
                    ]
                )
                run(
                    command + ["up", "-d", "--wait", "--wait-timeout", "480"],
                    timeout=540,
                )
                # Export public CA only. Private keys never leave their protected named volume.
                run(command + ["cp", "db:/certs/ca.crt", str(folder / "ca.crt")])
            elif action == "backup":
                run(command + ["stop", *writers], timeout=stop_timeout)
                bundle = "/var/lib/ppi/backups/" + secrets.token_hex(6)
                receipt = run(
                    command
                    + [
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        "migration",
                        "python",
                        "manage.py",
                        "backup_bundle",
                        "--maintenance-window",
                        "--confirm-database",
                        manifest["database"],
                        "--output",
                        bundle,
                    ]
                )
                event.update({"bundle": bundle, "receipt": json.loads(receipt)})
                run(
                    command + ["up", "-d", "--wait", "--wait-timeout", "120"],
                    timeout=180,
                )
            elif action == "restart":
                run(command + ["stop"], timeout=stop_timeout)
                run(
                    command + ["up", "-d", "--wait", "--wait-timeout", "240"],
                    timeout=300,
                )
            elif action == "status":
                event["operational_status"] = json.loads(
                    run(
                        command
                        + [
                            "exec",
                            "-T",
                            "backend",
                            "python",
                            "manage.py",
                            "operational_status",
                        ]
                    )
                )
            elif action == "verify":
                event["verification"] = runtime_probe(folder, command)
            elif action == "restore":
                bundle = completed_backup(manifest)
                token = secrets.token_hex(5)
                target = "ppi_restore_" + token
                private = "/var/lib/ppi/restores/" + token + "/private"
                run(command + ["exec", "-T", "db", "createdb", "-U", "ppi_migration", target])
                extra = [
                    "-e",
                    "POSTGRES_DB=" + target,
                    "-e",
                    "INGESTION_STORAGE_ROOT=" + private,
                    "-e",
                    "DJANGO_SETTINGS_MODULE=config.settings.production",
                ]
                output = run(
                    command
                    + [
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        *extra,
                        "migration",
                        "python",
                        "manage.py",
                        "restore_bundle",
                        "--bundle",
                        bundle,
                        "--confirm-target-database",
                        target,
                        "--media-target",
                        private,
                    ]
                )
                event["receipt"] = json.loads(output.splitlines()[-1])
                run(
                    command
                    + [
                        "run",
                        "--rm",
                        "--no-deps",
                        "-T",
                        *extra,
                        "migration",
                        "python",
                        "manage.py",
                        "bootstrap_rehearsal",
                    ]
                )
                event["verification"] = runtime_probe(folder, command, extra)
                event["isolated_database"] = target
                event["private_root"] = private
            elif action in {"rollout", "rollback"}:
                completed_backup(manifest)
                candidate = image("physical-product-intelligence-backend")
                selected = previous_image if action == "rollback" else candidate
                if not selected or not re.fullmatch(r"sha256:[a-f0-9]{64}", selected):
                    raise ReleaseError(
                        "Rollback requires a reviewed immutable local image identity"
                    )
                image(selected)
                # Keep controlled tools on the candidate; only application backend is rolled back.
                env_path = folder / "compose.env"
                env_path.write_text(
                    re.sub(
                        r"(?m)^PPI_BACKEND_IMAGE=.*$",
                        "PPI_BACKEND_IMAGE=" + candidate,
                        env_path.read_text(),
                    ),
                    encoding="utf-8",
                )
                if action == "rollout":
                    frontend = image("physical-product-intelligence-frontend")
                    env_path.write_text(
                        re.sub(
                            r"(?m)^PPI_FRONTEND_IMAGE=.*$",
                            "PPI_FRONTEND_IMAGE=" + frontend,
                            env_path.read_text(),
                        ),
                        encoding="utf-8",
                    )
                    manifest["images"]["frontend"] = frontend
                override = "app-" + secrets.token_hex(6) + ".json"
                write_json(
                    folder / override,
                    {
                        "services": {
                            "backend": {
                                "image": selected,
                                "environment": {
                                    "DJANGO_SETTINGS_MODULE": "config.settings.production"
                                    if action == "rollback"
                                    else "config.settings.rehearsal"
                                },
                            }
                        }
                    },
                )
                run(command + ["stop", *writers], timeout=stop_timeout)
                if action == "rollout":
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
                            "release_migrate",
                            "--confirm-database",
                            manifest["database"],
                        ]
                    )
                manifest["active_override"] = override
                command = compose(folder, manifest)
                run(
                    command
                    + [
                        "up",
                        "-d",
                        "--no-deps",
                        "--wait",
                        "--wait-timeout",
                        "180",
                        "backend",
                        "frontend",
                        *(["processors"] if manifest.get("processors_enabled") else []),
                    ],
                    timeout=240,
                )
                run(
                    command
                    + [
                        "up",
                        "-d",
                        "--no-deps",
                        "--force-recreate",
                        "--wait",
                        "--wait-timeout",
                        "90",
                        "edge",
                    ],
                    timeout=120,
                )
                event["verification"] = runtime_probe(folder, command)
                event["application_image"] = selected
                manifest["active_application_image"] = selected
                if action == "rollout":
                    manifest["source"] = source_identity()
                    manifest["images"]["backend"] = candidate
            elif action == "seal":
                manifest["reviewed_source"] = source_identity()
                manifest["sealed_at"] = datetime.now(UTC).isoformat()
                manifest["evidence"] = {
                    path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in folder.iterdir()
                    if path.is_file()
                    and path.name
                    in {
                        "access.json",
                        "load.json",
                        "security.json",
                        "observation.json",
                        "backend-tests.log",
                        "backend-tests-final.log",
                        "frontend-tests.log",
                        "backend-checks.log",
                        "verification.json",
                        "vulnerability-summary.json",
                    }
                }
                manifest["artifact_build_times"] = {
                    name: run(
                        [
                            "docker",
                            "image",
                            "inspect",
                            "--format",
                            "{{.Created}}",
                            reference,
                        ]
                    )
                    for name, reference in manifest["images"].items()
                }
            event["status"] = "passed"
        finally:
            event["elapsed_seconds"] = round(time.monotonic() - started, 2)
            manifest["events"].append(event)
            write_json(folder / "release.json", manifest)
        return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "prepare",
            "start",
            "backup",
            "restart",
            "status",
            "verify",
            "restore",
            "rollback",
            "rollout",
            "seal",
        ],
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--https-port", type=int, default=18443)
    parser.add_argument("--previous-image")
    parser.add_argument(
        "--processors",
        action="store_true",
        help="Include supervised processors in a new isolated rehearsal",
    )
    args = parser.parse_args()
    folder = args.directory.resolve()
    if not folder.is_relative_to(ROOT / "artifacts"):
        parser.error("Rehearsal state must stay under this checkout's ignored artifacts directory")
    try:
        result = (
            prepare(folder, args.https_port, args.processors)
            if args.action == "prepare"
            else operate(folder, args.action, args.previous_image)
        )
        print(
            json.dumps(
                {
                    "status": "passed",
                    "action": args.action,
                    "project": result.get("project"),
                    "manifest": str(folder / "release.json"),
                }
            )
        )
    except ReleaseError as error:
        parser.exit(1, str(error) + "; inspect isolated target status.\n")
    except (ValueError, KeyError, OSError):
        parser.exit(
            1,
            "Release step refused/failed; inspect target status; secret output suppressed.\n",
        )


if __name__ == "__main__":
    main()
