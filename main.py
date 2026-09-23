name: JAN Product Image Search

on:
  workflow_dispatch:

jobs:
  search:
    runs-on: ubuntu-latest
    timeout-minutes: 350

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install packages
        run: |
          pip install ddg-rs
          pip install google-api-python-client
          pip install google-auth
          pip install google-auth-oauthlib
          pip install pillow

      - name: Run
        env:
          GOOGLE_CLIENT_ID: ${{ secrets.GOOGLE_CLIENT_ID }}
          GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}
          GOOGLE_REFRESH_TOKEN: ${{ secrets.GOOGLE_REFRESH_TOKEN }}
          SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
          DRIVE_FOLDER_ID: ${{ secrets.DRIVE_FOLDER_ID }}
        run: python main.py
