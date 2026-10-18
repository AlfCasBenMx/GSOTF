"""Explicit device inventory report; all destination credentials are external."""
import json
import os
import socket
import subprocess
import requests
import StartSettings


def get_anydesk_id():
    return subprocess.run(["anydesk", "--get-id"], capture_output=True, text=True,
                          timeout=5, check=True).stdout.strip()


def get_ip(interface):
    result = subprocess.run(["ip", "-j", "-4", "addr", "show", interface],
        capture_output=True, text=True, timeout=5)
    if result.returncode:
        return None
    for row in json.loads(result.stdout):
        for address in row.get("addr_info", []):
            if address.get("scope") == "global":
                return address["local"]
    return None


def main():
    StartSettings.startVar(required=("serialLiper",))
    payload = {"SerialLiper": StartSettings.serialLiper, "IdAnyDesk": get_anydesk_id(),
               "IpWifi": get_ip("wlan0"), "IpEthernet": get_ip("eth0")}
    endpoint = os.environ.get("GDF_DEVICE_INFO_URL")
    if endpoint:
        with requests.post(endpoint, json=payload, timeout=(5, 15)) as response:
            response.raise_for_status()
    token, chat = os.environ.get("GDF_TELEGRAM_TOKEN"), os.environ.get("GDF_TELEGRAM_CHAT")
    if token and chat:
        import telepot
        telepot.Bot(token).sendMessage(chat, socket.gethostname() + "\n" + json.dumps(payload))


if __name__ == "__main__":
    main()
