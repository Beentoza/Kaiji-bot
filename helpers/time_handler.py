from datetime import datetime as dt

# different time intervals in seconds
DAY = 86400
WEEK = 604800
MONTH = 2592000
MARKET_TIMER = 3600

def get_timestamp():
	return int(dt.now().timestamp())
