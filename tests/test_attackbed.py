"""Checks for image selection, resuming builds, and per-lab SSH aliases."""

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from attackbed import cli, deploy, images, ssh


def image(name, image_id, created):
    return SimpleNamespace(id=image_id, name=name, created_at=created, status="active")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        recipe = self.root / "packer" / "firewall"
        recipe.mkdir(parents=True)
        (recipe / "default.json.example").write_text('{"image_name": "atb-firewall"}')
        (recipe / "default.json").write_text('{"image_name": "atb-firewall"}')
        recipe = self.root / "packer" / "corpdns"
        recipe.mkdir(parents=True)
        (recipe / "default.json.example").write_text('{"image_name": "atb-corpdns"}')
        (recipe / "default.json").write_text('{"image_name": "atb-corpdns"}')
        config = self.root / "config"
        config.mkdir()
        (config / "image-recipes.yaml").write_text("inetfw_image: firewall\ncorpdns_image: corpdns\n")
        terragrunt = self.root / "terragrunt"
        (terragrunt / "bootstrap/module").mkdir(parents=True)
        (terragrunt / "bootstrap/terragrunt.hcl").touch()
        (terragrunt / "bootstrap/module/variables.tf").write_text(
            'variable "inetfw_image" {}\nvariable "corpdns_image" {}\nvariable "mgmt_image" {}\n')
        (config / "scenarios.yaml").write_text("core: [bootstrap]\n")
        (self.root / "packer/defaults.json").write_text(
            '{"network": "build-net", "floating_ip_pool": "Ext-Net", "security_group": "default"}')
        self.images = [image("atb-firewall-1", "11111111-1111-1111-1111-111111111111", "2026-01-01"),
                       image("atb-firewall-2", "22222222-2222-2222-2222-222222222222", "2026-02-01"),
                       image("atb-corpdns-1", "33333333-3333-3333-3333-333333333333", "2026-03-01")]
        self.conn = SimpleNamespace(image=SimpleNamespace(
            images=lambda: self.images,
            get_image=lambda uid: next((i for i in self.images if i.id == uid), None)))

    def test_required_recipes_and_latest(self):
        recipes = images.required_recipes(self.root, ["bootstrap"])
        self.assertEqual(recipes, {"corpdns_image": "corpdns", "inetfw_image": "firewall"})
        selected = images.latest_images(self.conn, self.root, recipes)
        self.assertEqual(selected["inetfw_image"]["name"], "atb-firewall-2")
        self.assertEqual(selected["corpdns_image"]["id"], self.images[2].id)

    def test_shared_packer_defaults_and_recipe_override(self):
        recipe = self.root / "packer/firewall"
        (recipe / "default.json.example").write_text(json.dumps({
            "image_name": "atb-firewall", "base_image": "Ubuntu 22.04",
            "network": "old-cloud", "floating_ip_pool": "old-pool",
        }))
        (recipe / "default.json").unlink()
        config = images.recipe_config(self.root, "firewall", build=True)
        self.assertEqual(config["image_name"], "atb-firewall")
        self.assertEqual(config["base_image"], "Ubuntu 22.04")
        self.assertEqual(config["network"], "build-net")
        self.assertEqual(config["floating_ip_pool"], "Ext-Net")
        (recipe / "default.json").write_text('{"network": "custom-net"}')
        self.assertEqual(images.recipe_config(self.root, "firewall", build=True)["network"], "custom-net")

    def test_build_requires_configured_network(self):
        (self.root / "packer/defaults.json").unlink()
        with self.assertRaisesRegex(ValueError, "Configure network and floating_ip_pool"):
            images.recipe_config(self.root, "firewall", build=True)
        self.assertEqual(images.recipe_config(self.root, "firewall")["image_name"], "atb-firewall")

    def test_resume_skips_successful_packer_build(self):
        built = []

        def build(conn, root, recipe, log):
            built.append(recipe)
            if recipe == "firewall" and built.count("firewall") == 1:
                raise RuntimeError("build failed")
            return images.active_image(conn, next(i.id for i in self.images if recipe in i.name))

        selections = []

        def run(*args, **kwargs):
            selections.append(os.environ.get("ATTACKBED_IMAGES_FILE"))
            return 0

        with patch.object(cli, "connect", return_value=self.conn), \
             patch.object(cli, "build_image", side_effect=build), \
             patch.object(deploy, "main", side_effect=run) as invoke, \
             patch.object(cli, "write_ssh_config"):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                cli.main(["core", "--build", "--copies", "2", "--tofu-parallelism", "3"], self.root)
            self.assertEqual(cli.main(["--resume"], self.root), 0)
            self.assertEqual(cli.main(["--resume"], self.root), 0)
            call = invoke.call_args
        self.assertEqual(built, ["corpdns", "firewall", "firewall"])
        self.assertEqual(call.args[0].count("--deployment"), 2)
        self.assertIn("--tofu-parallelism", call.args[0])
        self.assertTrue(Path(selections[0]).is_absolute())
        directory = next((self.root / "runs").iterdir())
        self.assertEqual(call.kwargs["run_dir"], directory)
        self.assertTrue((directory / "logs/packer").is_dir())
        self.assertTrue(json.loads((directory / "run.json").read_text())["complete"])
        self.assertEqual(len(json.loads((directory / "images.json").read_text())), 2)

    def test_latest_selection_is_saved_for_resume(self):
        with patch.object(cli, "connect", return_value=self.conn), \
             patch.object(cli, "write_ssh_config") as ssh_write, \
             patch.object(deploy, "main", side_effect=[1, 0]):
            with self.assertRaisesRegex(RuntimeError, "Terragrunt apply failed"):
                cli.main(["core"], self.root)
            self.images.append(image("atb-firewall-3", "44444444-4444-4444-4444-444444444444", "2026-04-01"))
            cli.main(["--resume"], self.root)
            self.assertEqual(ssh_write.call_count, 1)
        directory = next((self.root / "runs").iterdir())
        self.assertEqual(json.loads((directory / "images.json").read_text())["inetfw_image"]["name"],
                         "atb-firewall-2")

    def test_destroy_uses_scenario_copies_and_prefix(self):
        with patch.object(deploy, "main", return_value=0) as run, patch.object(cli, "connect") as connect:
            self.assertEqual(cli.main(["destroy", "core", "--copies", "3", "--prefix", "trial",
                                       "--parallel-copies", "2", "--yes"], self.root), 0)
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ["core", "destroy", "--yes"])
        self.assertEqual(args[-4:], ["--copies", "3", "--prefix", "trial"])
        self.assertIn("--parallel-copies", args)
        self.assertNotIn("--deployment", args)
        self.assertIsNone(run.call_args.kwargs["run_dir"])
        connect.assert_not_called()

    def test_destroy_run_id_uses_saved_deployments_and_updates_state(self):
        selected_images = []

        def run(*args, **kwargs):
            selected_images.append(os.environ.get("ATTACKBED_IMAGES_FILE"))
            return 0

        with patch.object(cli, "connect", return_value=self.conn) as connect, \
             patch.object(cli, "write_ssh_config"), \
             patch.object(deploy, "main", side_effect=run) as invoke:
            self.assertEqual(cli.main(["core", "--copies", "2", "--tofu-parallelism", "3"], self.root), 0)
            directory = next((self.root / "runs").iterdir())
            invoke.reset_mock()
            self.assertEqual(cli.main(["destroy", directory.name, "--yes"], self.root), 0)
            invoke.assert_called_once()
            args = invoke.call_args.args[0]
            self.assertEqual(args.count("--deployment"), 2)
            self.assertIn("lab-001", args)
            self.assertIn("lab-002", args)
            self.assertIn("--tofu-parallelism", args)
            self.assertEqual(invoke.call_args.kwargs["run_dir"], directory)
            self.assertEqual(selected_images[-1], str((directory / "images.json").resolve()))
            invoke.reset_mock()
            self.assertEqual(cli.main(["destroy", directory.name, "--yes"], self.root), 0)
            invoke.assert_not_called()
            connect.assert_called_once()
        job = json.loads((directory / "run.json").read_text())
        self.assertTrue(job["destroyed"])
        self.assertFalse(job["deployed"])
        with self.assertRaises(SystemExit):
            cli.main(["--resume", directory.name], self.root)

    def test_destroy_requires_confirmation_and_preserves_failed_runs(self):
        with patch.object(deploy, "main") as run:
            for args in (["destroy", "core", "--copies", "2"],
                         ["destroy", "core", "--yes"],
                         ["destroy", "core", "--copies", "0", "--yes"]):
                with self.assertRaises(SystemExit):
                    cli.main(args, self.root)
            run.assert_not_called()

        directory = self.root / "runs" / "run-20261116-test"
        directory.mkdir(parents=True)
        job = {"scenario": "core", "deployments": ["lab-001"],
               "parallel_copies": 2, "tofu_parallelism": None, "deployed": True}
        cli.save_json(directory / "run.json", job)
        with patch.object(deploy, "main", return_value=1):
            with self.assertRaisesRegex(RuntimeError, "Terragrunt destroy failed"):
                cli.main(["destroy", directory.name, "--yes"], self.root)
        self.assertEqual(json.loads((directory / "run.json").read_text()), job)

    def test_terragrunt_logs_append_in_run_directory(self):
        directory = self.root / "runs/run-test"
        with patch.object(deploy.subprocess, "Popen") as popen:
            proc = popen.return_value.__enter__.return_value
            proc.stdout = ["created resource\n"]
            proc.wait.return_value = 0
            for _ in range(2):
                with self.subTest(attempt=_):
                    self.assertEqual(deploy.main(["core", "plan", "--copies", "1"],
                                                 self.root / "terragrunt", run_dir=directory), 0)
        log = (directory / "logs/plan.log").read_text()
        self.assertEqual(log.count("[lab-001/bootstrap] created resource\n"), 2)
        self.assertEqual(log.count("--- plan "), 2)

    def test_packer_machine_output_parsing(self):
        self.conn.image.get_image = lambda uid: image("atb-firewall-3", uid, "2026")
        with patch.object(images.subprocess, "run") as run, patch.object(images.subprocess, "Popen") as popen:
            proc = popen.return_value.__enter__.return_value
            proc.stdout = ["123,openstack.builder,artifact,0,builder-id,mitchellh.openstack\n",
                           "123,openstack.builder,artifact,0,id,eu-west-par:44444444-4444-4444-4444-444444444444\n"]
            proc.wait.return_value = 0
            log_path = self.root / "build.log"
            log_path.write_text("previous build\n")
            result = images.build_image(self.conn, self.root, "firewall", log_path)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["ansible-galaxy", "role", "install", "-r", "playbook/requirements.yml", "-p", "playbook/roles"],
            ["packer", "init", "."],
        ])
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))
        self.assertEqual(result["id"], "44444444-4444-4444-4444-444444444444")
        self.assertIn("previous build\n", log_path.read_text())
        args = popen.call_args.args[0]
        var_file = Path(next(arg.partition("=")[2] for arg in args if arg.startswith("-var-file=")))
        self.assertTrue(var_file.is_absolute())
        self.assertEqual(json.loads(var_file.read_text())["network"], "build-net")
        self.assertEqual(var_file.stat().st_mode & 0o777, 0o600)

    def test_packer_stops_when_ansible_roles_fail(self):
        with (
            patch.object(images.subprocess, "run", side_effect=images.subprocess.CalledProcessError(1, "ansible-galaxy")) as run,
            patch.object(images.subprocess, "Popen") as popen,
        ):
            with self.assertRaises(images.subprocess.CalledProcessError):
                images.build_image(self.conn, self.root, "firewall", self.root / "build.log")
        self.assertEqual(run.call_count, 1)
        popen.assert_not_called()


class SSHTests(unittest.TestCase):
    def test_labs_with_overlapping_private_ips(self):
        def server(name, network, ip, floating=None):
            addresses = [{"addr": ip, "OS-EXT-IPS:type": "fixed"}]
            if floating:
                addresses.append({"addr": floating, "OS-EXT-IPS:type": "floating"})
            return SimpleNamespace(name=name, addresses={network: addresses})

        machines = [server("lab-001-mgmt", "lab-001-admin", "10.12.0.201", "203.0.113.1"),
                    server("lab-001-adminpc1", "lab-001-admin", "10.12.0.222"),
                    server("lab-002-mgmt", "lab-002-admin", "10.12.0.201", "203.0.113.2"),
                    server("lab-002-adminpc1", "lab-002-admin", "10.12.0.222")]
        conn = SimpleNamespace(compute=SimpleNamespace(servers=lambda: machines))
        with TemporaryDirectory() as temp:
            path = Path(temp) / "ssh_config"
            ssh.write_ssh_config(conn, ["lab-001", "lab-002"], path)
            content = path.read_text()
        self.assertIn("ProxyJump lab-001-mgmt", content)
        self.assertIn("ProxyJump lab-002-mgmt", content)
        self.assertIn("HostKeyAlias lab-001-adminpc1", content)
        self.assertIn("HostKeyAlias lab-002-adminpc1", content)
        self.assertEqual(content.count("HostName 10.12.0.222"), 2)


if __name__ == "__main__":
    unittest.main()
