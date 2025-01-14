#!/usr/bin/env python3

import sys
import re
from mitreattack.stix20 import MitreAttackData

inputfile = sys.argv[1]
counthash = {}

matrix_filename = "enterprise-attack.json"

if len(sys.argv) == 3:
    filename = sys.argv[2]

mitre_attack_data: MitreAttackData = MitreAttackData(matrix_filename)

with open(inputfile, 'r') as file:
    for line in file:
        m = re.findall(r'T\d{4}', line)
        if m:
            for i in m:
                if i in counthash.keys():
                    counthash[i] = counthash[i] + 1
                else:
                    counthash[i] = 1


counter = 0

for technique,value in counthash.items():
    t: object = mitre_attack_data.get_object_by_attack_id(technique, "attack-pattern")
    tactics = mitre_attack_data.get_tactics_by_technique(t.id)
    tactic_names = []
    for t in tactics:
        tactic_names.append(t.name)

    print(f"{technique}: {value} {tactic_names}")
    counter = counter + value

print(f"Summary: {counter}")
print(f"Unique: {len(counthash.keys())}")
