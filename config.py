import os
import json

import discord
from dotenv import load_dotenv
from alembic.config import Config
from alembic import command

load_dotenv()

TOKEN = os.getenv("TOKEN")

GUILD_IDS = [int(x) for x in os.getenv("GUILD_ID", "").split(",")]
GUILDS = [discord.Object(id=gid) for gid in GUILD_IDS]

with open('parameters.json', 'r') as file:
    data_dict = json.load(file)


def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
