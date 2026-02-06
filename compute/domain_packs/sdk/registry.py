"""Domain Pack Registry for managing pack registration and instantiation."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import DomainPackBase


class DomainPackRegistry:
    """
    Registry for domain packs.
    
    Provides a central location for:
    - Registering domain pack classes
    - Looking up packs by name
    - Creating pack instances with version tracking
    """
    
    _registry: Dict[str, Type["DomainPackBase"]] = {}
    _versions: Dict[str, Dict[str, Type["DomainPackBase"]]] = {}
    
    @classmethod
    def register(cls, pack_class: Type["DomainPackBase"]) -> Type["DomainPackBase"]:
        """
        Register a domain pack class.
        
        Can be used as a decorator:
            @DomainPackRegistry.register
            class MyPack(DomainPackBase):
                name = "my-pack"
                version = "1.0.0"
        
        Args:
            pack_class: The domain pack class to register
            
        Returns:
            The same class (for decorator use)
        """
        name = pack_class.name
        version = pack_class.version
        
        # Register by name (latest)
        cls._registry[name] = pack_class
        
        # Register by name+version
        if name not in cls._versions:
            cls._versions[name] = {}
        cls._versions[name][version] = pack_class
        
        return pack_class
    
    @classmethod
    def get(cls, name: str, version: Optional[str] = None) -> Optional[Type["DomainPackBase"]]:
        """
        Get a domain pack class by name.
        
        Args:
            name: The pack name
            version: Optional specific version
            
        Returns:
            The pack class or None if not found
        """
        if version is not None:
            versions = cls._versions.get(name, {})
            return versions.get(version)
        return cls._registry.get(name)
    
    @classmethod
    def create_instance(
        cls,
        name: str,
        version: Optional[str] = None,
    ) -> Optional["DomainPackBase"]:
        """
        Create an instance of a domain pack.
        
        Args:
            name: The pack name
            version: Optional specific version
            
        Returns:
            An instance of the pack or None if not found
        """
        pack_class = cls.get(name, version)
        if pack_class is None:
            return None
        return pack_class()
    
    @classmethod
    def list_packs(cls) -> List[str]:
        """Get list of all registered pack names."""
        return list(cls._registry.keys())
    
    @classmethod
    def list_versions(cls, name: str) -> List[str]:
        """Get list of all versions for a pack."""
        versions = cls._versions.get(name, {})
        return list(versions.keys())
    
    @classmethod
    def get_pack_info(cls, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered pack."""
        pack_class = cls.get(name)
        if pack_class is None:
            return None
        
        return {
            "name": pack_class.name,
            "version": pack_class.version,
            "description": pack_class.description,
            "metrics": pack_class.metrics,
            "fidelity_modes": [f.value for f in pack_class.fidelity_modes],
        }
    
    @classmethod
    def clear(cls) -> None:
        """Clear the registry (for testing)."""
        cls._registry.clear()
        cls._versions.clear()
