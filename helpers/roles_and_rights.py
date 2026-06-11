from helpers.logger_config import  internal_logger as logger

ROLES = {'Degen gambler': ['set'], 'Avid gambler': ['outcome']}


def roles_for_certain_roles(groups, roles, user_id):
    for i in ROLES.keys():
        for j in ROLES[i]:
            if j in groups:
                groups.remove(j)
    for role in roles:
        if role.name in ROLES:
            for i in ROLES[role.name]:
                logger.debug(f"Added {i} to {user_id} because of {role.name}")
                groups.append(i)
    return groups