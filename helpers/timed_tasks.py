from datetime import datetime
import datetime as dt
import asyncio
import numpy as np

import constants
from database.models.Events import EventType
from discord.ext import tasks
import discord
from database.db_functions import db_effects, db_other, db_outcome_logic, db_items, db, db_logs
from helpers.logger_config import internal_logger as logger


_bot_ref = None
balance_log_buffer = []

def set_bot_reference(bot_instance):
    global _bot_ref
    _bot_ref = bot_instance

target_time = dt.time(hour=19, minute=50, tzinfo=dt.timezone.utc)
@tasks.loop(time=target_time)
async def add_chances_data_into_DB():
    """Function which getting chances of all players into DB"""
    logger.info("Adding chances data to DB")
    data = await db_other.get_chances_data() # getting info of market, lottery and double commands
    if not data:
        logger.info("No chances data to aggregate, skipping")
        return
    user_data = np.array(data)

    market_info = (user_data[:, 2])[user_data[:, 0] == EventType.market]
    market_average_multiplier = np.mean(market_info)

    lottery_info = (user_data[:, 1])[user_data[:, 0] == EventType.lottery]
    lottery_prizes = [
        lottery_info == constants.LOTTERY_FIFTH_PLACE,
        lottery_info == constants.LOTTERY_FOURTH_PLACE,
        lottery_info == constants.LOTTERY_THIRD_PLACE,
        lottery_info == constants.LOTTERY_SECOND_PLACE,
        lottery_info >= constants.LOTTERY_FIFTH_PLACE,
    ]
    lottery_points = [125, 250, 500, 1000, 2000]
    points_array = np.select(lottery_prizes, lottery_points, default=0) # for every win getting points, should also divide it to uses probably
    lottery_total_points = np.sum(points_array)

    double_info = (user_data[:, 1])[user_data[:, 0] == EventType.double]
    total_games = len(double_info)
    double_win_probability = (np.count_nonzero(double_info > 0) / total_games * 100) if total_games else 0
    await db.add_chances_data(double_win_probability, lottery_total_points, market_average_multiplier)


@tasks.loop(minutes=3.0)
async def check_open_bets_status():
    bets = await db_outcome_logic.check_open_bets(datetime.now().timestamp())

    if bets is None:
        logger.debug("There's no bets which should be closed")
        return



    for bet in bets:
        # per-bet guard: a deleted channel/message must not kill the whole loop
        try:
            channel_id = bet["channel_id"]
            channel = _bot_ref.get_channel(channel_id) or await _bot_ref.fetch_channel(channel_id)

            logger.debug(f"Changing bet {bet['theme']}")

            message = await channel.fetch_message(bet['message_id'])
            if message.embeds: # just a check, if message has embeds (f.e. if admins deleted it, for a joke)
                logger.info(f"Changing {message.id} for bet to expired")
                embed = message.embeds[0]
                embed.color = discord.Color.yellow()
                embed.remove_field(len(embed.fields) - 1)
                embed.add_field(name="Status", value=":yellow_circle:  Closed, checking if it's valid bet", inline=False)

                await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update open bet {bet.get('theme')}: {e}")
            continue


@tasks.loop(minutes=3.0)
async def check_bets_liquidity_task():
    result = await db_outcome_logic.process_in_progress_bets()
    if not result["refunded"] and not result["active"]:
        logger.debug("There's no bets, which should expire")
        return



    for info in result["refunded"]:
        # per-bet guard: one broken message must not skip the rest
        try:
            channel = _bot_ref.get_channel(info["channel_id"])

            message = await channel.fetch_message(info["message_id"])
            if message.embeds:
                logger.info(f"Changing {message.id} for bet to expired")
                embed = message.embeds[0]
                embed.color = discord.Color.dark_gray()
                embed.remove_field(len(embed.fields) - 1)
                embed.add_field(name="Status", value=":black_circle:  Expired: Not enough participants", inline=False)
                await message.edit(embed=embed)
            await channel.get_partial_message(info["message_id"]).reply("Outcome expired")
        except Exception as e:
            logger.error(f"Failed to update refunded bet {info.get('message_id')}: {e}")
            continue


    for bet in result["active"]:
        # per-bet guard: one broken message must not skip the rest
        try:
            channel = _bot_ref.get_channel(bet.channel_id)

            message = await channel.fetch_message(bet.message_id)
            if message.embeds:
                embed = message.embeds[0]
                embed.color = discord.Color.red()
                embed.remove_field(len(embed.fields) - 1)
                embed.add_field(name="Status", value="✅ Waiting for result", inline=False)
                await message.edit(embed=embed)
            await channel.get_partial_message(bet.message_id).reply(
                "Outcome closed due time, you can't place bet anymore")
        except Exception as e:
            logger.error(f"Failed to update active bet {bet.message_id}: {e}")
            continue



@check_open_bets_status.before_loop
@check_bets_liquidity_task.before_loop
async def before_tasks():
    if _bot_ref:
        await _bot_ref.wait_until_ready()


async def auto_flush_timer():
    """Once in 3 hours clearing balance history buffed and sending into DB"""
    global balance_log_buffer
    while True:
        await asyncio.sleep(60*60*3)


        if balance_log_buffer:
            try:
                await db_logs.add_balance_history_into_DB(balance_log_buffer)
                balance_log_buffer.clear()
            except Exception as e:
                logger.error(e)


async def add_balance_history(user_id: int, server_id: int, group: str, command: str, profit: int, cur_balance: int) -> None:
    """Adding balance history in list of dicts"""
    new_log = {
        "user_id": user_id,
        "server_id": server_id,
        "group": group,
        "command": command,
        "profit": profit,
        "cur_balance": cur_balance ,
        "timestamp": int(datetime.now().timestamp())
    }
    balance_log_buffer.append(new_log)
    if len(balance_log_buffer) > 50:
        await db_logs.add_balance_history_into_DB(balance_log_buffer)
        balance_log_buffer.clear()


async def adding_logs_into_DB_by_command():
    global balance_log_buffer
    await db_logs.add_balance_history_into_DB(balance_log_buffer)
    balance_log_buffer.clear()

@tasks.loop(minutes=1.0)
async def check_expired_effects_task():
    try:
        expired = await db_effects.check_effects_for_expired()

        if not expired:
            return

        logger.info(f"Processing {len(expired)} expired effects")

        for effect in expired:
            u_id = effect["user_id"]
            g_id = effect["guild_id"]
            name = effect["effect_name"]

            logger.debug(f"Effect {name} expired for user {u_id} in guild {g_id}")

            role_id = await db_items.get_item_role(name)

            if role_id is not None:
                guild = _bot_ref.get_guild(g_id)
                if not guild:
                    logger.warning(f"Guild {g_id} not found")
                    continue

                role = guild.get_role(role_id)
                member = guild.get_member(u_id)

                if member and role:
                    try:
                        await member.remove_roles(role)
                        logger.info(f"Removed {name} (role {role_id}) from {u_id}")
                    except discord.Forbidden:
                        logger.error(f"No permissions to remove role {role_id} in {g_id}")
                    except Exception as e:
                        logger.error(f"Error removing role: {e}")
                else:
                    logger.debug(f"Member or role not found for {name} removal")

            elif name == "frog":
                pass

    except Exception as e:
        logger.error(f"Error in check_expired_effects_task: {e}")