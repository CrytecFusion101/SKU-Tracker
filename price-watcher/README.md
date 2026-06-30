# Price Watcher

A simple price tracking utility that scrapes product pages from Amazon and Flipkart and stores the latest prices in `state.json`.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Add product URLs to `products.json`.
4. Run the tracker:
   ```bash
   python tracker.py
   ```

## Environment Variables

- `DISCORD_WEBHOOK_URL`: Optional webhook URL for sending notifications.
