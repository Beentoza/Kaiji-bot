import sys
from loguru import logger
from loki_logger_handler.loki_logger_handler import LokiLoggerHandler

LOG_LEVEL = "INFO"


def setup_logging():
    logger.remove()

    # making a log into console
    logger.add(
        sink=sys.stderr,
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan> | <cyan>{function}</cyan>  | <level>{message}</level>",
        colorize=True
    )

    # saving log into file
    logger.add(
        sink="combined.log",
        level=LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan> | <cyan>{function}</cyan>  | <level>{message}</level>",
        rotation="10 MB",
        compression="zip",
        colorize=True
    )

    # sending logs to Loki
    loki_handler = LokiLoggerHandler(
        url="http://localhost:3100/loki/api/v1/push",
        labels={"app": "kaiji-bot"},
    )
    logger.add(
        sink=loki_handler,
        level=LOG_LEVEL,
    )

    return logger


internal_logger = setup_logging()