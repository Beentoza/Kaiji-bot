from database.db_functions import db_user, db_other
from helpers.logger_config import internal_logger as logger
import numpy as np
from database.models.Events import EventType

def get_data(data):
    user_data = np.array(data)
    market_info = (user_data[:, 2])[user_data[:, 0] == EventType.market]
    if len(market_info) > 0:
        market_average_multiplier = np.mean(market_info)
        market_percents = int((market_average_multiplier / 1.1) * 50) # getting percents
    else:
        market_percents = 50

    lottery_info = (user_data[:, 1])[user_data[:, 0] == EventType.lottery]
    if len(lottery_info) == 0:
        lottery_percents = 50
    else:
        lottery_prizes = [
            lottery_info == 19,
            lottery_info == 49,
            lottery_info == 124,
            lottery_info == 249,
            lottery_info == 499,
            lottery_info >= 500,
        ]
        lottery_points = [125, 250, 500, 1000, 2000, 5000]
        points_array = np.select(lottery_prizes, lottery_points, default=0) # getting points from winnings (f.e. changing 19 to 125 and e.t.c)
        lottery_total_points = np.sum(points_array)
        lottery_user_chances = lottery_total_points / len(lottery_info)
        lottery_percents = int((lottery_user_chances / 10.5) * 50)

    double_info = (user_data[:, 1])[user_data[:, 0] == EventType.double]
    if len(double_info) == 0:
        double_percents = 50
    else:
        double_percents = int(len(double_info[double_info > 0]) / len(double_info) * 100)

    return np.array((market_percents, lottery_percents, double_percents))

async def handle(interaction):
    """
    Send balance to user
    """
    try:
        await interaction.response.defer(thinking=True)
        user_data = await db_user.get_user_chances_data(interaction.user.id)
        if user_data is None:
            return await interaction.followup.send("I don't have idea who you are")
        user_percents = get_data(user_data)
        data = await db_other.get_chances_data()
        percents = get_data(data)
        user_plus = np.mean(user_percents) - np.mean(percents)
        if user_plus > 0:
            await interaction.followup.send(f"Your chances of winning decreased to {user_plus:.2f}%")
        if user_plus < 0:
            await interaction.followup.send(f"Your chances of winning increased to {abs(user_plus):.2f}%")
        if user_plus == 0:
            await interaction.followup.send("Your chances of winning didn't changed, wth")

    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred {e}")