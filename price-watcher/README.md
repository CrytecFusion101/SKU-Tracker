# Price Watcher

Tracks prices for Amazon India and Flipkart product URLs and sends a
Telegram notification whenever the price changes, stock status changes, or
a product hits its target price.

## How it works

Every product flows through the same pipeline, one stage at a time:

```
Load products
      │
      ▼
Marketplace Resolver   (scrapers/__init__.py: get_scraper_for_url)
      │
      ▼
Scraper                (scrapers/amazon.py, scrapers/flipkart.py)
      │
      ▼
Price Event            (events.py: build_price_event)
      │
      ▼
Notifier                (notifier.py: TelegramNotifier.handle)
      │
      ▼
State Store             (state_store.py)
```

1. `tracker.py` loads the list of products from `products.json`.
2. **Marketplace Resolver** — the product URL's hostname picks the matching
   scraper (`scrapers/__init__.py`).
3. **Scraper** — drives a headless Chromium instance via async Playwright to
   read the product title, price, and availability. Scrapes are retried up
   to 3 times with exponential backoff (2s, 4s, 8s) on failure.
4. **Price Event** — the scrape result is diffed against the last known
   value in `state.json` and turned into a `PriceEvent` (`events.py`):
   ```python
   PriceEvent(
       product="Sony XM6",
       marketplace="Amazon",
       old_price=29990,
       new_price=27999,
       changed=True,
       target_hit=True,
       ...
   )
   ```
   Every scrape produces a `PriceEvent`, whether or not anything changed —
   the event itself carries `changed`/`target_hit` flags rather than the
   tracker deciding upfront what's notification-worthy.
5. **Notifier** — receives the `PriceEvent` and decides for itself whether
   to alert (`event.changed or event.target_hit`). If so, it formats and
   sends a Telegram message.
6. **State Store** — `state_store.py` records the latest scrape result for
   next run, independent of whether the notifier fired.

## Project structure

```
scrapers/
    base.py       # BaseScraper interface + ScrapedProduct result type
    amazon.py     # Amazon-specific selectors and parsing
    flipkart.py   # Flipkart-specific selectors and parsing
    __init__.py   # Scraper registry + URL -> scraper auto-detection (resolver)
events.py         # PriceEvent + build_price_event (diffs a scrape into an event)
state_store.py    # StateStore: reads/writes state.json
notifier.py       # TelegramNotifier: decides to alert, formats, and sends
tracker.py        # Orchestration: wires the pipeline stages together per product
utils.py          # Generic async retry-with-backoff helper
products.json     # User-supplied list of products to track
state.json        # Last known price/availability per product (auto-managed)
```

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium --with-deps
   ```
3. Copy `.env.example` to `.env` and fill in your Telegram credentials:
   ```bash
   cp .env.example .env
   ```
   - `TELEGRAM_BOT_TOKEN`: create a bot via [@BotFather](https://t.me/BotFather)
     and copy the token it gives you.
   - `TELEGRAM_CHAT_ID`: the chat/user/group ID that should receive alerts.
     Message your bot once, then call
     `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID.
4. Add the products you want to track to `products.json`:
   ```json
   {
     "name": "Product name",
     "url": "https://www.amazon.in/dp/XXXXXXX",
     "target_price": 1999
   }
   ```
   `target_price` is optional — set it to `null` to only be notified of
   price/stock changes without a target alert.
5. Run the tracker:
   ```bash
   python tracker.py
   ```

Run it on a schedule (e.g. a Railway cron job, plain cron, or Task
Scheduler) to get ongoing alerts. `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`
should be set as environment variables/secrets on whatever platform runs it.

## Adding a new marketplace

1. Create `scrapers/<marketplace>.py` with a class that subclasses
   `BaseScraper` from `scrapers/base.py`.
2. Set `marketplace_name` and `domains` (hostname fragments used for
   auto-detection), and implement `_extract_title`, `_extract_price`, and
   `_extract_availability`. All selectors stay local to that file.
3. Register an instance of the new class in the `SCRAPERS` list in
   `scrapers/__init__.py`.

No other file needs to change — `tracker.py` picks up new marketplaces
automatically via `get_scraper_for_url`.

## Notes

- Selectors for Amazon/Flipkart may need occasional updates if either site
  changes its page markup — they are isolated to `scrapers/amazon.py` and
  `scrapers/flipkart.py` for easy maintenance.
- Products are scraped sequentially on a single browser page to keep
  request volume low and reduce the chance of bot detection.
- Scraping failures (timeouts, missing elements, network errors) are
  retried automatically; if all retries are exhausted, that product is
  skipped for the run and logged, without affecting the others.
