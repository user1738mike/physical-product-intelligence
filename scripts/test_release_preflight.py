import unittest

from release_preflight import REQUIRED_JOBS, hosted_jobs_passed


class HostedCandidateTests(unittest.TestCase):
    def test_every_exact_candidate_job_must_pass_without_skips_or_missing_matrix_legs(self):
        revision = "a" * 40
        workflow = {"head_sha": revision, "status": "completed", "conclusion": "success"}
        jobs = [
            {"name": name, "status": "completed", "conclusion": "success"} for name in REQUIRED_JOBS
        ]
        self.assertTrue(hosted_jobs_passed(workflow, jobs, revision))
        self.assertFalse(hosted_jobs_passed(workflow, jobs[:-1], revision))
        self.assertFalse(hosted_jobs_passed(workflow, jobs + [jobs[0]], revision))
        self.assertFalse(hosted_jobs_passed(workflow, jobs, "b" * 40))
        for state in ("skipped", "cancelled", "failure", "neutral", None):
            changed = [{**job} for job in jobs]
            changed[0]["conclusion"] = state
            self.assertFalse(hosted_jobs_passed(workflow, changed, revision))
        self.assertFalse(
            hosted_jobs_passed({**workflow, "conclusion": "cancelled"}, jobs, revision)
        )
