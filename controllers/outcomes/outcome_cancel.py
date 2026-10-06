from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.BetTypes import BetEndType, BetEndResult
from controllers.outcomes.bet_message import fetch_bet_message, set_bet_status
import constants


def _format_cancel_message(result, mention, outcome_name):
    """From result making a message"""
    match result.outcome:
        case BetEndType.NO_RIGHTS:
            return "Only authorized users can make bets"
        case BetEndType.BET_NOT_FOUND:
            return f"{mention} outcome with this name doesn't exist"
        case BetEndType.CANCELLED | BetEndType.NO_PARTICIPANTS:
            return f"{mention} cancelled outcome {outcome_name}"
    return f"{mention} unknown error happened"


async def logic(user_id, outcome_name, server_id, unit_of_work) -> BetEndResult:
    """Give every participant their bet back and remove the Outcome."""
    async with unit_of_work as uow:
        status_level = await uow.user.get_user_status(user_id)
        if status_level is None or status_level < constants.STATUS_REQUIRED_OUTCOME_COMMANDS:
            return BetEndResult(outcome=BetEndType.NO_RIGHTS)

        outcome_info = await uow.settlement.find_outcome(outcome_name, server_id)
        if not outcome_info:
            return BetEndResult(outcome=BetEndType.BET_NOT_FOUND)

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

        logger.info(f"Starting to refund {outcome_name}")
        await uow.settlement.execute_refund_step(outcome_info["id"], rows, 'cancelled')
        await uow.commit()

    return BetEndResult(
        outcome=BetEndType.CANCELLED,
        channel_id=outcome_info["channel_id"],
        message_id=outcome_info["message_id"],
    )


async def handle(interaction, outcome):
    logger.debug(f"Bet cancel handle started work for {interaction.user.id}: {outcome}")
    await interaction.response.defer(thinking=True)
    try:
        result = await logic(user_id=interaction.user.id, outcome_name=outcome, server_id=interaction.guild_id,
                             unit_of_work=UnitOfWork())
        logger.info(f"Outcome **{outcome}** cancel by {interaction.user.id}, status {result.outcome}")

        if result.outcome in (BetEndType.CANCELLED, BetEndType.NO_PARTICIPANTS):
            message = await fetch_bet_message(interaction.client, result.channel_id, result.message_id)
            if message is not None:
                await set_bet_status(message, f':no_entry_sign:  Bet was cancelled by {interaction.user.mention}')

        await interaction.followup.send(_format_cancel_message(result, interaction.user.mention, outcome))
    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.exception(f"Error occurred when tried to cancel outcome {outcome}: {e}")
