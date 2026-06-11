STATUS_ROLE_NAMES = {
    0: "Banned",
    1: "User",
    2: "Authorized",
    3: "Admin",
}


def give_role_name(status_id: int) -> str:
    return STATUS_ROLE_NAMES.get(status_id, "Unknown")
