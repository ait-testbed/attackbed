# Welcome to AttackBed! <img alt="Logo" src="/images/AttackBed_logo.svg" align="right" height="90">

The AttackBed is a simulated enterprise network packed with numerous vulnerabilities. This testbed can be applied to automatically launch several attack scenarios (using <a href="https://github.com/ait-testbed/attackmate">AttackMate</a>) and collect log data (apache access logs, DNS logs, syslog, authentication logs, audit logs, suricata logs, exim/mail logs, monitoring logs, etc.) as well as network traffic for forensic or live analysis and IDS evaluation. The attack scenarios are designed to cover as many tactics and techniques of the MITRE ATT&CK enterprise framework as possible. This repository contains all scripts required to setup such a testbed and launch the attack scenarios within a virtualized environment.
 
## Scenarios

The testbed comprises three segments connected via a firewall: Internet (contains public DNS server), DMZ (contains a video server), and Intranet (contains user hosts). The scenarios are designed as multi-step attacks; to incorporate as many different attack techniques as possible, attack scenarios can be launched with many different variations of specific attack steps. Each scenario targets certain components or services in the network, which are described in the following.

### Videoserver Scenario

In the video server scenario, an attacker first scans the network for vulnerabilities. After disclosing a vulnerable CCTV software on a video server, the attacker gains access to the DMZ through unauthenticated remote code execution. Subsequently, one of several vulnerabilities is used by the attacker to escalate privileges. Finally, using root permissions, the attacker is able to pause the CCTV image momentarily, potentially allowing intruders to physically invade the enterprise without being recorded.

<img src="/docs/images/AttackBed-Videoserver.png" alt="Videoserver Scenario" style="width:600pt;"/>

### Linux Malware Scenario

The Linux malware scenario uses the same network components as the video server scenario. An attacker gains access to the system through a remote service and manages to increase their privileges there. Next, the malicious actor installs a post exploitation toolkit to persist their access. In a variation of this scenario, the attacker installs a Linux rootkit to hide the post exploitation toolkit.

### Lateral Movement Scenario

In the lateral movement scenario, the attacker gains access to a repository server in the DMZ through various remote services. By sniffing network connections, they obtain access credentials that provide administrator permissions. Next, the malicious actor gains access to a linux share in the local network through various vulnerabilities. Finally, the attacker executes various malicious payloads (such as a ransomware attack) on the target system. 

<img src="/docs/images/AttackBed-LateralMovement.png" alt="Lateral Movement Scenario" style="width:600pt;"/>

### MITRE Navigator

The following figure shows which tactics and techniques are currently covered by the aforementioned scenarios:

<img src="/docs/images/Szenario1_2_3.png" alt="MITRE Navigator" style="width:600pt;"/>


## Requirements

* [OpenStack](https://www.openstack.org/)
* [OpenTofu](https://opentofu.org/)
* [Terragrunt](https://terragrunt.gruntwork.io/)
* [Ansible](https://www.ansible.com/)

## Documentation

* [Installation](https://aeciddocs.ait.ac.at/attackbed/current/installation/overview.html)
* [Documentation](https://aeciddocs.ait.ac.at/attackbed/current/)

## Publications

If you use the testbed environment or any of the generated datasets, please cite the following publications: 

* Landauer M., Skopik F., Frank M., Hotwagner W., Wurzenberger M., Rauber A. (2023): [Maintainable Log Datasets for Evaluation of Intrusion Detection Systems.](https://ieeexplore.ieee.org/abstract/document/9866880) IEEE Transactions on Dependable and Secure Computing, vol. 20, no. 4, pp. 3466-3482. \[[PDF](https://arxiv.org/pdf/2203.08580.pdf)\]
* Landauer M., Skopik F., Wurzenberger M., Hotwagner W., Rauber A. (2021): [Have It Your Way: Generating Customized Log Data Sets with a Model-driven Simulation Testbed.](https://ieeexplore.ieee.org/document/9262078) IEEE Transactions on Reliability, Vol.70, Issue 1, pp. 402-415. IEEE. \[[PDF](https://www.skopik.at/ait/2020_trel.pdf)\]
* Landauer M., Frank M., Skopik F., Hotwagner W., Wurzenberger M., Rauber A. (2022): [A Framework for Automatic Labeling of Log Datasets from Model-driven Testbeds for HIDS Evaluation.](https://dl.acm.org/doi/abs/10.1145/3510547.3517924) Proceedings of the Workshop on Secure and Trustworthy Cyber-Physical Systems, pp. 77-86. ACM. \[[PDF](https://www.skopik.at/ait/2022_satcps.pdf)\]

## Contact

[Austrian Institute of Technology](https://www.ait.ac.at/en/research-topics/cyber-security)

## License

GNU General Public License v3.0
