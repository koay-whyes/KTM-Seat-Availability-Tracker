# KTM Seat Availability Tracker

Python-based KTM ETS seat tracker that scrapes the KTMB booking site, watches for seat availability changes, stores snapshots in PostgreSQL, and sends Telegram alerts when availability changes.

## What it does

- Starts from a Telegram conversation where you choose an origin, destination, and travel date.
- Uses Selenium and BeautifulSoup to scrape the train schedule, fare, and seat-count table from KTMB.
- Compares the latest scrape with the previous snapshot and sends Telegram notifications when seat counts change.
- Saves structured snapshots to Heroku Postgres for later trend analysis.
- Runs headlessly in Docker and is configured for Heroku deployment.

## Pipeline

This project follows an ETL-style flow:

1. Extract: scrape the KTMB booking page.
2. Transform: parse the HTML into structured train records and derive seat/fare fields.
3. Load: store the snapshot in PostgreSQL before generating alerts.

## Environment Variables

Create a local `.env` file with:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_DEFAULT_CHAT_ID=your_chat_id
DATABASE_URL=your_postgres_connection_string
```

On Heroku, set the same values in Config Vars. `DATABASE_URL` will be provided automatically if Heroku Postgres is attached.