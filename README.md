# Kaiji — Discord gambling bot

<img width="448" height="285" alt="image" src="https://github.com/user-attachments/assets/a2dff8fa-443d-41b9-a0b6-3c95cf1d128a" />

A Discord bot with its own currency (Đ). Moderators open outcomes with any options,
players bet on them, the bot pays out by the odds. On top of that: daily rewards,
mini-games with a shared jackpot, items with effects and stats.

## Features

| Group | Commands | What it does |
|---|---|---|
| `/outcome` | `create`, `end`, `cancel` | authorized users open an outcome with options and a deadline, then pick the winner or cancel it (bets are refunded) |
| `/bet` | `place`, `withdraw` | bet Đ on an option; withdraw while the outcome is still open |
| `/check` | `daily`, `weekly`, `monthly`, `pickupchange` | periodic rewards with cooldowns |
| `/try` | `lottery`, `market`, `double_or_nothing` | mini-games; the lottery jackpot is shared by all players |
| `/item` | `flex`, `yeet`, `add`, `change` | use items on yourself or others; admins manage item types |
| `/stats` | `games`, `leaderboard`, `jackpot`, `data` | personal game stats, richest players, current jackpot |
| top level | `/balance`, `/profile`, `/outcomes`, `/casino`, `/help` | |

`/help` describes every command. Command names and descriptions live in `parameters.json`.

Background tasks (`helpers/timed_tasks.py`):
- every 3 min: outcomes past their deadline are closed for new bets;
- every 3 min: closed outcomes with money on fewer than two options are cancelled and refunded;
- every minute: expired item effects are removed.

## Tech stack

- Python 3.11, asyncio
- discord.py (slash commands, groups, context menus)
- PostgreSQL 16, SQLAlchemy 2.0 (async) + asyncpg, Alembic
- pytest, pytest-asyncio, pre-commit
- Docker, docker-compose, GitHub Actions
- loguru (console, rotating file, Loki)

## Architecture

```
cogs/          Discord command registration only
controllers/   one file per command
database/
  models/      SQLAlchemy models
  db_functions/ repositories (queries grouped by domain)
  uow.py       Unit of Work: one session per command, repositories attached to it
  factory.py   engine and session factory
alembic/       migrations
helpers/       background tasks, logging, autocomplete, shared types
tests/
  unit/        controller logic with a fake Unit of Work, no database
  integration/ repositories and controllers against a real PostgreSQL
```

**Discord is kept out of the money logic.** Commands that move money (`/bet`,
`/outcome end` and `cancel`, `/check`, `/try`) are split in two: `logic()` gets plain ids
and a Unit of Work and returns a frozen dataclass, `handle()` turns it into a message.
Logic is tested without Discord, and network calls happen after the transaction is closed.

**Unit of Work.** A command opens one `UnitOfWork`, does all its reads and writes in that
session and commits explicitly with `uow.commit()`. Leaving the block without a commit
rolls everything back.

**Money and concurrency.**
- Balances change with atomic `UPDATE ... SET balance = balance + :amount`, never
  read-modify-write in Python.
- Reward cooldowns are claimed with a conditional `UPDATE ... WHERE` and checked by
  `rowcount`, so two parallel `/check daily` calls can't both pay.
- Rows that a decision depends on are locked with `SELECT ... FOR UPDATE` (an outcome
  being settled, a user's timestamps and balance, the jackpot). The lock order across
  tables is documented in `database/uow.py`.
- `CHECK (balance >= 0)` in the database as the last line of defence.

## Running locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
```

`.env` in the project root:

```
TOKEN=<discord bot token>
GUILD_ID=<guild id>[,<guild id>...]
DATABASE_URI=postgresql+asyncpg://<user>:<password>@<host>:<port>/<db>
TEST_DATABASE_URI=postgresql+asyncpg://lucky:tucky@localhost:8080/kaiji_tests
```

```bash
python main.py
```

`main.py` applies migrations (`alembic upgrade head`) and then starts the bot.

## Tests

```bash
docker compose up -d db           # test PostgreSQL on localhost:8080
python -m pytest tests/unit
python -m pytest tests/integration
```

- Integration tests refuse to run against any database not named `kaiji_tests`.
- Each test runs inside a SAVEPOINT on one shared connection and is rolled back, so tests
  don't see each other's data and the schema is built once. The schema is rebuilt
  automatically when the models change; `RESET_TEST_SCHEMA=1` forces a rebuild.

Git hooks run the tests automatically: unit tests on every commit, integration tests on
every push. Install once after cloning:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## CI/CD

`.github/workflows/deploy.yml`, on every push to `develop` and `pre-release`:

1. **tests** — starts a throwaway PostgreSQL 16 service container, installs dependencies
   (pip cache keyed on `requirements*.txt`), runs unit and then integration tests.
2. **deploy** — only for `pre-release` and only if tests passed: connects to the VPS over
   SSH and runs the deploy script there. The bot runs in Docker (`Dockerfile`).
