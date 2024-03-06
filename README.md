# Welcome to AIT AECID Testbed!

The AECID Testbed is a simulated enterprise network with numerous vulnerabilities.  Attacks in this testbed are executed automized and cover as many tactics and techniques of the mitre enterprise framework as possible.  
 
# Scenarios

The testbed simulates an enterprise IT network, involving mail servers, file share, firewall, intranet, DMZ, DNS, VPN, etc. Log data is collected from many sources, including network traffic, apache access logs, DNS logs, syslog, authentication logs, audit logs, suricata logs, exim/mail logs, monitoring logs, etc. 

## Videoserver Scenario

In the video server scenario, an attacker scans the network for vulnerabilities. Next, the attacker gains access to the DMZ through an unauthenticated remote code execution in the video server. He then increases his privileges through various vulnerabilities. Finally, as the system administrator, he can pause the camera image momentarily, allowing physical access.

<img src="/docs/images/AECID-Testbed-Videoserver.png" alt="Videoserver Scenario" style="width:600pt;"/>


## Lateral Movement Scenario

In the lateral movement scenario, the attacker gains access to a repository server in the DMZ through various remote services. By sniffing network connections, he obtains access data that gives him administrator rights. Next, the malicious actor gains access to a linux share in the local network through various vulnerabilities. Finally, the attacker executes various malicious payloads (such as a ransomware attack) on the target system. 

<img src="/docs/images/AECID-Testbed-LateralMovement.png" alt="Lateral Movement Scenario" style="width:600pt;"/>

## MITRE Navigator

The following tactics and techniques are covered:

<img src="/docs/images/Szenario1_2_3.png" alt="MITRE Navigator" style="width:600pt;"/>


# Requirements

* [OpenStack](https://www.openstack.org/)
* [OpenTofu](https://opentofu.org/)
* [Terragrunt](https://terragrunt.gruntwork.io/)
* [Ansible](https://www.ansible.com/)

# Documentation

* [Installation](https://aeciddocs.ait.ac.at/atb-aecid-testbed/current/installation/overview.html)
* [Documentation](https://aeciddocs.ait.ac.at/atb-aecid-testbed/current/)

# Publications

If you use the Kyoushi Testbed Environment or any of the generated datasets, please cite the following publications: 

* Landauer M., Skopik F., Frank M., Hotwagner W., Wurzenberger M., Rauber A. (2023): [Maintainable Log Datasets for Evaluation of Intrusion Detection Systems.](https://ieeexplore.ieee.org/abstract/document/9866880) IEEE Transactions on Dependable and Secure Computing, vol. 20, no. 4, pp. 3466-3482. \[[PDF](https://arxiv.org/pdf/2203.08580.pdf)\]
* Landauer M., Skopik F., Wurzenberger M., Hotwagner W., Rauber A. (2021): [Have It Your Way: Generating Customized Log Data Sets with a Model-driven Simulation Testbed.](https://ieeexplore.ieee.org/document/9262078) IEEE Transactions on Reliability, Vol.70, Issue 1, pp. 402-415. IEEE. \[[PDF](https://www.skopik.at/ait/2020_trel.pdf)\]
* Landauer M., Frank M., Skopik F., Hotwagner W., Wurzenberger M., Rauber A. (2022): [A Framework for Automatic Labeling of Log Datasets from Model-driven Testbeds for HIDS Evaluation.](https://dl.acm.org/doi/abs/10.1145/3510547.3517924) Proceedings of the Workshop on Secure and Trustworthy Cyber-Physical Systems, pp. 77-86. ACM. \[[PDF](https://www.skopik.at/ait/2022_satcps.pdf)\]

# Contact

[Austrian Institute of Technology](https://www.ait.ac.at/themen/cyber-security)

# License

GNU General Public License v3.0
