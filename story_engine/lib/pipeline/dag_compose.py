
from abc import ABC, abstractmethod
from typing import final, Any, Dict, List, Callable, Set, Tuple, Union
from pathlib import Path
import hashlib
import json
import pickle
import logging
import shutil
from collections import defaultdict, deque

from story_engine.lib.pipeline.memoized_compose import MemoizableTransform
from story_engine.lib.pipeline.schema import (
    Schema,
    AdvancedSchema,
    SchemaValidationError,
    SchemaCompatibilityError,
    validate_schemas_compatible,
    validate_schema_dict,
)

logger = logging.getLogger(__name__)


class DAGTransform(MemoizableTransform):
    """Base class for transforms that can declare dependencies in a DAG structure with schema validation."""

    def __init__(self, name: str, dependencies: List[str] | None = None):
        """
        Initialize a DAG transform.

        Args:
            name: Unique identifier for this transform in the DAG
            dependencies: List of transform names whose outputs this transform needs.
                         If None or empty, uses the previous transform's output (linear behavior)
        """
        super().__init__()
        self.name = name
        self.dependencies = dependencies or []

        # Validate that inputs match schema if defined
        self._validate_inputs_against_schema()

    @abstractmethod
    def __call__(self, **kwargs: Any) -> Any:
        """
        Execute the transform.

        Args are passed as keyword arguments based on input schema names.
        For transforms with multiple inputs, kwargs will contain outputs from
        dependent transforms with keys matching the input schema names.
        """
        ...

    @classmethod
    def input_schema(cls) -> Dict[str, Schema]:
        """
        Define the input schema for this transform.

        Returns:
            Dictionary mapping input names to Schema objects
            Returns {} if no schema validation is needed (backward compatibility)
        """
        return {}

    @classmethod
    def output_schema(cls) -> Union[Schema, Dict[str, Schema]]:
        """
        Define the output schema for this transform.

        Returns:
            Single Schema for single output, or Dict mapping output names to Schemas for multiple outputs
            Returns None if no schema validation is needed (backward compatibility)
        """
        return None

    def _validate_inputs_against_schema(self) -> None:
        """Validate that declared inputs match the input schema."""
        input_schemas = self.input_schema()

        # If no schema is defined, skip validation (backward compatibility)
        if not input_schemas:
            return

        # If no dependencies are declared but we have schemas, this could be a root transform
        # that takes the initial pipeline input - this is valid
        if not self.dependencies and input_schemas:
            # Root transform - schemas will be matched against pipeline input
            return

        # Skip validation here - dependencies are transform names, schemas are parameter names
        # This will be validated at DAG construction time when we can check compatibility

        # Note: We can't validate schema completeness here because dependencies are transform names
        # and schemas are parameter names. This validation happens at DAG execution time.

    @final
    def get_cache_key(self, input_data: Any) -> str:
        """Generate a cache key based on transform parameters and input data."""
        # For DAG transforms with multiple inputs, handle them specially
        if isinstance(input_data, dict) and "_dag_inputs" in input_data:
            # Multiple inputs from DAG
            input_hashes = {}
            for input_name, input_value in input_data["_dag_inputs"].items():
                input_hashes[input_name] = self._hash_input(input_value)
            combined_data = {
                "transform_class": self.__class__.__name__,
                "transform_name": self.name,
                "input_hashes": input_hashes,
            }
        else:
            # Single input (backward compatible)
            combined_data = {
                "transform_class": self.__class__.__name__,
                "transform_name": self.name,
                "input_hash": self._hash_input(input_data),
            }

        serialized = json.dumps(combined_data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def validate_and_convert_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert inputs according to schema."""
        input_schemas = self.input_schema()
        return validate_schema_dict(input_schemas, inputs)

    def validate_output(self, output: Any) -> Any:
        """Validate output according to schema."""
        output_schema = self.output_schema()

        if isinstance(output_schema, dict):
            # Multiple outputs - output should be a dict
            if not isinstance(output, dict):
                raise SchemaValidationError(
                    f"Transform '{self.name}' output schema expects dict but got {type(output)}"
                )
            return validate_schema_dict(output_schema, output)
        else:
            # Single output
            try:
                return output_schema.convert_value(output)
            except (TypeError, ValueError) as e:
                raise SchemaValidationError(
                    f"Output validation failed for '{self.name}': {e}"
                )


class DAGCompose:
    """A Compose class that supports DAG execution with memoization."""

    def __init__(
        self,
        transforms: List[Union[Callable, DAGTransform]],
        cache_dir: str | Path | None = None,
        verbose_logging: bool = False,
        copy_from_cache_dir: str | Path | None = None,
        copy_from_start_stage: int | str | None = None,
    ):
        """
        Initialize DAGCompose.

        Args:
            transforms: List of transforms (DAGTransform or regular callables)
            cache_dir: Optional directory path for transform-specific storage and cache
            verbose_logging: Enable verbose logging for transform operations
            copy_from_cache_dir: Optional source cache directory to copy from on first run
            copy_from_start_stage: Optional stage to start copying from (int index or name)
        """
        self.transforms = transforms
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache = {}
        self.verbose_logging = verbose_logging
        self.copy_from_cache_dir = (
            Path(copy_from_cache_dir) if copy_from_cache_dir else None
        )
        self.copy_from_start_stage = copy_from_start_stage
        self._cache_copied = False

        # Build transform registry and dependency graph
        self._build_registry()
        self._validate_dag()
        self._compute_execution_order()

        # Set verbose_logging on all transforms that support it
        for transform in self.transforms:
            if isinstance(transform, MemoizableTransform):
                transform.verbose_logging = self.verbose_logging

    def _build_registry(self) -> None:
        """Build a registry of transforms by name."""
        self.transform_registry = {}
        self.transform_index = {}  # Maps transform to its index

        for i, transform in enumerate(self.transforms):
            # Assign default names if not DAGTransform
            if isinstance(transform, DAGTransform):
                name = transform.name
            else:
                # For backward compatibility with non-DAG transforms
                name = f"{i:02d}_{transform.__class__.__name__}"

            if name in self.transform_registry:
                raise ValueError(f"Duplicate transform name: {name}")

            self.transform_registry[name] = transform
            self.transform_index[transform] = i

            # Set name for non-DAG transforms for consistency
            if not isinstance(transform, DAGTransform) and hasattr(
                transform, "__dict__"
            ):
                transform.name = name

    def _validate_dag(self) -> None:
        """Validate that the DAG has no cycles and all dependencies exist, and schemas are compatible."""
        # Check that all dependencies exist
        for transform in self.transforms:
            if isinstance(transform, DAGTransform):
                for dep_name in transform.dependencies:
                    if dep_name not in self.transform_registry:
                        raise ValueError(
                            f"Transform '{transform.name}' depends on '{dep_name}' "
                            f"which doesn't exist in the pipeline"
                        )

        # Check for cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(name: str) -> bool:
            visited.add(name)
            rec_stack.add(name)

            transform = self.transform_registry[name]
            if isinstance(transform, DAGTransform):
                for dep_name in transform.dependencies:
                    if dep_name not in visited:
                        if has_cycle(dep_name):
                            return True
                    elif dep_name in rec_stack:
                        return True

            rec_stack.remove(name)
            return False

        for name in self.transform_registry:
            if name not in visited:
                if has_cycle(name):
                    raise ValueError(
                        f"Cycle detected in DAG involving transform '{name}'"
                    )

        # Validate schema compatibility
        self._validate_schema_compatibility()

    def _validate_schema_compatibility(self) -> None:
        """Validate that output schemas of dependencies match input schemas of dependents."""
        for transform in self.transforms:
            if not isinstance(transform, DAGTransform):
                continue

            input_schemas = transform.input_schema()

            # Skip schema validation if no input schemas defined
            if not input_schemas:
                continue

            for dep_name in transform.dependencies:
                dependency = self.transform_registry[dep_name]
                if not isinstance(dependency, DAGTransform):
                    logger.warning(
                        f"Cannot validate schema compatibility between non-DAGTransform '{dep_name}' "
                        f"and DAGTransform '{transform.name}'"
                    )
                    continue

                # Get output schema of dependency
                dep_output_schema = dependency.output_schema()

                # Skip if dependency has no output schema
                if dep_output_schema is None:
                    continue

                # For simple case (single dependency, single schema), check compatibility
                if len(transform.dependencies) == 1 and len(input_schemas) == 1:
                    input_schema = next(iter(input_schemas.values()))
                elif len(transform.dependencies) == len(input_schemas):
                    # Map dependencies in order (simplified)
                    dep_idx = transform.dependencies.index(dep_name)
                    input_schema = list(input_schemas.values())[dep_idx]
                else:
                    logger.warning(
                        f"Cannot validate schema compatibility for '{transform.name}': "
                        f"{len(transform.dependencies)} dependencies but {len(input_schemas)} schemas"
                    )
                    continue

                # Handle multiple outputs case
                if isinstance(dep_output_schema, dict):
                    # Dependency has multiple outputs - need to specify which one to use
                    # For now, this is an error - we could extend this later
                    raise SchemaCompatibilityError(
                        f"Transform '{dependency.name}' has multiple outputs but '{transform.name}' "
                        f"doesn't specify which output to use. Multiple outputs not yet supported."
                    )

                # Check compatibility
                if not validate_schemas_compatible(dep_output_schema, input_schema):
                    raise SchemaCompatibilityError(
                        f"Schema incompatibility: '{dependency.name}' outputs {dep_output_schema.type.__name__} "
                        f"but '{transform.name}' expects {input_schema.type.__name__} for dependency '{dep_name}'"
                    )

    def _compute_execution_order(self) -> None:
        """Compute topological ordering of transforms."""
        # Build adjacency list (reverse direction for topological sort)
        dependents = defaultdict(list)
        in_degree = defaultdict(int)

        for transform in self.transforms:
            if isinstance(transform, DAGTransform):
                name = transform.name
                if name not in in_degree:
                    in_degree[name] = 0

                for dep_name in transform.dependencies:
                    dependents[dep_name].append(name)
                    in_degree[name] += 1
            else:
                # Non-DAG transforms have implicit linear dependency
                name = (
                    transform.name
                    if hasattr(transform, "name")
                    else f"{self.transform_index[transform]:02d}_{transform.__class__.__name__}"
                )
                if name not in in_degree:
                    in_degree[name] = 0

        # Find nodes with no dependencies
        queue = deque(
            [name for name in self.transform_registry if in_degree[name] == 0]
        )
        self.execution_order = []

        while queue:
            name = queue.popleft()
            self.execution_order.append(name)

            # Reduce in-degree for dependent nodes
            for dependent in dependents[name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # For linear compatibility, ensure transforms without explicit dependencies
        # execute in their original order
        remaining = [
            name for name in self.transform_registry if name not in self.execution_order
        ]
        self.execution_order.extend(
            sorted(
                remaining,
                key=lambda n: self.transform_index[self.transform_registry[n]],
            )
        )

    def _get_transform_directory(
        self,
        transform_name: str,
        call_sub_dir: str | None = None,
    ) -> Path:
        """Get the directory path for a specific transform."""
        if self.cache_dir is None:
            raise ValueError(
                "Cache Dir shouldn't be none if calling _get_transform_directory"
            )

        transform = self.transform_registry[transform_name]
        index = self.transform_index[transform]
        dir_name = f"{index:02d}_{transform_name}"

        if call_sub_dir:
            return self.cache_dir / call_sub_dir / dir_name
        return self.cache_dir / dir_name

    def _ensure_transform_directory(
        self,
        transform_name: str,
        call_sub_dir: str | None = None,
    ) -> Path:
        """Ensure the transform directory exists and return its path."""
        transform_dir = self._get_transform_directory(transform_name, call_sub_dir)
        transform_dir.mkdir(parents=True, exist_ok=True)
        return transform_dir

    def _get_cache_file_path(self, call_sub_dir: str | None) -> Path:
        """Get the path to the cache file."""
        if self.cache_dir is None:
            raise ValueError(
                "Cache Dir shouldn't be none if calling _get_cache_file_path"
            )

        if call_sub_dir is None:
            return self.cache_dir / "cache.pkl"
        else:
            return self.cache_dir / call_sub_dir / "cache.pkl"

    def _get_registry_file_path(self, call_sub_dir: str | None) -> Path:
        """Get the path to the DAG registry file."""
        if self.cache_dir is None:
            raise ValueError(
                "Cache Dir shouldn't be none if calling _get_registry_file_path"
            )

        if call_sub_dir is None:
            return self.cache_dir / "dag_registry.pkl"
        else:
            return self.cache_dir / call_sub_dir / "dag_registry.pkl"

    def _load_cache(self, call_sub_dir: str | None) -> None:
        """Load cache from disk if it exists."""
        cache_file = self._get_cache_file_path(call_sub_dir)
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    self.cache = pickle.load(f)
            except (pickle.PickleError, IOError, EOFError):
                self.cache = {}

    def _save_cache(self, call_sub_dir: str | None) -> None:
        """Save cache to disk."""
        if self.cache_dir:
            cache_file = self._get_cache_file_path(call_sub_dir)
            with open(cache_file, "wb") as f:
                pickle.dump(self.cache, f, protocol=pickle.HIGHEST_PROTOCOL)

    def _load_registry(self, call_sub_dir: str | None) -> Dict[str, Any]:
        """Load output registry from disk if it exists."""
        registry_file = self._get_registry_file_path(call_sub_dir)
        if registry_file.exists():
            try:
                with open(registry_file, "rb") as f:
                    return pickle.load(f)
            except (pickle.PickleError, IOError, EOFError):
                return {}
        return {}

    def _save_registry(
        self, output_registry: Dict[str, Any], call_sub_dir: str | None
    ) -> None:
        """Save output registry to disk."""
        if self.cache_dir:
            registry_file = self._get_registry_file_path(call_sub_dir)
            with open(registry_file, "wb") as f:
                pickle.dump(output_registry, f, protocol=pickle.HIGHEST_PROTOCOL)

    def __call__(self, data: Any, sub_dir: str | None = None) -> Any:
        """Apply transforms according to DAG structure with memoization."""
        # Create main cache directory and load cache if specified
        if self.cache_dir:
            cache_dir = (
                self.cache_dir / sub_dir if sub_dir is not None else self.cache_dir
            )
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Lazy copy from source cache directory on first run
            if self.copy_from_cache_dir and not self._cache_copied:
                self._copy_cache_from(
                    self.copy_from_cache_dir, self.copy_from_start_stage, sub_dir
                )
                self._cache_copied = True

            self._load_cache(sub_dir)
            output_registry = self._load_registry(sub_dir)
        else:
            output_registry = {}

        # Initialize output registry with input data
        output_registry["_input"] = data

        # Execute transforms in topological order
        for transform_name in self.execution_order:
            transform = self.transform_registry[transform_name]

            if self.verbose_logging:
                logger.info(f"Executing transform: {transform_name}")

            # Prepare inputs for this transform
            if isinstance(transform, DAGTransform):
                if transform.dependencies:
                    # Gather inputs from specified dependencies
                    transform_inputs = {}
                    for dep_name in transform.dependencies:
                        if dep_name not in output_registry:
                            raise RuntimeError(
                                f"Transform '{transform_name}' requires dependency '{dep_name}' "
                                f"which hasn't been computed yet"
                            )
                        transform_inputs[dep_name] = output_registry[dep_name]

                    # Package inputs for cache key generation
                    input_data = {"_dag_inputs": transform_inputs}

                    # Map transform outputs to schema parameter names
                    input_schemas = transform.input_schema()

                    if input_schemas:
                        # Has schema - do validation and mapping
                        schema_inputs = {}

                        if len(transform.dependencies) == 1 and len(input_schemas) == 1:
                            # Simple case: one dependency to one parameter
                            param_name = next(iter(input_schemas.keys()))
                            dep_name_input = transform.dependencies[0]
                            schema_inputs[param_name] = transform_inputs[dep_name_input]
                        elif len(transform.dependencies) == len(input_schemas):
                            # Map dependencies in order (this is a simplification)
                            for i, (param_name, schema) in enumerate(
                                input_schemas.items()
                            ):
                                if i < len(transform.dependencies):
                                    dep_name_input = transform.dependencies[i]
                                    schema_inputs[param_name] = transform_inputs[
                                        dep_name_input
                                    ]
                        else:
                            raise RuntimeError(
                                f"Transform '{transform_name}' has {len(transform.dependencies)} dependencies "
                                f"but {len(input_schemas)} schema parameters. Cannot map automatically."
                            )

                        # Validate and convert inputs according to schema
                        validated_inputs = transform.validate_and_convert_inputs(
                            schema_inputs
                        )
                        transform_kwargs = validated_inputs
                    else:
                        # No schema - use old behavior with positional args
                        transform_args = [
                            transform_inputs[name] for name in transform.dependencies
                        ]
                        transform_kwargs = None
                else:
                    # DAGTransform with empty dependencies list uses initial input
                    input_data = data
                    # Get the schema name for the primary input (usually the first one)
                    input_schemas = transform.input_schema()
                    if input_schemas:
                        # Use the first schema name as the parameter name
                        primary_input_name = next(iter(input_schemas.keys()))
                        validated_inputs = transform.validate_and_convert_inputs(
                            {primary_input_name: data}
                        )
                        transform_kwargs = validated_inputs
                    else:
                        # No schema defined, use old behavior with positional args
                        transform_args = [data]
                        transform_kwargs = None
            else:
                # Non-DAG transforms use linear chaining for backward compatibility
                prev_transforms = self.execution_order[
                    : self.execution_order.index(transform_name)
                ]
                if prev_transforms:
                    input_data = output_registry[prev_transforms[-1]]
                else:
                    input_data = data
                transform_args = [input_data]
                transform_kwargs = None

            # Apply memoization if transform supports it
            if isinstance(transform, MemoizableTransform):
                # Reset cache flags
                transform._loaded_from_cache = False
                transform._loaded_from_cache_dir = False

                # Try to get from cache
                cache_key = transform.get_cache_key(input_data)

                if cache_key in self.cache:
                    result = self.cache[cache_key]
                    transform._loaded_from_cache = True
                    if self.verbose_logging:
                        logger.info(
                            f"  → Loaded from memory cache (key: {cache_key[:8]}...)"
                        )
                elif self.cache_dir:
                    transform_dir = self._get_transform_directory(
                        transform_name, sub_dir
                    )

                    if transform_dir.exists():
                        cached_result = transform.deserialize(str(transform_dir))
                        if cached_result is not None:
                            result = cached_result
                            transform._loaded_from_cache_dir = True
                            if self.verbose_logging:
                                logger.info(
                                    f"  → Loaded from directory cache: {transform_dir}"
                                )

                # If not in cache, apply transform
                if not transform.is_loaded_from_cache:
                    if self.verbose_logging:
                        logger.info(f"  → Applying transform (not in cache)")

                    # Execute transform with appropriate arguments
                    if isinstance(transform, DAGTransform):
                        if transform_kwargs is not None:
                            result = transform(**transform_kwargs)
                            # Validate output according to schema if available
                            output_schema = transform.output_schema()
                            if output_schema is not None:
                                result = transform.validate_output(result)
                        else:
                            result = transform(*transform_args)
                    else:
                        result = transform(*transform_args)

                    # Save to memory cache
                    self.cache[cache_key] = result
                    self._save_cache(sub_dir)
                    if self.verbose_logging:
                        logger.info(
                            f"  → Saved to memory cache (key: {cache_key[:8]}...)"
                        )

                    # Save to directory if available
                    if self.cache_dir:
                        transform_dir = self._ensure_transform_directory(
                            transform_name, sub_dir
                        )
                        transform.serialize(result, str(transform_dir))
                        if self.verbose_logging:
                            logger.info(
                                f"  → Saved to directory cache: {transform_dir}"
                            )
            else:
                # Non-memoizable transform
                if self.verbose_logging:
                    logger.info(f"  → Applying non-memoizable transform")

                # Execute transform with appropriate arguments
                if isinstance(transform, DAGTransform):
                    if transform_kwargs is not None:
                        result = transform(**transform_kwargs)
                        # Validate output according to schema if available
                        output_schema = transform.output_schema()
                        if output_schema is not None:
                            result = transform.validate_output(result)
                    else:
                        result = transform(*transform_args)
                else:
                    result = transform(*transform_args)

            # Store result in registry
            output_registry[transform_name] = result

        # Save registry to disk
        if self.cache_dir:
            self._save_registry(output_registry, sub_dir)

        # Return the full output registry
        return output_registry

    def _copy_cache_from(
        self,
        source_cache_dir: Union[str, Path],
        start_stage: int | str | None = None,
        sub_dir: str | None = None,
    ) -> None:
        """
        Copy cache from another pipeline directory up to a specified stage.

        Args:
            source_cache_dir: Directory containing the source cache to copy from
            start_stage: Transform name or index to start from
            sub_dir: Optional subdirectory for cache organization
        """
        source_path = Path(source_cache_dir)
        if not source_path.exists():
            raise ValueError(
                f"Source cache directory does not exist: {source_cache_dir}"
            )

        if not self.cache_dir:
            raise ValueError("Current pipeline has no cache directory specified")

        # Determine the actual source and destination directories
        source_dir = source_path / sub_dir if sub_dir else source_path
        dest_dir = self.cache_dir / sub_dir if sub_dir else self.cache_dir

        # Ensure destination directory exists
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Determine which transforms to copy
        if start_stage is None:
            # Copy all transforms
            transforms_to_copy = list(self.transform_registry.keys())
        elif isinstance(start_stage, str):
            # Copy transforms before the named stage
            if start_stage not in self.transform_registry:
                raise ValueError(f"Transform '{start_stage}' not found in pipeline")
            idx = self.execution_order.index(start_stage)
            transforms_to_copy = self.execution_order[:idx]
        else:
            # Copy transforms before the indexed stage
            transforms_to_copy = [
                name
                for name, transform in self.transform_registry.items()
                if self.transform_index[transform] < start_stage
            ]

        # Copy transform directories
        for transform_name in transforms_to_copy:
            src_transform_dir = self._get_transform_directory(transform_name, None)
            src_transform_dir = source_dir / src_transform_dir.name

            if src_transform_dir.exists():
                dest_transform_dir = dest_dir / src_transform_dir.name
                if dest_transform_dir.exists():
                    shutil.rmtree(dest_transform_dir)
                shutil.copytree(src_transform_dir, dest_transform_dir)
                if self.verbose_logging:
                    logger.info(f"Copied transform directory: {src_transform_dir.name}")

        # Copy cache files
        for filename in ["cache.pkl", "dag_registry.pkl"]:
            source_file = source_dir / filename
            if source_file.exists():
                dest_file = dest_dir / filename
                shutil.copy2(source_file, dest_file)
                if self.verbose_logging:
                    logger.info(f"Copied {filename} from {source_file}")

        # Load the updated cache
        self._load_cache(sub_dir)

        if self.verbose_logging:
            logger.info(
                f"Successfully copied cache from {source_cache_dir} "
                f"for transforms: {transforms_to_copy}"
            )

    def get_output(
        self, transform_name: str, data: Any, sub_dir: str | None = None
    ) -> Any:
        """
        Get the output of a specific transform in the DAG.

        Args:
            transform_name: Name of the transform whose output to retrieve
            data: Input data to the pipeline
            sub_dir: Optional subdirectory for cache organization

        Returns:
            Output of the specified transform
        """
        if transform_name not in self.transform_registry:
            raise ValueError(f"Transform '{transform_name}' not found in pipeline")

        # Run the full pipeline to ensure all dependencies are computed
        self(data, sub_dir)

        # Load the registry and return the requested output
        if self.cache_dir:
            output_registry = self._load_registry(sub_dir)
            if transform_name in output_registry:
                return output_registry[transform_name]

        raise RuntimeError(f"Output for transform '{transform_name}' not found")

    def __repr__(self) -> str:
        format_string = self.__class__.__name__ + "(\n"
        format_string += "  Execution Order:\n"
        for name in self.execution_order:
            transform = self.transform_registry[name]
            if isinstance(transform, DAGTransform) and transform.dependencies:
                format_string += f"    {name} <- {transform.dependencies}\n"
            else:
                format_string += f"    {name}\n"
        format_string += ")"
        return format_string
