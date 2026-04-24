
from typing import Dict, List


def format_list(items: List[str], separator: str = ", ") -> str:
    """
    Formats a list of strings into a single string with the specified separator.

    Args:
        items (List[str]): The list of strings to format.
        separator (str): The separator to use between items. Defaults to ", ".

    Returns:
        str: The formatted string.
    """
    if not items:
        return "[]"

    formatted_text = "["

    if len(items) == 1:
        formatted_text += items[0]
    else:
        formatted_text += separator.join(items)

    return formatted_text + "]"


def format_tuple_list(
    items: List[tuple[str, ...]],
    separator_tuple: str = ", ",
    separator_item: str = "\n",
) -> str:
    """
    Formats a list of tuples into a single string with the specified separator.

    Args:
        items (List[tuple[str, str]]): The list of tuples to format.
        separator_tuple (str): The separator to use between tuple items. Defaults to ", ".
        separator_item (str): The separator to use between items. Defaults to "\n".

    Returns:
        str: The formatted string.
    """
    if not items:
        return "[]"

    formatted_text = "[\n"

    if len(items) == 1:
        formatted_text += f"({items[0][0]}, {items[0][1]})"
    else:
        formatted_text += separator_item.join(
            [f"({separator_tuple.join(item)})" for item in items]
        )

    return formatted_text + "\n]"


def format_dict_to_tuple(
    items: Dict[str, Dict[str, str]],
    keys: List[str],
    separator_tuple: str = ", ",
    separator_item: str = "\n",
) -> str:
    """
    Formats a dictionary of dictionaries into a single string with the specified separator.
    Each inner dictionary is represented as a tuple with the specified keys.

    """
    if not items:
        return "[]"

    formatted_text = "[\n"

    tupled_items = [tuple(item[key] for key in keys) for item in items.values()]
    formatted_text += separator_item.join(
        [f"({separator_tuple.join(item)})" for item in tupled_items]
    )

    return formatted_text + "\n]"
