name: Spruce Hall charger alerts

on:
  schedule:
    # GitHub cron uses UTC. These cover Denver business hours in both MST and MDT;
    # the local-time check below enforces the precise 8:00–17:00 window.
    - cron: '2-59/5 14-23 * * 1-5'
    - cron: '2-59/5 0 * * 2-6'
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: spruce-charger
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 4
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install browser
        run: |
          python -m pip install playwright
          python -m playwright install --with-deps chromium
      - name: Check station and send alert if a port just became available
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python spruce_charger_alert.py
      - name: Save last verified port statuses
        run: |
          if [ -n "$(git status --porcelain -- charger_state.json)" ]; then
            git config user.name 'github-actions[bot]'
            git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
            git add charger_state.json
            git commit -m 'Update Spruce Hall charger status'
            git push
          fi
