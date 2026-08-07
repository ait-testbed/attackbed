# AttackBed Documentation

The AttackBed is a simulated enterprise network packed with numerous vulnerabilities. This testbed can be
applied to automatically launch several attack scenarios (using [AttackMate](https://github.com/ait-testbed/attackmate))
and collect log data (apache access logs, DNS logs, syslog, authentication logs, audit logs, suricata logs,
exim/mail logs, monitoring logs, etc.) as well as network traffic for forensic or live analysis and IDS
evaluation. The attack scenarios are designed to cover as many tactics and techniques of the MITRE ATT&CK
enterprise framework as possible.

## Getting started

Start with [Installation Overview](installation/overview.md) to set up the testbed, then continue with
[Requirements](installation/requirements.md) and the rest of the installation guide to deploy the
bootstrap network and a scenario.

## Scenarios

Once the testbed is deployed, see the [Scenarios](scenarios/overview.md) section for how to run the
included attack scenarios and gather logs.

## Development

For contributors, see the [Development Overview](development/overview.md) for an introduction to the
project structure and how machines in the testbed are connected.

## Tools

- [Testbedrun](tools/testbedrun.md) — selectively redeploy individual OpenStack instances.
- [MITRE Technique & Tactic Counter](tools/mitrecounter.md) — count MITRE ATT&CK technique references in a file.
