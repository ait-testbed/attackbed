import os
import subprocess
import inquirer
from pprint import pprint

VM_MAP = { "reposerver": "repository", 
           "linuxshare": "repository",
           "videoserver": "videoserver",
           "adminpc": "videoserver",
           "webcam": "videoserver",
           "corpdns": "videoserver",
           "attacker": "attacker",
           "inet-dns": "bootstrap",
           "inet-fw": "bootstrap",
           "mgmt": "bootstrap"
         }

def get_rootpath():
    current = os.getcwd()
    for dirfile in os.listdir(current):
        if dirfile == "terragrunt" and os.path.isdir(os.path.join(current, dirfile)):
            return current
    head = current
    tail = True
    while tail:
        (head, tail) = os.path.split(head)
        for dirfile in os.listdir(head):
            if dirfile == "terragrunt" and os.path.isdir(os.path.join(head, dirfile)):
                return head
    return None

def choose_machines():
    machines = VM_MAP.keys()
    questions = [
                 inquirer.Checkbox(
                     "vms",
                     message="Which Instances do you want to redeploy?",
                     choices=machines,
                 ),
    ]
    answers = inquirer.prompt(questions)
    return answers['vms']

def restart_instance(instance, rootpath):
    subdir = VM_MAP[instance]
    print(f"Resource: openstack_compute_instance_v2.{instance}")
    print(f"Path: {rootpath}/terragrunt/{subdir}")
    os.chdir(os.path.join(rootpath, "terragrunt", subdir))
    p = subprocess.run(['terragrunt', 'destroy', '--target', f"openstack_compute_instance_v2.{instance}"])
    if p.returncode == 0:
        p = subprocess.run(['terragrunt', 'apply'])
    else:
        exit(1)


def main():
    rootpath = get_rootpath()
    if not rootpath:
        print("Testbed directory not found!")
        return 1
    print(rootpath)
    for instance in choose_machines():
        restart_instance(instance, rootpath)



if __name__ == '__main__':
    exit(main())
