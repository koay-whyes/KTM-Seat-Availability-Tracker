# KTM-Seat-Availability-Tracker

## Environment Variables

Create a local `.env` file with:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_DEFAULT_CHAT_ID=your_chat_id
DATABASE_URL=your_postgres_connection_string
```

On Heroku, set the same values in Config Vars. `DATABASE_URL` will be provided automatically if Heroku Postgres is attached.