from helpers.logger_config import internal_logger as logger
from database.db_functions import db_user, db_bet
from helpers.user_functions import check_new_user


async def handle(interaction, bet: str, choice: str, amount: int):
    logger.debug(f"Place bet handle started work for user {interaction.user.id}, {bet}, {choice}, {amount}")
    await interaction.response.defer(thinking=True)
    await check_new_user.ensure_user_registered(interaction)

    status = await db_user.get_user_status(interaction.user.id)
    logger.debug(f"Checking if user {interaction.user.id} banned")
    if status == 0: # if user banned
        logger.debug(f"User {interaction.user.id} banned")
        return await interaction.followup.send("You're banned, mate")
    logger.debug(f"Checking if user {interaction.user.id} tried to use not valid amount")

    # checking if placed valid amount
    if amount < 1:
        logger.debug(f"User {interaction.user.id} tried to use not valid amount")
        return await interaction.followup.send("Please bet with a valid price")

    # getting balance
    logger.debug(f"Getting {interaction.user.id} balance")
    balance = await db_user.get_user_balance(interaction.user.id)
    logger.debug(f"Checking if {interaction.user.id} tried to place more money than he has")

    # checking if has enough balance to place this bet
    if amount > balance:
        logger.debug(f"User {interaction.user.id} tried to place more money than he has")
        return await interaction.followup.send("You can't bet with more than you have")

    try:
        logger.debug("All check are fine, starting placing bet in DB")
        # Calling function to add place into DB
        result = await db_bet.process_place_bet(interaction.user.id, bet, choice, amount, interaction.guild_id)
        logger.info(f"Place bet result for user {interaction.user.id}: {result}")
        # checking what it returned

        answers = {
            "success": f"{interaction.user.mention} Your bet on **{choice}** accepted. You placed {amount}",
            "bet_not_found": f"{interaction.user.mention} Didn't found bet with this name",
            "choice_not_found": f"{interaction.user.mention} Didn't found option with this name",
            "already_bet": f"{interaction.user.mention} You can't place more than once on same outcome\n"
                           f"You can use withdraw bet to change your option",
        }
        msg = answers.get(result, "Error happened")

        return await interaction.followup.send(msg)


    except Exception as e:
        logger.warning(f"Error occurred when tried to place bet for {interaction.user}: {e}")
        await interaction.followup.send("Error occurred", ephemeral=True)
        return None