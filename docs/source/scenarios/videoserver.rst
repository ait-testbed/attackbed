======================
Videoserver(Scenario1)
======================

1. Attacker scans DNS-Server of company with dns-brute(T1590,T1591)
2. Attacker scans Host with nmap(T1595) auch mit -O (T1592)
3. Attacker scans Host with nikto(T1595)
4. Attacker uses gobuster to crawl webserver(T1594)
5. Attacker penetrates zoneminder(T1190, T1059)
6. Attacker creates a stable reverse-shell(T1574, T1104) and attaches it to a running process(T1055 https://github.com/W3ndige/linux-process-injection) [KEIN PROZESS ATTACH]
7. Attacker uploads linpeas(T1105) and executes it(T1087, T1083, T1201, T1069, T1057, T1518, T1082, T1614, T1016, T1049, T1033, T1007, T1615)
8. Attacker finds privilege escalation

   a. Polkit exploit(T1068, T1546, T1574)
   b. Sudo weakness (T1548)
   c. Misconfigured systemd-unit(T1547)
   d. Logrotten(T1546)
   e. Misconfigured cron-job(T1053)
   f. Finds ssh-key for root-user(T1078)

9. Attacker gains root
10. Attacker adds backdoor

   a. Attacker adds new ssh-key to authorized_keys(T1098)
   b. Attacker creates new account(T1136)
   c. Attacker modifies pam(T1556)

11. Attacker uses split to proxy command(T1218)
12. Attacker reads from /etc/shadow(T1555)
13. Attacker runs nmap(T1046)  [VERSCHIEBEN IN ANDERES SZENARIO]
14. Attacker runs lspci and lsusb(T1120)  [lsusb ist nicht installiert]
15. Attacker runs ntpdate or date(T1124)  [ntpdate ist nicht installiert]
16. Attacker checks virtualbox-files(T1497)
