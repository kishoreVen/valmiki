
import dataclasses
import json
import logging
import types
from typing import Any, Dict, List, Type, TypeVar, Union, get_args, get_origin, get_type_hints
from datetime import datetime

import re
from json_repair import repair_json

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _strip_xml_wrapper(json_string: str) -> str:
    """
    Strip XML tags that wrap JSON content.

    LLMs sometimes wrap JSON output in XML tags that mirror the prompt format,
    e.g., <feedback_output_format>{"key": "value"}</feedback_output_format>

    Args:
        json_string: The string that may contain XML-wrapped JSON.

    Returns:
        The JSON string with outer XML tags removed.
    """
    # Pattern matches: <tag_name>...content...</tag_name>
    # where tag_name contains word characters and underscores
    xml_wrapper_pattern = re.compile(
        r"^\s*<(\w+)>\s*(.*?)\s*</\1>\s*$",
        re.DOTALL
    )

    match = xml_wrapper_pattern.match(json_string)
    if match:
        inner_content = match.group(2)
        # Recursively strip in case of nested XML wrappers
        return _strip_xml_wrapper(inner_content)

    return json_string


def safe_json_decode(json_string: str) -> Any:
    """
    Given an input string, try to decode json by cleaning up the string as necessary.

    Uses json-repair library for fixing common LLM output issues like unescaped quotes,
    trailing commas, control characters, etc.

    Args:
        json_string (str): Input string to decode into json

    Returns:
        json object: Decoded JSON.

    Raises:
        json.JSONDecodeError: If the clean up and decoding was unsuccessful
    """
    try:
        return json.loads(json_string)
    except json.decoder.JSONDecodeError:
        original_string = json_string

        # Strip XML wrapper tags (e.g., <feedback_output_format>...</feedback_output_format>)
        json_string = _strip_xml_wrapper(json_string)

        # Remove markdown code block markers
        if "```json" in json_string:
            json_string = json_string.replace("```json", "")
        if "json\n" in json_string:
            json_string = json_string.replace("json", "")
        if "```" in json_string:
            json_string = json_string.replace("```", "")

        json_string = json_string.strip()

        try:
            # Use json-repair for all the heavy lifting (trailing commas, unescaped
            # quotes, control chars, etc.)
            return json.loads(repair_json(json_string))
        except Exception as inner_e:
            # Save the problematic JSON to a temp file before raising
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            error_file = f"/tmp/json_decode_error_{timestamp}.json"
            with open(error_file, "w") as f:
                f.write(f"# Original string that failed to decode:\n")
                f.write(original_string)
                f.write(f"\n\n# After cleanup attempts:\n")
                f.write(json_string)
                f.write(f"\n\n# Error: {str(inner_e)}\n")
            print(f"Saved problematic JSON to: {error_file}")
            raise


def _decode_value(field_type: Type, value: Any) -> Any:
    """
    Recursively decode a value based on its expected type.

    Handles nested dataclasses and lists of dataclasses.

    Args:
        field_type: The expected type for the value.
        value: The value to decode.

    Returns:
        The decoded value, potentially converted to a dataclass instance.
    """
    if value is None:
        return None

    # Check if field_type is a dataclass
    if dataclasses.is_dataclass(field_type) and isinstance(value, dict):
        return safe_dataclass_decode(field_type, value)

    # Check if field_type is a generic type (e.g., List[Beat])
    origin = get_origin(field_type)
    if origin is list:
        args = get_args(field_type)
        if args and dataclasses.is_dataclass(args[0]):
            # It's a List[SomeDataclass]
            return [safe_dataclass_decode(args[0], item) for item in value]

    # Check for Union types (e.g., str | None or Union[str, None])
    # In Python 3.10+, `str | None` uses types.UnionType, while typing.Union uses typing.Union
    if origin is Union or isinstance(field_type, types.UnionType):
        args = get_args(field_type)
        # Try each type in the union
        for arg in args:
            if arg is type(None):
                continue
            if dataclasses.is_dataclass(arg) and isinstance(value, dict):
                return safe_dataclass_decode(arg, value)
            # Check for List[Dataclass] within Union
            arg_origin = get_origin(arg)
            if arg_origin is list:
                arg_args = get_args(arg)
                if arg_args and dataclasses.is_dataclass(arg_args[0]) and isinstance(value, list):
                    return [safe_dataclass_decode(arg_args[0], item) for item in value]

    return value


def safe_dataclass_decode(
    dataclass_type: Type[T], data: Union[str, Dict[str, Any]], **extra_fields
) -> T:
    """
    Safely decode a JSON string or dictionary into a dataclass instance.

    Filters out keys that don't exist in the dataclass and logs them as warnings.
    Recursively decodes nested dataclasses and lists of dataclasses.

    Args:
        dataclass_type: The dataclass type to instantiate.
        data: Either a JSON string or a dictionary to decode.
        **extra_fields: Additional fields to inject (e.g., fields not from LLM response).

    Returns:
        An instance of the dataclass populated with the valid fields.

    Raises:
        json.JSONDecodeError: If string input cannot be decoded as JSON.
        TypeError: If dataclass_type is not a dataclass.
    """
    if isinstance(data, str):
        data = safe_json_decode(data)

    fields = dataclass_type.__dataclass_fields__
    valid_keys = {f.name for f in fields.values()}
    filtered_data = {}
    filtered_out_keys = []

    # Use get_type_hints to resolve string annotations (from `from __future__ import annotations`)
    try:
        resolved_types = get_type_hints(dataclass_type)
    except Exception:
        # Fall back to raw field types if resolution fails
        resolved_types = {name: f.type for name, f in fields.items()}

    for key, value in data.items():
        if key in valid_keys:
            # Get the resolved field type and recursively decode if needed
            field_type = resolved_types.get(key, fields[key].type)
            filtered_data[key] = _decode_value(field_type, value)
        else:
            filtered_out_keys.append(key)

    if filtered_out_keys:
        logger.warning(
            f"Filtered out keys not in {dataclass_type.__name__}: {filtered_out_keys}"
        )

    # Merge in extra fields (e.g., fields injected by caller, not from LLM response)
    filtered_data.update(extra_fields)

    # Check for missing required fields and provide helpful error message
    required_fields = [
        name for name, f in fields.items()
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    ]
    missing_fields = [f for f in required_fields if f not in filtered_data]
    if missing_fields:
        raise TypeError(
            f"{dataclass_type.__name__} missing required fields: {missing_fields}. "
            f"Received keys: {list(data.keys())}"
        )

    return dataclass_type(**filtered_data)
