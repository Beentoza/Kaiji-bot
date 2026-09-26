import time
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.BetTypes import BetEndType, BetEndResult
from helpers.outcome_rules import validate_outcome, calculate_payouts
from controllers.outcomes.bet_message import fetch_bet_message, set_bet_status
import constants


def _format_refusal(result, mention) -> str | None:
    """Message for a bet that was NOT ended, or None if it was."""
    match result.outcome:
        case BetEndType.NO_RIGHTS:
            return "Only authorized users can end outcomes"
        case BetEndType.BET_NOT_FOUND:
            return f"{mention} outcome wasn't ended due to This outcome doesn't exist"
        case BetEndType.OPEN_BET:
            return f"{mention} outcome wasn't ended due to This outcome still open"
        case BetEndType.NOT_OPTION:
            return f"{mention} outcome wasn't ended due to Can't find outcome with this options"
    return None


def _closed_reason(result) -> str:
    match result.outcome:
        case BetEndType.NO_PARTICIPANTS:
            return "No participants found"
        case BetEndType.NO_WINNERS_OR_LOSERS:
            return "Bet ended with no winners or no losers. Refunded."
    return "Error"


def _split_payouts(payouts: dict, choice) -> tuple[list, list]:
    """(winners, losers) as lists of (discord_id, amount)."""
    winners, losers = [], []
    for bet_choice, users in payouts.items():
        for user_id, amount in users.items():
            if bet_choice == choice:
                winners.append((user_id, int(amount)))
            else:
                losers.append((user_id, int(amount)))
    return winners, losers


async def _display_name(guild, uid) -> str:
    member = guild.get_member(uid) or await guild.fetch_member(uid)
    return member.display_name if member else f"User {uid}"


async def _build_result_embeds(guild, embed, result, choice, outcome_name):
    """Losers embed, winners embed and the ping list for a paid-out bet."""
    winners, losers = _split_payouts(result.payouts, choice)
    embed_red = embed(title='Losers', color=0xff0000)
    embed_green = embed(title='Winners', color=0x00ff00)
    pings = []

    for uid, amount in losers:
        logger.debug(f"{uid} lost {amount} in {outcome_name}")
        pings.append(f'<@{uid}>')
        embed_red.add_field(name=await _display_name(guild, uid), value=f'-{amount}', inline=False)

    for uid, amount in winners:
        logger.debug(f"{uid} won {amount} in {outcome_name}")
        pings.append(f'<@{uid}>')
        profit = int(amount * result.koef)
        embed_green.add_field(name=await _display_name(guild, uid), value=f'{amount} + {profit}', inline=False)

    return embed_red, embed_green, pings


async def logic(user_id, outcome_name, server_id, win_option, time_now, unit_of_work) -> BetEndResult:
    """Close a bet with a winning option and pay the winners out."""
    async with unit_of_work as uow:
        status_level = await uow.user.get_user_status(user_id)
        if status_level is None or status_level < constants.STATUS_REQUIRED_OUTCOME_COMMANDS:
            return BetEndResult(outcome=BetEndType.NO_RIGHTS)

        outcome_info = await uow.settlement.find_outcome(outcome_name, server_id)
        outcome_info, status = validate_outcome(outcome_info, time_now, win_option)
        if not outcome_info:
            return BetEndResult(outcome=status)

        rows = await uow.settlement.get_participation_data(outcome_info["id"])
        if not rows:
            logger.info(f"Didn't find participants for outcome {outcome_name}, deleting it")
            await uow.settlement.delete_outcome(outcome_info["id"])
            await uow.commit()
            return BetEndResult(
                outcome=BetEndType.NO_PARTICIPANTS,
                channel_id=outcome_info["channel_id"],
                message_id=outcome_info["message_id"],
            )

        calc = calculate_payouts(rows, outcome_info["opts"], win_option)

        if calc["action"] == "refund":
            logger.info(f"No winners or loosers for outcome {outcome_name}")
            await uow.settlement.execute_refund_step(outcome_info["id"], rows, 'refunded')
            await uow.commit()
            return BetEndResult(
                outcome=BetEndType.NO_WINNERS_OR_LOSERS,
                channel_id=outcome_info["channel_id"],
                message_id=outcome_info["message_id"],
            )

        # calculate_payouts only ever returns "refund" or "payout"
        logger.debug("execute payout step")
        await uow.settlement.execute_payout_step(outcome_info["id"], rows, outcome_info["win_index"])
        await uow.commit()

    logger.info(f"Successfully ended outcome {outcome_name}")
    return BetEndResult(
        outcome=BetEndType.SUCCESS,
        payouts=calc["outcome"],
        koef=calc["koef"],
        channel_id=outcome_info["channel_id"],
        message_id=outcome_info["message_id"],
    )


async def handle(interaction, embed, outcome_name, choice):
    """Command to end outcomes"""
    logger.debug(f"Started work for {interaction.user.id}: {outcome_name}")
    await interaction.response.defer(thinking=True)
    try:
        result = await logic(user_id=interaction.user.id, outcome_name=outcome_name, server_id=interaction.guild_id,
                             win_option=choice, time_now=time.time(), unit_of_work=UnitOfWork())

        refusal = _format_refusal(result, interaction.user.mention)
        if refusal is not None:
            return await interaction.followup.send(refusal)

        message = await fetch_bet_message(interaction.client, result.channel_id, result.message_id)
        if message is None or not message.embeds:
            return await interaction.followup.send("Error. Can't find outcome message")

        if result.outcome is not BetEndType.SUCCESS:  # no participants, or no winners/losers - refunded
            await set_bet_status(message, f':no_entry_sign:  Bet closed due {_closed_reason(result)}')
            return await interaction.followup.send(f'Bet **{outcome_name}** ended!')

        embed_red, embed_green, pings = await _build_result_embeds(interaction.guild, embed, result, choice, outcome_name)

        logger.info(f"Bet {outcome_name} closed by {interaction.user.display_name}")
        await interaction.followup.send(f'Bet **{outcome_name}** ended! Winner: **{choice}**')
        await interaction.followup.send(embed=embed_red)
        await interaction.followup.send(embed=embed_green)
        await set_bet_status(message, '⏲️ The outcome has already been played')

        ping_str = ", ".join(pings)
        if len(ping_str) > 1900:
            await interaction.followup.send("Can't ping everyone to show end of bet.")
        else:
            await interaction.followup.send(ping_str)

        logger.info(f"Bet closing handle finished successfully for {interaction.user.id}: {outcome_name}")

    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.exception(f"Error occurred when tried to close bet {outcome_name}: {e}")
