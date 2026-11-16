"""State cleanup must never delete tracked resources or states after failed destroys."""

from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError


script = Path(__file__).resolve().parents[1] / "deploy_scenario.py"
spec = importlib.util.spec_from_file_location("deploy_scenario", script)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

ENV = {
    "GITLAB_STATE_REPOSITORY": "https://gitlab.example.com/api/v4/projects/123/terraform/state",
    "CR_GITLAB_ACCESS_TOKEN": "test-token",
    "OS_PROJECT_NAME": "Default",
    "OS_USER_DOMAIN_NAME": "Default",
    "OS_REGION_NAME": "eu-west-par",
}


class StateCleanupTests(unittest.TestCase):
    def test_failed_destroy_preserves_states(self):
        calls = []

        def runner(root, deployment, unit, action, parallelism, logfile, debug):
            calls.append(unit)
            return int(unit == "videoserver")

        with mock.patch.object(deploy, "delete_deployment_states") as delete:
            result = deploy.run_deployment(Path("/tmp"), "lab-001",
                                           ["bootstrap", "videoserver"], "destroy",
                                           runner=runner)
        self.assertEqual((result, calls), (1, ["videoserver"]))
        delete.assert_not_called()

    def test_cleanup_only_after_every_destroy(self):
        calls = []

        def runner(root, deployment, unit, action, parallelism, logfile, debug):
            calls.append(unit)
            return 0

        with mock.patch.object(deploy, "delete_deployment_states") as delete:
            result = deploy.run_deployment(Path("/tmp"), "lab-001",
                                           ["bootstrap", "videoserver"], "destroy",
                                           runner=runner)
        self.assertEqual((result, calls), (0, ["videoserver", "bootstrap"]))
        delete.assert_called_once_with("lab-001", ["bootstrap", "videoserver"])

    def test_state_is_checked_before_delete(self):
        requests = []

        def open_state(request, timeout):
            requests.append(request)
            if request.get_method() == "GET":
                return BytesIO(json.dumps({"resources": [
                    {"mode": "data", "instances": [{}]}
                ]}).encode())
            return BytesIO()

        with mock.patch.dict(os.environ, ENV):
            with mock.patch.object(deploy, "urlopen", side_effect=open_state):
                deploy.delete_deployment_states("lab-001", ["bootstrap"])
        self.assertEqual([r.get_method() for r in requests], ["GET", "DELETE"])
        self.assertTrue(requests[0].full_url.endswith(
            "Default_Default_eu-west-par_lab-001_bootstrap"))
        self.assertEqual(requests[1].get_header("Private-token"), "test-token")

    def test_nonempty_state_is_kept(self):
        state = {"resources": [{"mode": "managed", "instances": [{"attributes": {"id": "live"}}]}]}
        with mock.patch.dict(os.environ, ENV):
            with mock.patch.object(deploy, "urlopen",
                                   return_value=BytesIO(json.dumps(state).encode())) as fetch:
                with self.assertRaisesRegex(RuntimeError, "still tracks resources"):
                    deploy.delete_deployment_states("lab-001", ["bootstrap"])
        fetch.assert_called_once()

    def test_missing_state_is_ok_but_other_errors_fail(self):
        with mock.patch.dict(os.environ, ENV):
            for code in (404, 403):
                with self.subTest(code=code):
                    error = HTTPError("https://gitlab.example.com", code, "failure", None, None)
                    with mock.patch.object(deploy, "urlopen", side_effect=error) as fetch:
                        if code == 404:
                            deploy.delete_deployment_states("lab-001", ["bootstrap"])
                        else:
                            with self.assertRaises(HTTPError):
                                deploy.delete_deployment_states("lab-001", ["bootstrap"])
                    fetch.assert_called_once()

    def test_rejects_unexpected_api_url(self):
        with mock.patch.dict(os.environ,
                             {**ENV, "GITLAB_STATE_REPOSITORY": "https://example.com/unrelated"}):
            with mock.patch.object(deploy, "urlopen") as fetch:
                with self.assertRaisesRegex(ValueError, "GitLab Terraform state API"):
                    deploy.delete_deployment_states("lab-001", ["bootstrap"])
                fetch.assert_not_called()

    def test_cleanup_failure_reports_error(self):
        with mock.patch.object(deploy, "delete_deployment_states",
                               side_effect=RuntimeError("not empty")):
            with redirect_stderr(StringIO()) as err:
                result = deploy.run_deployment(Path("/tmp"), "lab-001", ["bootstrap"],
                                               "destroy", runner=lambda *args: 0)
        self.assertEqual(result, 1)
        self.assertIn("state cleanup failed", err.getvalue())


class LoggingTests(unittest.TestCase):
    def test_failures_show_tail_and_redact_log(self):
        with mock.patch.dict(os.environ, {"CR_GITLAB_ACCESS_TOKEN": "SECRET"}):
            with mock.patch.object(deploy.subprocess, "Popen") as popen:
                process = popen.return_value.__enter__.return_value
                process.stdout = ["SECRET\n", "Error: failure\n"]
                process.wait.return_value = 1
                log, err = StringIO(), StringIO()
                with redirect_stderr(err), redirect_stdout(StringIO()):
                    result = deploy.run_unit(Path("/tmp"), "lab-001", "bootstrap",
                                             "destroy", log_file=log)
        self.assertEqual(result, 1)
        self.assertIn("Error: failure", err.getvalue())
        self.assertIn("[REDACTED]", log.getvalue())
        self.assertNotIn("SECRET", log.getvalue() + err.getvalue())

    def test_log_is_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "terragrunt"
            root.mkdir()
            config = root.parent / "config"
            config.mkdir()
            (config / "scenarios.yaml").write_text("demo: [bootstrap]\n")
            (root / "bootstrap").mkdir()
            (root / "bootstrap/terragrunt.hcl").touch()
            (root / "attackbed.log").write_text("previous run")
            with mock.patch.object(deploy.subprocess, "Popen") as popen:
                process = popen.return_value.__enter__.return_value
                process.stdout = ["current run\n"]
                process.wait.return_value = 0
                with redirect_stdout(StringIO()):
                    result = deploy.main(["demo", "plan", "--copies", "1"], root)
            log = (root / "attackbed.log").read_text()
        self.assertEqual(result, 0)
        self.assertEqual(log, "[lab-001/bootstrap] current run\n")


if __name__ == "__main__":
    unittest.main()
