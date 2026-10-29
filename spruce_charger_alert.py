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
# The public page lists each connector as status | charging speed | power | plug.
# A separate station-level status appears before the connector listings; ignore it.
CONNECTOR = re.compile(
    r"\b(Available|Free|Open|In Use|Occupied|Charging|Unavailable|Reserved|"
    r"Out of Service|Offline)\s*\|\s*"
    r"\d+(?:\.\d+)?\s*mi\s*/\s*hour\s*\|\s*"
    r"\d+(?:\.\d+)?\s*kW\s*\|\s*\(J1772\)",
    re.I,
)


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

    text = " | ".join(lines)
    # Only inspect this station's connector list, not reviews or map results.
    marker = "COLO STATE UNIV / SPRUCE HALL 1 | 150 Old Main Dr, Fort Collins | ChargePoint Network | "
    if marker not in text or " | Report a Problem" not in text.split(marker, 1)[1]:
        print("Page text excerpt:", text[:9000], flush=True)
        raise ValueError("Cannot locate this station's connector list; no notification sent")
    section = text.split(marker, 1)[1].split(" | Report a Problem", 1)[0]
    matches = list(CONNECTOR.finditer(section))
    plugs = re.findall(r"\(J1772\)", section, re.I)
    if len(plugs) != 2 or len(matches) != 2:
        print("Page text excerpt:", text[:9000], flush=True)
        raise ValueError("Cannot verify both connectors from the public page; no notification sent")
    statuses = [match.group(1).lower() for match in matches]
    available_count = sum(status in {"available", "free", "open"} for status in statuses)
    print(f"Two connector statuses in displayed order: {statuses!r}", flush=True)
    return available_count


def notify(count):
    topic = os.environ["NTFY_TOPIC"]
    request = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=f"Spruce Hall 1: {count} of 2 connectors available. Check before driving over: {URL}".encode(),
        headers={"Title": "Spruce Hall charger available", "Click": URL, "Tags": "electric_plug"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def main():
    current = read_ports()
    print(f"Verified statuses: {current} of 2 connectors available", flush=True)
    previous = json.loads(STATE.read_text()) if STATE.exists() else None
    if previous is None:
        print("First verified check: saving baseline; no alert yet.", flush=True)
    elif current > previous:
        notify(current)
        print(f"Notified: {current} of 2 connectors available", flush=True)
    if previous != current:
        STATE.write_text(json.dumps(current) + "\n")


if __name__ == "__main__":
    main()
