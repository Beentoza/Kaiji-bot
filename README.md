# Kaiji - discord gambling bot

<img width="448" height="285" alt="image" src="https://github.com/user-attachments/assets/a2dff8fa-443d-41b9-a0b6-3c95cf1d128a" />

- Outcomes with any tittles and options, and choose time, for how long it will be open. And later on place bets on one of the options
- Try commands where you can get or lose Đ (meassure of money in a bot): market, double or nothing or lottery, where you have chance to win jackpot

There's also /help command where explained ALL existed commands for now. And it keep getting updated

Stack:

## Tech Stack

**Language & Runtime**
- Python 3.11
- asyncio

**Discord**
- discord.py (slash commands, app commands, context menus)

**Database**
- PostgreSQL 16
- SQLAlchemy 2.0 (async)
- asyncpg
- Alembic (migrations)


**Testing**
- pytest
- pytest-asyncio

**DevOps**
- GitHub Actions (CI/CD)
- Docker / docker-compose

**Utilities**
- matplotlib (for graphic in profile)
- numpy

Arhitecture:

- **main.py** - launching all needed files: Database, timed_task and synced commands.
- **controllers** - handlers for discord commands
- **database** - factory.py, which creating DB. db_XX.py files, which have functions for operating with DB. and also there's **models** directory.
- **helpers** - functions, which making a different tasks for code: logger, timed_tasks, auto_options for commands and e.t.c
- **tests** - directory, where exist all functions to test the real ones. Launching with every commit in pre-release
- **alembic** - directory, for alembic (sync DB in code with the real one)
- **.github/workflows** - have .yml files which launching on pre-release to launch VPS server
- **requirements.txt** - all needed libraries
**parameters.json** - description of all commands
