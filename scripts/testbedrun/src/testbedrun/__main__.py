import os
import subprocess
import inquirer
from pprint import pprint
import yaml
import argparse
from typing import Dict, List, Optional

def load_vm_map(yaml_file: str) -> Dict[str, str]:
    """
    Load the VM map from a YAML file.
    
    :param yaml_file: Path to the YAML file.
    :return: A dictionary containing the VM map.
    """
    try:
        with open(yaml_file, 'r') as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Error: File {yaml_file} not found.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        exit(1)

def get_rootpath() -> Optional[str]:
    """
    Find the root path containing the "terragrunt" directory.
    
    :return: The root path as a string or None if not found.
    """
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

def choose_machines(vm_map: Dict[str, str]) -> List[str]:
    """
    Prompt the user to select machines for redeployment.
    
    :param vm_map: The VM map containing machine names.
    :return: A list of selected machine names.
    """
    machines = vm_map.keys()
    questions = [
                 inquirer.Checkbox(
                     "vms",
                     message="Which Instances do you want to redeploy?",
                     choices=machines,
                 ),
    ]
    answers = inquirer.prompt(questions)
    return answers['vms']

def restart_instance(instance: str, rootpath: str, vm_map: Dict[str, str]) -> None:
    """
    Restart a specified instance using Terragrunt.
    
    :param instance: The instance name.
    :param rootpath: The root path containing the "terragrunt" directory.
    :param vm_map: The VM map containing instance-to-subdirectory mappings.
    """
    subdir = vm_map[instance]
    print(f"Resource: openstack_compute_instance_v2.{instance}")
    print(f"Path: {rootpath}/terragrunt/{subdir}")
    os.chdir(os.path.join(rootpath, "terragrunt", subdir))
    p = subprocess.run(['terragrunt', 'destroy', '--target', f"openstack_compute_instance_v2.{instance}"])
    if p.returncode == 0:
        p = subprocess.run(['terragrunt', 'apply'])
    else:
        exit(1)


def main():
    parser = argparse.ArgumentParser(description="Redeploy OpenStack Instances")
    parser.add_argument(
        "yaml_file", 
        type=str, 
        help="Path to the YAML file containing the VM map."
    )
    args = parser.parse_args()

    vm_map = load_vm_map(yaml_file)
    rootpath = get_rootpath()
    if not rootpath:
        print("Testbed directory not found!")
        return 1
    print(rootpath)
    for instance in choose_machines(vm_map):
        restart_instance(instance, rootpath)



if __name__ == '__main__':
    exit(main())
