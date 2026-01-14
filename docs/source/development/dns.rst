.. _development_dns:

========
DNS
========

DNS is an important part of some attacks of the scenarios. For that reason there is a server named ``corpdns``, which plays the role of the authoritative DNS server for the public domain attackbed.com of the corporate network and which is targeted by the attacker. 

There also is a server named ``inetdns`` (called 'Public DNS' in the diagrams) which plays the analogue of e.g. the Google DNS server 8.8.8.8 in the real world. This server is used by all machines in the AttackBed for actual communication with the Internet and therefore is not manipulated by the attacker. It redirects queries regarding the domain attackbed.com to ``corpdns``.

``corpdns`` holds the records for the domain attackbed.com, and hostnames like fw.attackbed.com. These records point to 192.42.0.254, which is the 'fake internet' address of ``inetfw``, the firewall that is part of the attack scenarios - ``inetfw`` also runs dnsmasq and resolves all queries for the zone attackbed.local. Other DNS queries ``inetfw`` forwards to ``inetdns``.

So for all machines inside the corporate network, ``inetfw`` will be the first DNS server address, which then either resolves the queries (if they're for attackbed.local), or it will forward them to ``inetdns``.  ``inetdns`` in turn forwards them to ``corpdns``, if they concern the domain-zone attackbed.com. Otherwise queries will be forwarded to the resolver that is configured(for example 8.8.8.8).

``inetfw``, ``inetdns`` and ``corpdns`` have IP addresses in the public range 192.42.0.0/16, which is not connected to the actual internet directly, to allow a 'fake' internet to be established - so that the attacks can simulate a real world scenario with public IP addresses more realistically. Traffic in this subnet does NOT get routed over the actual internet, and it is not accessible from the internet.

Example query:

Host puppet wants to know attackbed.com:
The DNS query goes to ``inetfw``, ``inetfw`` forwards it to ``inetdns``, which forwards the query for attackbed.com to ``corpdns``. This returns the IP address back through the chain to host puppet.

