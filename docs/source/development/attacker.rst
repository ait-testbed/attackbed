.. _development_attacker:

===========================
Attacker Services and Ports
===========================

The attacker machine runs several services to support various attack scenarios, C2 operations, and simulation management. The following table lists the key services identified listening for connections based on typical ``netstat`` output:

.. list-table:: Attacker Service Ports
   :widths: 15 30 15 40
   :header-rows: 1

   * - Protocol
     - Service
     - Port(s)
     - Reference / Tool Link
   * - TCP
     - SSH Daemon
     - 22
     - `OpenSSH <https://www.openssh.com/>`_
   * - TCP
     - Apache HTTP Server
     - 80
     - `Apache HTTP Server Project <https://httpd.apache.org/>`_
   * - TCP
     - x11vnc (VNC Server)
     - 5900
     - `x11vnc <https://github.com/LibVNC/x11vnc>`_
   * - TCP
     - Bettercap API/UI (Localhost)
     - 8081
     - `Bettercap <https://www.bettercap.org/>`_
   * - TCP
     - PostgreSQL (Localhost)
     - 5433
     - `PostgreSQL <https://www.postgresql.org/>`_
   * - TCP
     - Metasploit RPC Daemon (msfrpcd)
     - 55553
     - `Metasploit Framework <https://www.metasploit.com/>`_
   * - TCP/UDP
     - RustDesk Server (ID/Relay)
     - 21115-21119
     - `RustDesk <https://rustdesk.com/>`_
   * - UDP (QUIC)
     - VeilTransfer Server
     - 443
     - `VeilTransfer <https://github.com/infosecn1nja/VeilTransfer/>`_

.. note::
   Specific attack playbooks might start additional temporary web servers (e.g., using Python's ``http.server``) on other ports (like 8080, 8082, 8083) to serve payloads or tools. These are typically short-lived and may not appear in a static ``netstat`` snapshot.


Scenario Usage
--------------

The services listed above are utilized across different scenarios as follows:

*   **SSH (Port 22):** Provides general management access to the attacker machine and is used for establishing tunnels (e.g., via the MGMT host) to access internal services like VNC on client machines during playbook execution.

*   **Apache (Port 80):** Can serve as a general-purpose web server. 

*   **VNC (x11vnc, Port 5900):** Primarily used by the automation framework (AttackMate) to control the graphical interface of simulated machines (both attacker and victim VNC sessions) for tasks like configuring attacker tools (e.g., RustDesk client) or simulating user actions directed on the victim (e.g., opening documents, installing software via social engineering).

*   **Bettercap (Port 8081 - Localhost):** The backend API/UI for Bettercap. It is used in Scenario 5 (LAN Turtle) to perform ARP spoofing (``arp.spoof``) and SSL stripping (``http.proxy.sslstrip``), controlled via a ``.cap`` file.

*   **PostgreSQL (Port 5433 - Localhost):** Serves as the backend database for the Metasploit Framework, storing workspace data, host information, credentials, etc. Essential for Metasploit's operation but not directly interacted with by scenario logic.

*   **Metasploit RPC (msfrpcd, Port 55553):** Allows programmatic control of the Metasploit Framework. Attackmate playbooks use this interface extensively to:
    *   Generate payloads (``msfvenom`` commands).
    *   Start handlers (``exploit/multi/handler``) to receive reverse shells 
    *   Interact with established Meterpreter sessions (uploading files, running commands, obtaining shells).

*   **RustDesk Server (Ports 21115-21119):** Provides the necessary backend infrastructure (ID/Rendezvous server ``hbbs`` and Relay server ``hbbr``) for establishing connections using the RustDesk remote access tool. This is central to scenario 6 involving attacker control via RustDesk screensharing.

*   **VeilTransfer Server (UDP Port 443):** Acts as the listener for data exfiltrated using the VeilTransfer client over the QUIC protocol. This is used for stealthy data exfiltration in variations of Scenario 6.