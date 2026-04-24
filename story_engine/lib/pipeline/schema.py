
"""
Schema system for DAG transforms to ensure type safety and validation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Type, Callable, Union, get_type_hints
import inspect
import logging

logger = logging.getLogger(__name__)


@dataclass
class Schema:
    """Schema definition for transform inputs and outputs."""

    name: str
    type: Type
    description: str = ""
    optional: bool = False
    default: Any = None

    def validate_value(self, value: Any) -> bool:
        """Validate that a value conforms to this schema."""
        if value is None:
            return self.optional

        return isinstance(value, self.type)

    def convert_value(self, value: Any) -> Any:
        """Convert value to schema type if possible."""
        if value is None:
            if self.optional:
                return self.default
            else:
                raise ValueError(f"Required schema field '{self.name}' cannot be None")

        if isinstance(value, self.type):
            return value

        # Try basic type conversions
        try:
            if self.type in (int, float, str, bool):
                return self.type(value)
        except (ValueError, TypeError):
            pass

        raise TypeError(
            f"Cannot convert value {value} of type {type(value)} to {self.type} "
            f"for schema field '{self.name}'"
        )

    def __repr__(self) -> str:
        optional_str = " (optional)" if self.optional else ""
        default_str = f" = {self.default}" if self.default is not None else ""
        return f"{self.name}: {self.type.__name__}{optional_str}{default_str}"


@dataclass
class AdvancedSchema(Schema):
    """Extended schema with additional validation and conversion features."""

    validators: List[Callable[[Any], bool]] = field(default_factory=list)
    converters: Dict[Type, Callable[[Any], Any]] = field(default_factory=dict)
    shape: tuple | None = None  # For arrays/tensors
    range: tuple | None = None  # (min, max) for numeric types
    choices: List[Any] | None = None  # Enumerated valid values

    def validate_value(self, value: Any) -> bool:
        """Enhanced validation with custom validators."""
        # Basic type validation
        if not super().validate_value(value):
            return False

        if value is None:
            return True  # Already handled by parent

        # Range validation for numeric types
        if self.range is not None and hasattr(value, "__lt__"):
            min_val, max_val = self.range
            if value < min_val or value > max_val:
                return False

        # Choices validation
        if self.choices is not None and value not in self.choices:
            return False

        # Shape validation for arrays
        if self.shape is not None and hasattr(value, "shape"):
            # Allow None in shape for flexible dimensions
            expected_shape = self.shape
            actual_shape = value.shape

            if len(expected_shape) != len(actual_shape):
                return False

            for expected, actual in zip(expected_shape, actual_shape):
                if expected is not None and expected != actual:
                    return False

        # Custom validators
        for validator in self.validators:
            if not validator(value):
                return False

        return True

    def convert_value(self, value: Any) -> Any:
        """Enhanced conversion with custom converters."""
        if value is None:
            if self.optional:
                return self.default
            else:
                raise ValueError(f"Required schema field '{self.name}' cannot be None")

        # Try custom converters first
        for source_type, converter in self.converters.items():
            if isinstance(value, source_type):
                try:
                    converted = converter(value)
                    if self.validate_value(converted):
                        return converted
                except Exception as e:
                    logger.warning(f"Custom converter failed for {self.name}: {e}")

        # Fall back to basic conversion
        try:
            converted = super().convert_value(value)
            if self.validate_value(converted):
                return converted
            else:
                raise ValueError(
                    f"Converted value {converted} failed validation for {self.name}"
                )
        except TypeError:
            # If basic conversion fails, try more advanced conversions
            converted = self._try_advanced_conversion(value)
            if converted is not None and self.validate_value(converted):
                return converted

            raise TypeError(
                f"Cannot convert value {value} of type {type(value)} to {self.type} "
                f"for schema field '{self.name}'"
            )

    def _try_advanced_conversion(self, value: Any) -> Any:
        """Try advanced type conversions."""
        # PIL Image <-> numpy array conversions
        try:
            from PIL import Image
            import numpy as np

            if self.type == np.ndarray and isinstance(value, Image.Image):
                return np.array(value)
            elif self.type == Image.Image and isinstance(value, np.ndarray):
                return Image.fromarray(value)
        except ImportError:
            pass

        # PyTorch tensor conversions
        try:
            import torch
            import numpy as np

            if self.type == torch.Tensor:
                if isinstance(value, np.ndarray):
                    return torch.from_numpy(value)
                elif hasattr(value, "__array__"):
                    return torch.from_numpy(np.array(value))
            elif self.type == np.ndarray and isinstance(value, torch.Tensor):
                return value.cpu().numpy()
        except ImportError:
            pass

        return None


class SchemaValidationError(Exception):
    """Exception raised when schema validation fails."""

    pass


class SchemaCompatibilityError(Exception):
    """Exception raised when schemas are incompatible."""

    pass


def validate_schemas_compatible(output_schema: Schema, input_schema: Schema) -> bool:
    """Check if an output schema is compatible with an input schema."""
    # Exact type match
    if output_schema.type == input_schema.type:
        return True

    # Check if types are compatible (subclass relationship)
    if issubclass(output_schema.type, input_schema.type):
        return True

    # Check for known convertible types
    convertible_pairs = [
        (int, float),
        (list, tuple),
    ]

    for type1, type2 in convertible_pairs:
        if (output_schema.type, input_schema.type) in [(type1, type2), (type2, type1)]:
            return True

    # Check advanced schema converters
    if isinstance(input_schema, AdvancedSchema):
        return output_schema.type in input_schema.converters

    return False


def create_schema_from_type_hint(
    name: str, type_hint: Any, default: Any = None
) -> Schema:
    """Create a schema from a type hint."""
    # Handle Optional types
    origin = getattr(type_hint, "__origin__", None)
    if origin is Union:
        args = getattr(type_hint, "__args__", ())
        if len(args) == 2 and type(None) in args:
            # This is Optional[T]
            actual_type = next(arg for arg in args if arg is not type(None))
            return Schema(name=name, type=actual_type, optional=True, default=default)

    return Schema(name=name, type=type_hint, default=default)


def extract_schemas_from_signature(func: Callable) -> Dict[str, Schema]:
    """Extract input schemas from a function signature using type hints."""
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)
    schemas = {}

    for param_name, param in signature.parameters.items():
        if param_name == "self":
            continue

        type_hint = type_hints.get(param_name, Any)
        default = param.default if param.default != inspect.Parameter.empty else None

        schema = create_schema_from_type_hint(param_name, type_hint, default)
        schemas[param_name] = schema

    return schemas


def validate_schema_dict(
    schemas: Dict[str, Schema], values: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate and convert a dictionary of values against schemas."""
    result = {}

    # Check all required schemas have values
    for name, schema in schemas.items():
        if not schema.optional and name not in values:
            raise SchemaValidationError(f"Required input '{name}' not provided")

    # Validate and convert provided values
    for name, value in values.items():
        if name not in schemas:
            logger.warning(f"Unknown input '{name}' provided (no schema defined)")
            result[name] = value
            continue

        schema = schemas[name]
        try:
            result[name] = schema.convert_value(value)
        except (TypeError, ValueError) as e:
            raise SchemaValidationError(f"Schema validation failed for '{name}': {e}")

    # Add default values for missing optional inputs
    for name, schema in schemas.items():
        if schema.optional and name not in result:
            result[name] = schema.default

    return result


# Common schema definitions for convenience
class CommonSchemas:
    """Predefined common schemas."""

    IMAGE = Schema(
        name="image", type=object, description="PIL Image object"
    )  # Use object to avoid PIL import requirement
    NUMPY_ARRAY = Schema(name="array", type=object, description="NumPy array")
    TENSOR = Schema(name="tensor", type=object, description="PyTorch tensor")
    METADATA = Schema(name="metadata", type=dict, description="Metadata dictionary")
    SIZE = Schema(name="size", type=tuple, description="Size tuple (width, height)")
    PATH = Schema(name="path", type=str, description="File path")

    @staticmethod
    def image_with_converters() -> AdvancedSchema:
        """Image schema with automatic numpy/PIL conversions."""
        converters = {}
        try:
            from PIL import Image
            import numpy as np

            converters[np.ndarray] = lambda arr: Image.fromarray(arr)
        except ImportError:
            pass

        return AdvancedSchema(
            name="image",
            type=object,  # Will be set to PIL.Image if available
            description="Image with automatic format conversion",
            converters=converters,
        )

    @staticmethod
    def tensor_with_converters() -> AdvancedSchema:
        """Tensor schema with automatic conversions."""
        converters = {}
        try:
            import torch
            import numpy as np

            converters[np.ndarray] = lambda arr: torch.from_numpy(arr)
            converters[list] = lambda lst: torch.tensor(lst)
        except ImportError:
            pass

        return AdvancedSchema(
            name="tensor",
            type=object,  # Will be set to torch.Tensor if available
            description="Tensor with automatic format conversion",
            converters=converters,
        )
