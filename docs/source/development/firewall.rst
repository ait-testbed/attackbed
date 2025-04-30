.. _firewall_connections:

Firewall Connections Per Scenario
=================================

This document outlines the expected network connections traversing the firewall for each automated attack scenario. The firewall configuration (Shorewall) is defined in the ``packer/firewall/playbook/main.yml`` Ansible playbook.

Firewall Zones and Policies Overview
------------------------------------

The firewall defines several network zones:

*   **inet**: The external internet zone (Interface: ``ens3``)
*   **lan**: The internal LAN zone (Interface: ``ens4``, Subnet: ``192.168.100.0/24``)
*   **dmz**: The Demilitarized Zone (Interface: ``ens5``, Subnet: ``172.17.100.0/24``)
*   **admin**: The administrative network zone (Interface: ``ens6``, Subnet: ``10.12.0.0/24``)
*   **user**: The user network zone (Interface: ``ens7``, Subnet: ``192.168.50.0/24``)
*   **fw**: The firewall itself.

Default policies between zones:

*   ``fw -> all``: ACCEPT
*   ``admin -> all``: ACCEPT
*   ``lan -> inet``: ACCEPT
*   ``lan -> dmz``: ACCEPT
*   ``dmz -> inet``: ACCEPT
*   ``user -> all``: REJECT (Specific rules override this)
*   ``all -> all``: REJECT (Default deny for any traffic not explicitly matched)

Key Host IPs from configuration:

*   **REPOSERVER**: ``172.17.100.122`` (dmz)
*   **LINUXSHARE**: ``192.168.100.23`` (lan)
*   **VIDEOSERVER**: ``172.17.100.121`` (dmz)
*   **KAFKA**: ``192.168.100.10`` (lan)
*   **Firewall (inetfw)**: Public IP ``192.42.0.254`` (for knocking, from scenario 4), Internal IPs on respective zone interfaces.
*   **Attacker**: ``192.42.1.174`` (inet)
*   **inetdns**: Public DNS server, delegates requests for ``faaacebook.com``, ``facebock.com``, ``dailynews-wire.com`` to Attacker IP.

Scenario Connections
--------------------

Below are the specific connections for each scenario.

.. note::
    Connections listed as (POLICY) are allowed by the default zone-to-zone policies. Connections listed as (RULE) are allowed by specific entries in the ``rules`` section. Connections listed as (DNAT) involve port forwarding from the ``inet`` zone to an internal host.

Scenario 1: Videoserver / ZoneMinder Exploit 
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario targets the ZoneMinder service running on the ``VIDEOSERVER`` in the DMZ.

*   **Reconaissance (DNS Enumeration):**
        ``inet (Attacker) -> fw`` | TCP Top 100 Ports |  Attacker performs nmap scan to firewall IP (top 100 ports even if fhe ports are not open) 
*   **Reconaissance (Host/Service Scanning):**
        ``inet (Attacker) -> inet (CorpsDNS)`` | UDP/TCP Port 53 | Attacker performs DNS enumeration
*   **Initial Access & Exploitation:**
        ``inet (Attacker) -> dmz (VIDEOSERVER)`` | TCP Port 80 | (DNAT) - Attacker accesses the ZoneMinder web interface via the firewall's public IP, forwarded to the ``VIDEOSERVER``.
*   **Command and Control (Reverse Shell):**
        ``dmz (VIDEOSERVER) -> inet (Attacker)`` | TCP Port <LPORT> (e.g. 3333) | (POLICY: `dmz -> inet ACCEPT`) - Meterpreter reverse shell connection initiated from the compromised ``VIDEOSERVER`` back to the attacker's listener.
*   **Payload Download:**
        ``dmz (VIDEOSERVER) -> inet (Attacker)`` | TCP Port 80 | (POLICY: `dmz -> inet ACCEPT`) - Compromised ``VIDEOSERVER`` downloads additional payloads (e.g., `pam_unix.so`, command files like `README.txt.*`) from the attacker's web server.
*   **Post-Exploitation (SSH Access):**
        ``inet (Attacker) -> dmz (VIDEOSERVER)`` | TCP Port 2222 | (DNAT) - Attacker connects via SSH to the ``VIDEOSERVER`` (port 22 on server) using keys added during exploitation (e.g., via `README.txt` command execution).
*   **DNS Lookups:**
        ``dmz (VIDEOSERVER) -> fw`` | TCP/UDP Port 53 | (RULE: `DNS/ACCEPT`) - ``VIDEOSERVER`` performing DNS lookups via the firewall.

.. list-table:: Scenario 1 Firewall Connections
   :widths: 25 20 20 15 20
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - Reconaissance
     - ``inet (Attacker)``
     - ``fw``
     - TCP Top 100 Ports
     - - Intra-zone
   * - Reconaissance
     - ``inet (Attacker)``
     - ``inet (CorpsDNS)``
     - TCP 53
     - Intra-zone
   * - Initial Access
     - ``inet (Attacker)``
     - ``dmz (VIDEOSERVER)``
     - TCP 80
     - DNAT
   * - Command & Control
     - ``dmz (VIDEOSERVER)``
     - ``inet (Attacker)``
     - TCP 3333
     - POLICY: ``dmz -> inet ACCEPT``
   * - Payload Download
     - ``dmz (VIDEOSERVER)``
     - ``inet (Attacker)``
     - TCP 80
     - POLICY: ``dmz -> inet ACCEPT``
   * - Post-Exploitation SSH
     - ``inet (Attacker)``
     - ``dmz (VIDEOSERVER)``
     - TCP 2222
     - DNAT
   * - DNS Lookup (Victim)
     - ``dmz (VIDEOSERVER)``
     - ``fw``
     - TCP/UDP 53
     - RULE: ``DNS/ACCEPT``

Scenario 2: Linux Malware
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario involves exploiting a vulnerability on the ``VIDEOSERVER``, using DNS redirection and privilege escalation techniques.

*   **DNS Redirection Setup:**
        ``inet (Attacker) -> inetdns`` | (Configuration Task) - Attacker configures `inetdns` to resolve ``faaacebook.com`` to the Attacker's IP.
*   **Initial Access & Exploitation:**
        ``inet (Attacker) -> dmz (VIDEOSERVER)`` | TCP Port 80 | (DNAT) - Initial interaction with the ``VIDEOSERVER`` web service.
*   **DNS Lookups:**
        ``dmz (VIDEOSERVER) -> fw`` | TCP/UDP Port 53 | (RULE: `DNS/ACCEPT`) - ``VIDEOSERVER`` queries the firewall for DNS.
        ``fw -> inetdns / inet`` | TCP/UDP Port 53 | (POLICY: `fw -> all ACCEPT`) - Firewall forwards DNS query, receiving the malicious Attacker IP for ``faaacebook.com``.
*   **Payload Download / Malicious Site Access:**
        ``dmz (VIDEOSERVER) -> inet (Attacker)`` | TCP Port 80 | (POLICY: `dmz -> inet ACCEPT`) - ``VIDEOSERVER`` connects to the Attacker's IP (resolved via malicious DNS) to download payloads (`glibc_rootjail.tar.xz`).
        ``dmz (VIDEOSERVER) -> inet (Attacker)`` | TCP Port 443 | (POLICY: `dmz -> inet ACCEPT`) - Sliver connection from ``VIDEOSERVER`` to Attacker.
*   **SSH:**
        ``inet (Attacker) -> dmz (VIDEOSERVER)`` | TCP Port 2222 | (DNAT) - Attacker uses the stolen SSH key (`privesc_key_videoserver`) to log into ``VIDEOSERVER`` via the DNAT rule.

.. list-table:: Scenario 2 Firewall Connections
   :widths: 25 20 20 15 20
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - DNS Setup
     - ``inet (Attacker)``
     - ``inetdns``
     - N/A
     - Config Task
   * - Initial Access
     - ``inet (Attacker)``
     - ``dmz (VIDEOSERVER)``
     - TCP 80
     - DNAT
   * - DNS Lookup (Victim)
     - ``dmz (VIDEOSERVER)``
     - ``fw``
     - TCP/UDP 53
     - RULE: ``DNS/ACCEPT``
   * - DNS Lookup (Firewall)
     - ``fw``
     - ``inetdns / inet``
     - TCP/UDP 53
     - POLICY: ``fw -> all ACCEPT``
   * - Payload Download
     - ``dmz (VIDEOSERVER)``
     - ``inet (Attacker)``
     - TCP 80
     - POLICY: ``dmz -> inet ACCEPT``
   * - Command & Control
     - ``dmz (VIDEOSERVER)``
     - ``inet (Attacker)``
     - TCP `443`
     - POLICY: ``dmz -> inet ACCEPT``
   * - Post-Exploitation SSH
     - ``inet (Attacker)``
     - ``dmz (VIDEOSERVER)``
     - TCP 2222
     - DNAT

Scenario 3: Lateral Movement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario involves brute-forcing credentials and moving laterally within the network.

*   **Initial Access (Credential Attack):**
        ``inet (Attacker) -> dmz (REPOSERVER)`` | TCP Port 10022 | (DNAT) - SSH brute-force attempt against ``REPOSERVER``.

        ``inet (Attacker) -> dmz (REPOSERVER)`` | TCP Port 5901 | (DNAT) - VNC brute-force attempt against ``REPOSERVER``.
*   **Lateral Movement (From compromised DMZ host, e.g., REPOSERVER):**
        ``dmz (REPOSERVER) -> lan (KAFKA)`` | TCP Port 9092 | (RULE) - Accessing Kafka service.

        ``dmz (REPOSERVER) -> fw`` | TCP Port 22 | (RULE: `SSH/ACCEPT`) - SSH connection to the firewall.

        ``dmz (REPOSERVER) -> fw`` | TCP/UDP Port 53 | (RULE: `DNS/ACCEPT`) - DNS lookups via the firewall.

        ``dmz (REPOSERVER) -> lan (LINUXSHARE)`` | TCP Port 1881 | (RULE) - Healthcheck service, sending hostname and status message

        ``dmz (REPOSERVER) -> lan (LINUXSHARE)`` | TCP/UDP 111, 2049 | (RULE) - Access File Share
*   **Command and Control:**
        ``lan (LINUXSHARE) -> inet (Attacker)`` | TCP Port 4444 | (POLICY: `lan -> inet ACCEPT`) - Reverse shell from compromised hosts.



.. list-table:: Scenario 3 Firewall Connections
   :widths: 30 20 20 15 15
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - Initial Access (SSH Brute)
     - ``inet (Attacker)``
     - ``dmz (REPOSERVER)``
     - TCP 10022
     - DNAT
   * - Initial Access (VNC Brute)
     - ``inet (Attacker)``
     - ``dmz (REPOSERVER)``
     - TCP 5901
     - DNAT
   * - Lateral (-> LinuxShare Service)
     - ``dmz (REPOSERVER)``
     - ``lan (LINUXSHARE)``
     - TCP 1881
     - RULE
   * - Lateral (-> LinuxShare Filesystem)
     - ``dmz (REPOSERVER)``
     - ``lan (LINUXSHARE)``
     - TCP/UDP 111, 2049
     - RULE
   * - Lateral (-> Kafka)
     - ``dmz (REPOSERVER)``
     - ``lan (KAFKA)``
     - TCP 9092
     - RULE
   * - Lateral (-> Firewall SSH)
     - ``dmz (REPOSERVER)``
     - ``fw``
     - TCP 22
     - RULE: ``SSH/ACCEPT``
   * - Lateral (-> Firewall DNS)
     - ``dmz (REPOSERVER)``
     - ``fw``
     - TCP/UDP 53
     - RULE: ``DNS/ACCEPT``
   * - Command & Control 
     - ``lan (LINUXSHARE)``
     - ``inet (Attacker)``
     - TCP `4444`
     - POLICY: ``dmz -> inet ACCEPT``


Scenario 4: Network
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario uses port knocking on the firewall to trigger actions and establish command and control.

*   **Port Knocking:**
        ``inet (Attacker) -> fw (Public IP: 192.42.0.254)`` | TCP/UDP Ports 32768, 28977, 51234 | (Implicit Allow for Knockd) - Attacker sends the knock sequence to the firewall's external interface.
*   **Triggered Action (Payload Download):**
        ``fw -> inet (Attacker)`` | TCP Port 80 | (POLICY: `fw -> all ACCEPT`) - The `system-verify.sh` script, triggered by the knock and running on the firewall (`fw`), connects out to the attacker's web server to download the implant (`auditf.tar.gz`).
*   **Command and Control (Sliver/Implant):**
        ``fw -> inet (Attacker)`` | TCP/UDP Port 443 | (POLICY: `fw -> all ACCEPT`) - The implant (`auditf`) running on the firewall connects back to the attacker's C2 server.
*   **DNS Lookups:**
        ``fw -> inetdns / inet`` | TCP/UDP Port 53 | (POLICY: `fw -> all ACCEPT`) - Firewall performs DNS lookups needed by triggered scripts or implants.


.. list-table:: Scenario 4 Firewall Connections
   :widths: 25 20 20 15 20
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - Port Knocking
     - ``inet (Attacker)``
     - ``fw (Public IP)``
     - TCP/UDP 32768, 28977, 51234
     - Implicit Allow (Knockd)
   * - Triggered Download
     - ``fw``
     - ``inet (Attacker)``
     - TCP 80/443
     - POLICY: ``fw -> all ACCEPT``
   * - Command & Control
     - ``fw``
     - ``inet (Attacker)``
     - TCP/UDP `443`
     - POLICY: ``fw -> all ACCEPT``
   * - DNS Lookup (Firewall)
     - ``fw``
     - ``inetdns / inet``
     - TCP/UDP 53
     - POLICY: ``fw -> all ACCEPT``

Scenario 5: Lan Turtle
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario uses ARP spoofing within the `lan` zone to capture a session cookie and reuse it.

*   **ARP Spoofing Traffic (if Attacker in `lan` zone):**
        ``lan (Attacker) <-> lan (adminpc1)`` | ARP | (Intra-zone, local broadcast) - Attacker poisons ARP cache of `adminpc1`.
        ``lan (adminpc1) -> dmz (VIDEOSERVER)`` | TCP Port 80 | (Intercepted by Attacker, then forwarded) - Legitimate traffic from `adminpc1` to `VIDEOSERVER` passes through the firewall, intercepted/relayed by the Attacker in the `lan` zone.
*   **Session Hijacking (Attacker reusing cookie):**
        ``lan (Attacker) -> dmz (VIDEOSERVER)`` | TCP Port 80 | (POLICY: `lan -> all ACCEPT`) - Attacker makes HTTP requests to the ``VIDEOSERVER`` using the stolen session cookie.



.. list-table:: Scenario 5 Firewall Connections
   :widths: 30 20 20 15 15
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - ARP Spoofing *(Lan Zone)*
     - ``lan (Attacker)``
     - ``lan (adminpc1)``
     - ARP
     - Intra-zone
   * - Intercepted Traffic *(Lan Zone)*
     - ``lan (adminpc1)``
     - ``dmz (VIDEOSERVER)``
     - TCP 80
     - POLICY: ``lan -> all ACCEPT``
   * - Session Hijack *(Lan Zone)*
     - ``lan (Attacker)``
     - ``dmz (VIDEOSERVER)``
     - TCP 80
     - POLICY: ``lan-> dmz ACCEPT``

Scenario 6: Client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This scenario involves tricking a user on the `client` machine (in the `user` zone) into opening an office document with a malicious macro or installing a malicious browser extension.

*   **DNS Setup:**
        ``inet (Attacker) -> inetdns`` | (Configuration Task) - Attacker configures `inetdns` to resolve ``facebock.com`` and ``dailynews-wire.com`` to the Attacker's IP.
*   **Initial Contact / Phishing (User interaction):**
        ``user (client) -> fw`` | TCP/UDP Port 53 | (RULE: `DNS/ACCEPT`) - Client performs DNS lookups for phishing domains.
        ``fw -> inetdns / inet`` | TCP/UDP Port 53 | (POLICY: `fw -> all ACCEPT`) - Firewall resolves DNS, getting malicious IP.
        ``user (client) -> fw`` | TCP Port 3128 | (RULE) - Client connects to Squid proxy on firewall for web access.
        ``fw -> inet (Attacker IP / Phishing Site)`` | TCP Port 80/443 | (POLICY: `fw -> all ACCEPT`) - Firewall (Squid proxy) connects to the attacker-controlled website.
*   **Payload Download (Extension/Malware):**
        ``user (client) -> fw`` | TCP Port 3128 | (RULE) - Client connects to Squid proxy.
        ``fw -> inet (Attacker IP)`` | TCP Port 80 / 5000 (Flask server) | (POLICY: `fw -> all ACCEPT`) - Firewall (Squid proxy) downloads `extension.xpi`, `Nutzungshinweise.odt`, `firefox-startup` etc. from the attacker's HTTP server.
*   **Command and Control:**
        ``user (client) -> fw`` | TCP Port 3128 | (RULE) - Extension traffic goes through the proxy.
        ``user (client) -> inet (Attacker IP)`` | TCP Port 4443 | (RULE)
        ``user (client) -> inet (Attacker IP)`` | UDP Port 443 | (RULE) - If using VeilTransfer.
        ``user (client) -> inet (Attacker IP)`` | TCP Ports 21114-21118, 8000 / UDP 21116 | (RULE) - If using RustDesk.


.. list-table:: Scenario 6 Firewall Connections
   :widths: 30 20 20 15 15
   :header-rows: 1

   * - Phase / Action
     - Source
     - Destination
     - Protocol / Port
     - Firewall Rule/Policy
   * - DNS Setup
     - ``inet (Attacker)``
     - ``inetdns``
     - N/A
     - Config Task
   * - DNS Lookup (Client)
     - ``user (client)``
     - ``fw``
     - TCP/UDP 53
     - RULE: ``DNS/ACCEPT``
   * - DNS Lookup (Firewall)
     - ``fw``
     - ``inetdns / inet``
     - TCP/UDP 53
     - POLICY: ``fw -> all ACCEPT``
   * - Phishing Access (Proxy Conn)
     - ``user (client)``
     - ``fw``
     - TCP 3128
     - RULE
   * - Phishing Access (FW to Site)
     - ``fw``
     - ``inet (Attacker IP)``
     - TCP 80/443
     - POLICY: ``fw -> all ACCEPT``
   * - Payload Download (Proxy Conn)
     - ``user (client)``
     - ``fw``
     - TCP 3128
     - RULE
   * - Payload Download (FW to Server)
     - ``fw``
     - ``inet (Attacker IP)``
     - TCP 80 / 5000
     - POLICY: ``fw -> all ACCEPT``
   * - C2 (via Proxy - Client)
     - ``user (client)``
     - ``fw``
     - TCP 3128
     - RULE
   * - C2 (Direct - Reverse TCP Alt.)
     - ``user (client)``
     - ``inet (Attacker IP)``
     - TCP 4443
     - RULE
   * - C2 (Direct - VeilTransfer/UDP)
     - ``user (client)``
     - ``inet (Attacker IP)``
     - UDP 443
     - RULE
   * - C2 (Direct - RustDesk)
     - ``user (client)``
     - ``inet (Attacker IP)``
     - TCP 21114-8, 8000; UDP 21116
     - RULE
