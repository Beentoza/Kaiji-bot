import os
import json


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARAMS_FILE = os.path.join(BASE_DIR, "..", "parameters.json")
with open(PARAMS_FILE, "r", encoding="utf-8") as file:
    test_dict = json.load(file)


def get_list_of_groups() -> list:
    """
    Get list of command groups
    """
    groups = list(test_dict.keys())
    return groups


def get_list_of_commands(remove_help: bool = True) -> list:
    """
    Get list of commands
    """
    lst = []
    for group in test_dict.keys():
        for command in test_dict[group].keys():
            lst.append(command)

    if remove_help:
        lst = [i for i in lst if i != "help"]
    return lst


def get_dict_with_groups_and_commands(remove_help: bool = True) -> dict:
    """
    Get list of commands in groups
    """
    dct = {}
    for group, commands in test_dict.items():
        group_commands = []
        for cmd_name in commands.keys():
            if not remove_help or cmd_name != "help":
                group_commands.append(cmd_name)
        dct[group] = group_commands
    return dct


def get_all_commands_with_groups(remove_help: bool = True) -> list:
    """
    Get list of "group command"
    """
    commands = []
    for group, group_commands in test_dict.items():
        for cmd_name in group_commands.keys():
            if not remove_help or cmd_name != "help":
                commands.append(f"{group} {cmd_name}")
    return commands


def get_command_info(group: str, command: str) -> dict | None:
    """
    Get all info about command
    """
    if group in test_dict and command in test_dict[group]:
        return test_dict[group][command]
    return None

def get_command_metadata(group: str, command: str) -> dict | None:
    """"
    Get name and description of command
    """
    info = get_command_info(group, command)
    if info and 'metadata' in info:
        return info['metadata']
    return None


def get_command_description(group: str, command: str) -> dict:
    """
    Get description of command (options, a.k. parameters)
    """
    info = get_command_info(group, command)
    if info and 'description' in info:
        return info['description']


def get_commands_by_group(prefix: str, remove_help: bool = True, remove_prefix: bool = False) -> list:
    """Get commands by group filter"""
    all_commands = get_all_commands_with_groups(remove_help)
    filtered = [cmd for cmd in all_commands if cmd.startswith(prefix)]

    if remove_prefix:
        filtered = [cmd[len(prefix):].strip() for cmd in filtered]

    return filtered