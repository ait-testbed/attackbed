#!/usr/bin/env python3

import sys
import re
import argparse
from mitreattack.stix20 import MitreAttackData

parser = argparse.ArgumentParser(
                    prog='tt_counter.py',
                    description='Identifies MITRE ATT&CK® technique IDs (e.g., T1234), and counts their occurrences.',
                    epilog='Needs MITRE ATT&CK Enterprise STIX JSON file.')

parser.add_argument('--stix',nargs='?',default='enterprise-attack.json', help='MITRE ATT&CK Enterprise STIX JSON file. Defaults to ./enterprise-attack.json')
parser.add_argument('filenames',nargs='+')          

args = parser.parse_args()

matrix_filename = args.stix
mitre_attack_data: MitreAttackData = MitreAttackData(matrix_filename)

complete_hash = {}
for f in args.filenames:
    counthash = {}
    with open(f, 'r') as file:
        for line in file:
            m = re.findall(r'T\d{4}', line)
            if m:
                for i in m:
                    if i in counthash.keys():
                        counthash[i] = counthash[i] + 1
                    else:
                        counthash[i] = 1

                    if i in complete_hash.keys():
                        complete_hash[i] = complete_hash[i] + 1
                    else:
                        complete_hash[i] = 1



    counter = 0

    print(f"\nIn File {f}:\n")
    for technique,value in counthash.items():
        t: object = mitre_attack_data.get_object_by_attack_id(technique, "attack-pattern")
        tactics = mitre_attack_data.get_tactics_by_technique(t.id)
        tactic_names = []
        for t in tactics:
            tactic_names.append(t.name)

        print(f"{technique}: {value} {tactic_names}")
        counter = counter + value

    print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    print(f"File Summary: {counter}")
    print(f"File Unique: {len(counthash.keys())}")
    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")

counter = 0
print("\nTotal for all Files:\n")
for technique,value in complete_hash.items():
    t: object = mitre_attack_data.get_object_by_attack_id(technique, "attack-pattern")
    tactics = mitre_attack_data.get_tactics_by_technique(t.id)
    tactic_names = []
    for t in tactics:
        tactic_names.append(t.name)

    print(f"{technique}: {value} {tactic_names}")
    counter = counter + value
print("\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
print("Total for all Files:")
print(f"Total Summary: {counter}")
print(f"Total Unique: {len(complete_hash.keys())}")
print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
