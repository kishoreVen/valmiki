
from abc import ABC, abstractmethod
from typing import final, Any, Dict, List, Callable
from pathlib import Path
import hashlib
import json
import pickle
import logging
import shutil

logger = logging.getLogger(__name__)


class MemoizableTransform(ABC):
    """Base class for transforms that can be serialized and memoized."""

    def __init__(self):
        self._loaded_from_cache_dir = False
        self._loaded_from_cache = False
        self.verbose_logging = False

    def serialize(self, result: Any, cache_dir: str) -> None:
        """Serialize transform parameters into a dictionary."""
        ...

    def deserialize(self, cache_dir: str) -> Any:
        """Deserialize transform parameters from a dictionary."""
        ...

    @abstractmethod
    def __call__(self, *args: Any, **kwds: Any) -> Any: ...

    @final
    @property
    def is_loaded_from_cache(self) -> bool:
        """Check if transform was loaded from either cache or cache directory."""
        return self._loaded_from_cache_dir or self._loaded_from_cache

    @final
    @property
    def is_loaded_from_cache_dir(self) -> bool:
        """Check if transform was loaded specifically from cache directory."""
        return self._loaded_from_cache_dir

    @final
    def get_cache_key(self, input_data: Any) -> str:
        """Generate a cache key based on transform parameters and input data."""
        combined_data = {
            "transform_class": self.__class__.__name__,
            "input_hash": self._hash_input(input_data),
        }
        serialized = json.dumps(combined_data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @final
    def _hash_input(self, input_data: Any) -> str:
        """Create a hash of the input data."""
        if hasattr(input_data, "__dict__"):
            # For objects, use their string representation
            return hashlib.sha256(str(input_data.__dict__).encode()).hexdigest()
        else:
            # For simple types or tensors
            return hashlib.sha256(str(input_data).encode()).hexdigest()


class MemoizedCompose:
    """A Compose class that mimics torchvision's Compose with memoization support."""

    def __init__(
        self,
        transforms: List[Callable],
        cache_dir: str | Path | None = None,
        verbose_logging: bool = False,
        copy_from_cache_dir: str | Path | None = None,
        copy_from_start_stage: int | str | None = None,
    ):
        """
        Initialize MemoizedCompose.

        Args:
            transforms: List of callable transforms
            cache_dir: Optional directory path for transform-specific storage and cache
            verbose_logging: Enable verbose logging for transform operations
            copy_from_cache_dir: Optional source cache directory to copy from on first run
            copy_from_start_stage: Optional stage to start copying from (int index or class name)
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

        # Set verbose_logging on all transforms that support it
        for transform in self.transforms:
            if isinstance(transform, MemoizableTransform):
                transform.verbose_logging = self.verbose_logging

    def _get_transform_directory(
        self,
        index: int,
        transform: MemoizableTransform,
        call_sub_dir: str | None = None,
    ) -> Path:
        """Get the directory path for a specific transform."""

        if (cache_dir := self.cache_dir) is None:
            raise ValueError(
                f"Cache Dir shouldn't be none if calling _get_transform_directory"
            )

        dir_name = f"{index:02d}_{transform.__class__.__name__}"
        if call_sub_dir:
            return cache_dir / call_sub_dir / dir_name
        return cache_dir / dir_name

    def _ensure_transform_directory(
        self,
        index: int,
        transform: MemoizableTransform,
        call_sub_dir: str | None = None,
    ) -> Path:
        """Ensure the transform directory exists and return its path."""
        transform_dir = self._get_transform_directory(index, transform, call_sub_dir)
        transform_dir.mkdir(parents=True, exist_ok=True)
        return transform_dir

    def _get_cache_file_path(self, call_sub_dir: str | None) -> Path:
        """Get the path to the cache file."""
        if (cache_dir := self.cache_dir) is None:
            raise ValueError(
                f"Cache Dir shouldn't be none if calling _get_cache_file_path"
            )

        if call_sub_dir is None:
            return cache_dir / "cache.pkl"
        else:
            return cache_dir / call_sub_dir / "cache.pkl"

    def _load_cache(self, call_sub_dir: str | None) -> None:
        """Load cache from disk if it exists."""
        cache_file = self._get_cache_file_path(call_sub_dir)
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    self.cache = pickle.load(f)
            except (pickle.PickleError, IOError, EOFError):
                # If cache file is corrupted, start with empty cache
                self.cache = {}

    def _save_cache(self, call_sub_dir: str | None) -> None:
        """Save cache to disk."""
        if self.cache_dir:
            cache_file = self._get_cache_file_path(call_sub_dir)
            with open(cache_file, "wb") as f:
                pickle.dump(self.cache, f, protocol=pickle.HIGHEST_PROTOCOL)

    def __call__(self, data: Any, sub_dir: str | None = None) -> Any:
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

        """Apply transforms sequentially with memoization where possible."""
        result = data
        output_registry = {"_input": data}

        for i, transform in enumerate(self.transforms):
            if isinstance(transform, MemoizableTransform):
                if self.verbose_logging:
                    logger.info(
                        f"Transform {i + 1}: {transform.__class__.__name__} (memoizable)"
                    )
                # Reset cache flags for each transform call
                transform._loaded_from_cache = False
                transform._loaded_from_cache_dir = False

                # Try to get from cache
                cache_key = transform.get_cache_key(result)

                if cache_key in self.cache:
                    result = self.cache[cache_key]
                    transform._loaded_from_cache = True
                    if self.verbose_logging:
                        logger.info(
                            f"  → Loaded from memory cache (key: {cache_key[:8]}...)"
                        )
                elif self.cache_dir:
                    transform_dir = self._get_transform_directory(i, transform, sub_dir)

                    if transform_dir.exists():
                        cached_result = transform.deserialize(str(transform_dir))
                        if cached_result is not None:
                            result = cached_result
                            transform._loaded_from_cache_dir = True
                            if self.verbose_logging:
                                logger.info(
                                    f"  → Loaded from directory cache: {transform_dir}"
                                )

                # If not in directory cache, apply transform
                if not transform.is_loaded_from_cache:
                    if self.verbose_logging:
                        logger.info(f"  → Applying transform (not in cache)")
                    result = transform(result)

                # Always save to memory cache unless it was already loaded from memory cache
                if not transform._loaded_from_cache:
                    self.cache[cache_key] = result
                    self._save_cache(sub_dir)
                    if self.verbose_logging:
                        logger.info(
                            f"  → Saved to memory cache (key: {cache_key[:8]}...)"
                        )

                # Save to directory if available
                if self.cache_dir and not transform.is_loaded_from_cache_dir:
                    transform_dir = self._ensure_transform_directory(
                        i, transform, sub_dir
                    )
                    transform.serialize(result, str(transform_dir))
                    if self.verbose_logging:
                        logger.info(f"  → Saved to directory cache: {transform_dir}")
            else:
                # Non-memoizable transform, just apply it
                if self.verbose_logging:
                    logger.info(
                        f"Transform {i}: {transform.__class__.__name__} (non-memoizable)"
                    )
                    logger.info(f"  → Applying transform directly")
                result = transform(result)

            # Store result in registry with transform name
            transform_name = f"{i:02d}_{transform.__class__.__name__}"
            output_registry[transform_name] = result

        return output_registry

    def _copy_cache_from(
        self,
        source_cache_dir: str | Path,
        start_stage: int | str | None = None,
        sub_dir: str | None = None,
    ) -> None:
        """
        Copy cache from another pipeline directory up to a specified stage.

        Args:
            source_cache_dir: Directory containing the source cache to copy from
            start_stage: Either:
                - Transform index to start from (0-based integer)
                - Transform class name to start from (e.g., "AddTransform")
                - If None, uses last available stage
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

        # Find all transform directories in source
        transform_dirs = []
        for item in source_dir.iterdir():
            if item.is_dir() and item.name[0:2].isdigit() and "_" in item.name:
                try:
                    index = int(item.name.split("_")[0])
                    transform_dirs.append((index, item))
                except ValueError:
                    continue

        transform_dirs.sort(key=lambda x: x[0])

        # Determine start stage index
        start_stage_index = None

        if start_stage is None:
            # Use the last available stage
            if transform_dirs:
                start_stage_index = transform_dirs[-1][0] + 1
            else:
                start_stage_index = 0
        elif isinstance(start_stage, str):
            # Find the index by class name
            found = False
            for index, dir_path in transform_dirs:
                # Extract class name from directory name (format: "00_ClassName")
                class_name = (
                    dir_path.name.split("_", 1)[1] if "_" in dir_path.name else ""
                )
                if class_name == start_stage:
                    start_stage_index = index
                    found = True
                    break

            if not found:
                # If not found in source dirs, check our own transforms
                for i, transform in enumerate(self.transforms):
                    if transform.__class__.__name__ == start_stage:
                        start_stage_index = i
                        found = True
                        break

                if not found:
                    raise ValueError(
                        f"Transform class '{start_stage}' not found in pipeline"
                    )
        else:
            # It's an integer index
            start_stage_index = start_stage

        # Copy transform directories up to start_stage_index
        for index, src_transform_dir in transform_dirs:
            if index < start_stage_index:
                dest_transform_dir = dest_dir / src_transform_dir.name
                if dest_transform_dir.exists():
                    shutil.rmtree(dest_transform_dir)
                shutil.copytree(src_transform_dir, dest_transform_dir)
                if self.verbose_logging:
                    logger.info(f"Copied transform directory: {src_transform_dir.name}")

        # Copy cache.pkl without filtering
        # Since we can't reconstruct which transform created each cache entry from the hash,
        # we'll copy all cache entries. The directory-based cache will still be filtered correctly.
        source_cache_file = source_dir / "cache.pkl"
        if source_cache_file.exists():
            dest_cache_file = dest_dir / "cache.pkl"
            shutil.copy2(source_cache_file, dest_cache_file)

            if self.verbose_logging:
                logger.info(f"Copied cache.pkl from {source_cache_file}")

        # Load the updated cache
        self._load_cache(sub_dir)

        if self.verbose_logging:
            logger.info(
                f"Successfully copied cache from {source_cache_dir} starting from stage {start_stage_index}"
            )

    def __repr__(self) -> str:
        format_string = self.__class__.__name__ + "("
        for t in self.transforms:
            format_string += "\n    {0}".format(t)
        format_string += "\n)"
        return format_string
