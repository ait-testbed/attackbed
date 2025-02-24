# Mitre Techniques & Tactics counter

This tool reads in text files and counts the occurence of techniques and tactics of
the mitre attack framework.

# Installation

In order to install the python dependencies, use the following command:

```
$ pip3 install -r requirements.txt
$ wget https://github.com/mitre/cti/archive/refs/tags/ATT&CK-v16.1.tar.gz
$ tar xvfz ATT&CK-v16.1.tar.gz
$ ln -s cti-ATT-CK-v16.1/enterprise-attack/enterprise-attack.json .
```

# Usage

```
$ ./tt_counter.py ../attackbed/docs/source/scenarios/videoserver.rst enterprise-attack.json
T1590: 1 ['Reconnaissance']
T1591: 1 ['Reconnaissance']
T1595: 2 ['Reconnaissance']
T1592: 1 ['Reconnaissance']
T1594: 1 ['Reconnaissance']
T1190: 1 ['Initial Access']
T1059: 1 ['Execution']
T1574: 2 ['Persistence', 'Privilege Escalation', 'Defense Evasion']
T1104: 1 ['Command and Control']
T1055: 1 ['Privilege Escalation', 'Defense Evasion']
T1105: 1 ['Command and Control']
T1087: 1 ['Discovery']
T1083: 1 ['Discovery']
T1201: 1 ['Discovery']
T1069: 1 ['Discovery']
T1057: 1 ['Discovery']
T1518: 1 ['Discovery']
T1082: 1 ['Discovery']
T1614: 1 ['Discovery']
T1016: 1 ['Discovery']
T1049: 1 ['Discovery']
T1033: 1 ['Discovery']
T1007: 1 ['Discovery']
T1615: 1 ['Discovery']
T1068: 1 ['Privilege Escalation']
T1546: 2 ['Persistence', 'Privilege Escalation']
T1548: 1 ['Privilege Escalation', 'Defense Evasion']
T1547: 1 ['Persistence', 'Privilege Escalation']
T1053: 1 ['Execution', 'Persistence', 'Privilege Escalation']
T1078: 1 ['Persistence', 'Privilege Escalation', 'Defense Evasion', 'Initial Access']
T1098: 1 ['Persistence', 'Privilege Escalation']
T1136: 1 ['Persistence']
T1556: 1 ['Credential Access', 'Persistence', 'Defense Evasion']
T1218: 1 ['Defense Evasion']
T1555: 1 ['Credential Access']
T1046: 1 ['Discovery']
T1120: 1 ['Discovery']
T1124: 1 ['Discovery']
T1497: 1 ['Defense Evasion', 'Discovery']
Summary: 42
Unique: 39
```

