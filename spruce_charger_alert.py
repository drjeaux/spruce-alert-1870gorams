"""Watch ChargePoint station 1841901 and send phone alerts via ntfy.

Install: pip install playwright && playwright install chromium
Phone: install the ntfy app and subscribe to a long, random topic of your choice.
Run: NTFY_TOPIC=your-long-random-topic python spruce_charger_alert.py
Keep this process running on an always-on computer. Set CHECK_SECONDS as desired.

First run prints the public page text around ports 1 and 2. If it cannot
unambiguously identify both port statuses, it will NOT send an alert.
The page's markup may change; check the printed text before relying on it.
"""
import os
import re
import time
import urllib.request
from playwright.sync_api import sync_playwright

URL = "https://driver.chargepoint.com/stations/1841901"
TOPIC = os.environ["NTFY_TOPIC"]
INTERVAL = max(60, int(os.getenv("CHECK_SECONDS", "120")))
PORT = re.compile(r"^port\s*([12])(?:\s*[:#-].*)?$", re.I)
AVAILABLE = re.compile(r"^(?:available|free|open)$", re.I)
BUSY = re.compile(r"^(?:in use|in-use|occupied|unavailable|charging|reserved|out of service|offline|unknown)$", re.I)


def read_ports(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)  # Let client-rendered status load.
    lines = [s.strip() for s in page.locator("body").inner_text().splitlines() if s.strip()]
    result = {}
    for i, line in enumerate(lines):
        match = PORT.fullmatch(line)
        if not match:
            continue
        port = int(match.group(1))
        # Stop at the next port heading so one port cannot borrow another's status.
        following = []
        for item in lines[i + 1:i + 9]:
            if PORT.fullmatch(item):
                break
            following.append(item)
        statuses = ["available" if AVAILABLE.fullmatch(s) else "busy"
                    for s in following if AVAILABLE.fullmatch(s) or BUSY.fullmatch(s)]
        if len(statuses) == 1 and port not in result:
            result[port] = statuses[0]
        print(f"Port {port} nearby text: {following!r}; matched: {statuses!r}", flush=True)
    return result if set(result) == {1, 2} else None


def notify(ports):
    names = ", ".join(f"port {p}" for p in ports)
    request = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}",
        data=f"Spruce Hall 1: {names} available. {URL}".encode(),
        headers={"Title": "EV charger available", "Click": URL, "Tags": "electric_plug"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response.read()


def main():
    previous = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        while True:
            try:
                current = read_ports(page)
                if current is None:
                    print("Could not verify both port statuses; no alert sent.", flush=True)
                else:
                    print(f"Current status: {current}", flush=True)
                    newly_free = [p for p in (1, 2) if current[p] == "available"
                                  and (previous is None or previous[p] != "available")]
                    if newly_free:
                        notify(newly_free)
                    previous = current  # Only advance after a successful notification.
            except Exception as exc:
                print(f"Check failed; leaving previous status unchanged: {exc}", flush=True)
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
