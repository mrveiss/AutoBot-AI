# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task Registry for ECL Knowledge Pipeline.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from typing import Any, Callable, Dict, Type

logger = logging.getLogger(__name__)


class TaskRegistry:
    """Registry for pipeline tasks (extractors, cognifiers, loaders)."""

    _extractors: Dict[str, Type[Any]] = {}
    _cognifiers: Dict[str, Type[Any]] = {}
    _loaders: Dict[str, Type[Any]] = {}

    @classmethod
    def register_extractor(cls, name: str) -> Callable:
        """
        Decorator to register an extractor class.

        Args:
            name: Unique name for the extractor

        Returns:
            Decorator function
        """

        def decorator(extractor_class: Type[Any]) -> Type[Any]:
            if name in cls._extractors:
                logger.warning(
                    "Overwriting extractor '%s' (%s -> %s)",
                    name,
                    cls._extractors[name].__name__,
                    extractor_class.__name__,
                )
            cls._extractors[name] = extractor_class
            return extractor_class

        return decorator

    @classmethod
    def register_cognifier(cls, name: str) -> Callable:
        """
        Decorator to register a cognifier class.

        Args:
            name: Unique name for the cognifier

        Returns:
            Decorator function
        """

        def decorator(cognifier_class: Type[Any]) -> Type[Any]:
            if name in cls._cognifiers:
                logger.warning(
                    "Overwriting cognifier '%s' (%s -> %s)",
                    name,
                    cls._cognifiers[name].__name__,
                    cognifier_class.__name__,
                )
            cls._cognifiers[name] = cognifier_class
            return cognifier_class

        return decorator

    @classmethod
    def register_loader(cls, name: str) -> Callable:
        """
        Decorator to register a loader class.

        Args:
            name: Unique name for the loader

        Returns:
            Decorator function
        """

        def decorator(loader_class: Type[Any]) -> Type[Any]:
            if name in cls._loaders:
                logger.warning(
                    "Overwriting loader '%s' (%s -> %s)",
                    name,
                    cls._loaders[name].__name__,
                    loader_class.__name__,
                )
            cls._loaders[name] = loader_class
            return loader_class

        return decorator

    @classmethod
    def get_extractor(cls, name: str) -> Type[Any]:
        """Get extractor class by name."""
        return cls._extractors.get(name)

    @classmethod
    def get_cognifier(cls, name: str) -> Type[Any]:
        """Get cognifier class by name."""
        return cls._cognifiers.get(name)

    @classmethod
    def get_loader(cls, name: str) -> Type[Any]:
        """Get loader class by name."""
        return cls._loaders.get(name)

    @classmethod
    def get_task(cls, stage: str, name: str) -> Type[Any]:
        """
        Get task class by stage and name.

        Args:
            stage: Pipeline stage (extract, cognify, load)
            name: Task name

        Returns:
            Task class or None
        """
        stage_map = {
            "extract": cls._extractors,
            "cognify": cls._cognifiers,
            "load": cls._loaders,
        }
        registry = stage_map.get(stage, {})
        return registry.get(name)
