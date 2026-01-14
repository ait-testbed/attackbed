===================
Docker (Scenario 7)
===================

.. image:: ../../images/AttackBed-Docker.drawio.png

Attacker Steps:
---------------

1. Attacker enumerates subdomains of corporate domain-zone(T1590.002,T1591)
2. Attacker scans Host with smtp-enum(T1589.002)
3. Attacker brute-forces imap using the already enumerated username(T1078.002,T1110.001,T1133)
4. Attacker connects to webport to find out about nextcloud(T1592.002)
5. Attacker exploits nextcloud using a compromised acccount(T1586) which runs inside a container(T1190,T1059.004,T1095)
6. Attacker discovers user-id(T1033)
7. Attacker asks exposed docker-daemon for running containers(T1057)
8. Attacker discovers docker-networks using the exposed docker-daemon(T1016)
9. Attacker breaks out using exposed docker-daemon-api and schedules execution of sliver-malware(T1610,T1525,T1053.003,T1210) 
10. Attacker uses sliver to list files after container-escape(T1083)
11. Attacker uses sliver to list processes after container-escape(T1057)
12. Attacker uses sliver to dump /etc/shadow credentials(T1003.008,T1041)


