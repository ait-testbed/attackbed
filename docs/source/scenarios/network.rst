======================
Network (Scenario 4)
======================

.. image:: ../../images/AttackBed-Network.png

Attacker Steps:
---------------

1. Attacker is already on machine in DMZ (Reposerver) (T1078.003)
2. Attacker gets access on firewall via ssh that is open in DMZ via user and password reuse from step 1 (T1078.003)
3. Attacker installs malware that uses portknocking (T1105, T1205.001) on firewall
4. Attacker persists by creating systemd service that starts port knocking daemon (T1543.002)
4. Knock sequence triggers a script that downloads and executes sliver malware (T1205.001,T1071.001)
5. Attacker connects via sliver malware (T1071.001)
6. Attacker modifies iptables so that DMZ host is allowed to connect to a server in the lan (Linuxshare) (T1599)
7. Attacker connects to the linux fileshare server in the lan via the DMZ host, user and password reuse from step 1 (T1078.003)
