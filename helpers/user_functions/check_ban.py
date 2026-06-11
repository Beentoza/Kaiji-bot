import constants


def is_banned(status: int) -> bool:
    """True if the user's status marks them as banned."""
    return status == constants.STATUS_BANNED_USER
