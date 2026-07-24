name: Actualizar Precios CEDEARs

on:
  schedule:
    - cron: '0 21 * * 1-5'
  workflow_dispatch:

jobs:
  actualizar:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install yfinance pytz

      - run: python actualizar_precios.py

      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add precios_cedears.json
          git diff --staged --quiet || git commit -m "precios $(date +'%d/%m/%Y %H:%M')"
          git push
