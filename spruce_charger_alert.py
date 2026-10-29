"""One check of Spruce Hall 1, ports 1 and 2. Run by spruce_charger.yml.

The parser is deliberately strict and UNVERIFIED for this station. If the page
can't show two unambiguous statuses, the job fails without sending an alert.
"""
import json
import os
import re
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://driver.chargepoint.com/stations/1841901"
STATE = Path("charger_state.json")
PORT = re.compile(r"^port\s*([12])(?:\s*[:#-].*)?$", re.I)
AVAILABLE = re.compile(r"^(?:available|free|open)$", re.I)
BUSY = re.compile(r"^(?:in use|in-use|occupied|unavailable|charging|reserved|out of service|offline|unknown)$", re.I)


def read_ports():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)
            lines = [s.strip() for s in page.locator("body").inner_text().splitlines() if s.strip()]
        finally:
            browser.close()

    result = {}
    for i, line in enumerate(lines):
        match = PORT.fullmatch(line)
        if not match:
            continue
        port = match.group(1)
        following = []
        for item in lines[i + 1:i + 9]:
            if PORT.fullmatch(item):
                break
            following.append(item)
        found = ["available" if AVAILABLE.fullmatch(s) else "busy" for s in following
                 if AVAILABLE.fullmatch(s) or BUSY.fullmatch(s)]
        print(f"Port {port}: nearby text {following!r}; statuses {found!r}", flush=True)
        if len(found) != 1 or port in result:
            raise ValueError(f"Port {port} is ambiguous; no notification sent")
        result[port] = found[0]
    if set(result) != {"1", "2"}:
        print("Page text excerpt:", " | ".join(lines[:1000])[:9000], flush=True)
        raise ValueError("Cannot verify both ports from the public page; no notification sent")
    return result


def notify(ports):
    topic = os.environ["NTFY_TOPIC"]
    names = ", ".join(f"port {p}" for p in ports)
    request = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=f"Spruce Hall 1: {names} available. Check status before driving over: {URL}".encode(),
        headers={"Title": "Spruce Hall charger available", "Click": URL, "Tags": "electric_plug"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def main():
    current = read_ports()
    print(f"Verified statuses: {current}", flush=True)
    previous = json.loads(STATE.read_text()) if STATE.exists() else None
    if previous is None:
        print("First verified check: saving baseline; no alert yet.", flush=True)
    else:
        newly_free = [p for p in ("1", "2") if current[p] == "available"
                      and previous.get(p) != "available"]
        if newly_free:
            notify(newly_free)
            print(f"Notified about port(s): {newly_free}", flush=True)
    if previous != current:
        STATE.write_text(json.dumps(current, indent=2) + "\n")


if __name__ == "__main__":
    main()
