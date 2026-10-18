"""Read-only production gate. Never connects to a target host, reads secrets or deploys."""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from release import ROOT, run

REQUIRED_JOBS = {
    "backend",
    "frontend",
    "compose-smoke",
    "browser-acceptance",
    "backend-images-false",
    "backend-images-true",
    "infrastructure-security-postgres",
    "infrastructure-security-ingress",
    "infrastructure-security-scanner",
}


def hosted_jobs_passed(workflow, jobs, revision):
    return (
        workflow.get("head_sha") == revision
        and workflow.get("status") == "completed"
        and workflow.get("conclusion") == "success"
        and len(jobs) == len(REQUIRED_JOBS)
        and {job.get("name") for job in jobs} == REQUIRED_JOBS
        and all(
            job.get("status") == "completed" and job.get("conclusion") == "success" for job in jobs
        )
    )


def validate(target, manifest):
    blocked = []
    if target.get("environment") not in {"production", "staging"}:
        blocked.append("explicit_environment_required")
    if not target.get("target_host") or "REPLACE" in target["target_host"]:
        blocked.append("authorized_target_host_missing")
    origin = urlsplit(target.get("public_origin", ""))
    if (
        origin.scheme != "https"
        or not origin.hostname
        or "replace" in origin.hostname.lower()
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        blocked.append("approved_https_domain_missing")
    if not target.get("deployment_authorized"):
        blocked.append("external_deployment_not_authorized")
    if target.get("commercial_mode") not in {
        "approved_manual_private_pilot",
        "paid_public_launch",
    }:
        blocked.append("commercial_launch_decision_missing")
    if target.get("commercial_mode") == "paid_public_launch":
        blocked.append("real_payment_adapter_merchant_prices_and_policy_not_verified")
    if manifest["source"]["dirty"] or run(["git", "status", "--porcelain"]):
        blocked.append("committed_clean_candidate_required")
    if manifest["source"]["revision"] != run(["git", "rev-parse", "HEAD"]):
        blocked.append("manifest_revision_mismatch")
    expected_images = {"backend", "frontend", "postgres", "ingress", "scanner"}
    if set(manifest["images"]) != expected_images or any(
        not re.fullmatch(r"sha256:[a-f0-9]{64}", value) for value in manifest["images"].values()
    ):
        blocked.append("immutable_artifacts_required")
    scans = manifest.get("image_security", {})
    if scans.get("status") != "passed" or scans.get("images") != manifest["images"]:
        blocked.append("passing_security_evidence_for_all_artifacts_required")
    for key in ("runtime_env_file", "migration_env_file", "database_ca_file"):
        path = Path(target.get(key, ""))
        if not path.is_absolute() or not path.is_file() or path.resolve().is_relative_to(ROOT):
            blocked.append(key + "_not_provisioned_outside_repository")
        elif os.name == "posix" and key.endswith("env_file") and path.stat().st_mode & 0o077:
            blocked.append(key + "_permissions_too_broad")
    return blocked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--verify-hosted", action="store_true")
    args = parser.parse_args()
    target, manifest = (
        json.loads(args.target.read_text()),
        json.loads(args.manifest.read_text()),
    )
    blocked = validate(target, manifest)
    hosted = None
    if not blocked and args.verify_hosted:
        repo = target.get("repository", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            blocked.append("invalid_repository_identity")
        else:
            try:
                url = (
                    f"https://api.github.com/repos/{repo}/actions/runs?head_sha="
                    + manifest["source"]["revision"]
                )
                with urlopen(
                    Request(url, headers={"User-Agent": "ppi-release-preflight"}),
                    timeout=15,
                ) as response:
                    runs = json.load(response)["workflow_runs"]
                runs = [
                    r
                    for r in runs
                    if r["path"] == ".github/workflows/ci.yml"
                    and r["head_sha"] == manifest["source"]["revision"]
                ]
                jobs = []
                if runs:
                    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{runs[0]['id']}/attempts/{runs[0]['run_attempt']}/jobs?per_page=100"
                    with urlopen(
                        Request(jobs_url, headers={"User-Agent": "ppi-release-preflight"}),
                        timeout=15,
                    ) as response:
                        payload = json.load(response)
                    jobs = payload["jobs"]
                    if payload.get("total_count") != len(jobs):
                        jobs = []
                if runs and hosted_jobs_passed(runs[0], jobs, manifest["source"]["revision"]):
                    hosted = {
                        "url": runs[0]["html_url"],
                        "revision": runs[0]["head_sha"],
                        "status": "success",
                        "time": runs[0]["updated_at"],
                        "required_jobs": sorted(job["name"] for job in jobs),
                    }
                else:
                    blocked.append("hosted_ci_not_passed_for_candidate")
            except (OSError, ValueError, KeyError):
                blocked.append("hosted_ci_read_unavailable")
    else:
        blocked.append("hosted_ci_not_verified_for_candidate")
    print(
        json.dumps(
            {
                "status": "blocked" if blocked else "preflight_only_passed",
                "blocked": blocked,
                "hosted_ci": hosted,
                "infrastructure_acceptance": "separate_staging_checks_required",
                "remote_mutations": 0,
            }
        )
    )
    raise SystemExit(1 if blocked else 0)


if __name__ == "__main__":
    main()
