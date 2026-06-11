import time
from database.db_functions import db_user, db_outcome_logic
from helpers.logger_config import internal_logger as logger
import discord
from helpers.user_functions import check_new_user
import constants


async def handle(interaction, embed, outcome_name, choice):
    """Command to end outcomes"""
    logger.debug(f"Started work for {interaction.user.id}: {outcome_name}")
    await interaction.response.defer(thinking=True)

    if not await check_new_user.is_user_registered(interaction.user.id):
        # if we didn't find ID in DB, we don't adding
        # him. Instead, just saying he can't use this command
        return await interaction.followup.send("Only authorized users can end outcomes")
    status_level = await db_user.get_user_status(interaction.user.id)
    if status_level < constants.STATUS_REQUIRED_OUTCOME_COMMANDS: # if user status under authorizerd
        return await interaction.followup.send("Only authorized users can end outcomes")

    try:
        outcome_data, coefficient, status, channel_id, message_id = await db_outcome_logic.get_results_and_apply_payouts(
            bet_theme=outcome_name,
            current_time=time.time(),
            server_id=interaction.guild_id,
            win_choice=choice) # removing bet in DB,


        answers = {
                    'bet_not_found': "This outcome doesn't exist",
                    'open_bet': "This outcome still open",
                    'not_option': "Can't find outcome with this options",
                    'no_participants': "No participants found",
                    "no_winners_or_losers": "Bet ended with no winners or no losers. Refunded.",
                    "error": "Error"
                }
        msg = answers.get(status, "Error")
        failed_statuses = ['bet_not_found', 'not_option', "error"]

        if status in failed_statuses:
            return await interaction.followup.send(f"{interaction.user.mention} outcome wasn't ended due to {msg}")




        channel = interaction.client.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        if not message.embeds:
            return await interaction.followup.send("Error. Can't find outcome message")
        logger.debug(f"changing existent embed {outcome_name}")
        started_embed = message.embeds[0]
        if started_embed.color.value != constants.OUTCOME_OPEN_BET_COLOR:
            started_embed.remove_field(len(started_embed.fields) - 1)



        started_embed.color = discord.Color.dark_gray()
        started_embed.add_field(name='Status', value=f':no_entry_sign:  Bet closed due {msg}')
        await message.edit(embed=started_embed)
        if status != 'success': # if no participants or no loosers and winers then we don't need to make a loosers and winners list
            return await interaction.followup.send(f'Bet **{outcome_name}** ended!')


        embed_red = embed(title='Losers', color=0xff0000)
        embed_green = embed(title='Winners', color=0x00ff00)

        losers_list = []
        winners_list = []

        for bet_choice, users in outcome_data.items():
            for user_id, amount in users.items():
                amount = int(amount)
                if bet_choice == choice:
                    winners_list.append((user_id, amount))
                else:
                    losers_list.append((user_id, amount))

        pings = []
        # build the losers embed
        for uid, amount in losers_list:
            logger.debug(f"{uid} lost {amount} in {outcome_name}")
            pings.append(f'<@{uid}>')
            member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            name = member.display_name if member else f"User {uid}"
            embed_red.add_field(name=name, value=f'-{amount}', inline=False)

        # build the winners embed
        for uid, amount in winners_list:
            logger.debug(f"{uid} won {amount} in {outcome_name}")
            pings.append(f'<@{uid}>')
            member = interaction.guild.get_member(uid) or await interaction.guild.fetch_member(uid)
            name = member.display_name if member else f"User {uid}"
            profit = int(amount * coefficient)
            embed_green.add_field(name=name, value=f'{amount} + {profit}', inline=False)



        logger.info(f"Bet {outcome_name} closed by {interaction.user.display_name}")
        await interaction.followup.send(f'Bet **{outcome_name}** ended! Winner: **{choice}**')
        await interaction.followup.send(embed=embed_red)
        await interaction.followup.send(embed=embed_green)

        if channel_id is not None and message_id is not None:
            started_embed.color = discord.Color.dark_gray()
            started_embed.add_field(name='Status', value=f'⏲️ The outcome has already been played')
            await message.edit(embed=started_embed)

        ping_str = ", ".join(pings)
        if len(ping_str) > 1900:
            await interaction.followup.send("Can't ping everyone to show end of bet.")
        else:
            await interaction.followup.send(ping_str)


        logger.info(f"Bet closing handle finished successfully for {interaction.user.id}: {outcome_name}")

    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error occurred when tried to close bet {outcome_name}: {e}")