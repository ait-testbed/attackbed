"""Checks for image selection, resuming builds, and per-lab SSH aliases."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from attackbed import cli, images, ssh


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
        mapping = self.root / "scripts/attackbed"
        mapping.mkdir(parents=True)
        (mapping / "recipes.yaml").write_text("inetfw_image: firewall\ncorpdns_image: corpdns\n")
        terragrunt = self.root / "terragrunt"
        (terragrunt / "bootstrap/module").mkdir(parents=True)
        (terragrunt / "bootstrap/module/variables.tf").write_text(
            'variable "inetfw_image" {}\nvariable "corpdns_image" {}\nvariable "mgmt_image" {}\n')
        (terragrunt / "scenarios.yaml").write_text("core: [bootstrap]\n")
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

    def test_resume_skips_successful_packer_build(self):
        built = []

        def build(conn, root, recipe, log):
            built.append(recipe)
            if recipe == "firewall" and built.count("firewall") == 1:
                raise RuntimeError("build failed")
            return images.active_image(conn, next(i.id for i in self.images if recipe in i.name))

        with patch.object(cli, "connect", return_value=self.conn), \
             patch.object(cli, "build_image", side_effect=build), \
             patch.object(cli.subprocess, "run"), \
             patch.object(cli, "write_ssh_config"):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                cli.main(["core", "--build", "--copies", "2", "--tofu-parallelism", "3"], self.root)
            self.assertEqual(cli.main(["--resume"], self.root), 0)
            self.assertEqual(cli.main(["--resume"], self.root), 0)
            call = cli.subprocess.run.call_args
        self.assertEqual(built, ["corpdns", "firewall", "firewall"])
        self.assertEqual(call.args[0].count("--deployment"), 2)
        self.assertIn("--tofu-parallelism", call.args[0])
        self.assertTrue(Path(call.kwargs["env"]["ATTACKBED_IMAGES_FILE"]).is_absolute())
        directory = next((self.root / "runs").iterdir())
        self.assertTrue(json.loads((directory / "run.json").read_text())["complete"])
        self.assertEqual(len(json.loads((directory / "images.json").read_text())), 2)

    def test_latest_selection_is_saved_for_resume(self):
        with patch.object(cli, "connect", return_value=self.conn), \
             patch.object(cli, "write_ssh_config") as ssh_write, \
             patch.object(cli.subprocess, "run") as run:
            run.side_effect = [RuntimeError("interrupted"), None]
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                cli.main(["core"], self.root)
            self.images.append(image("atb-firewall-3", "44444444-4444-4444-4444-444444444444", "2026-04-01"))
            cli.main(["--resume"], self.root)
            self.assertEqual(ssh_write.call_count, 1)
        directory = next((self.root / "runs").iterdir())
        self.assertEqual(json.loads((directory / "images.json").read_text())["inetfw_image"]["name"],
                         "atb-firewall-2")

    def test_packer_machine_output_parsing(self):
        self.conn.image.get_image = lambda uid: image("atb-firewall-3", uid, "2026")
        with patch.object(images.subprocess, "run") as run, patch.object(images.subprocess, "Popen") as popen:
            proc = popen.return_value.__enter__.return_value
            proc.stdout = ["123,openstack.builder,artifact,0,builder-id,mitchellh.openstack\n",
                           "123,openstack.builder,artifact,0,id,eu-west-par:44444444-4444-4444-4444-444444444444\n"]
            proc.wait.return_value = 0
            result = images.build_image(self.conn, self.root, "firewall", self.root / "build.log")
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["ansible-galaxy", "role", "install", "-r", "playbook/requirements.yml", "-p", "playbook/roles"],
            ["packer", "init", "."],
        ])
        self.assertTrue(all(call.kwargs["check"] for call in run.call_args_list))
        self.assertEqual(result["id"], "44444444-4444-4444-4444-444444444444")

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
