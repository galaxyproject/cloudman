from cm.framework.messages import constants


def get_level_tags():
    """
    Returns the message level tags.
    """
    level_tags = constants.DEFAULT_TAGS.copy()
    return level_tags