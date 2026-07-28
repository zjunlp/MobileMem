# -*- coding: utf-8 -*-
"""Base class for all notebook classes used in trajectory synthesis."""
from abc import ABC, abstractmethod
from collections import OrderedDict
from agentscope.module import StateModule
from agentscope.message import Msg
from agentscope.tool import ToolResponse
from ..utils import execute_async_or_sync_func
from typing import (
    Callable, 
    Coroutine, 
    Any,
) 


class NotebookBase(StateModule, ABC):
    """
    Base class for all notebook classes.
    
    It provides common functionality including:
    - Abstract methods: `list_tools`, `get_current_hint`
    - Hook management: register/remove/trigger hooks at both instance and class level
    
    Each subclass automatically gets its own isolated class-level hooks dictionary.
    """
    
    # Global hooks that will be triggered for all instances. 
    _class_hooks: OrderedDict[str, Callable[..., None]] = OrderedDict() 
    
    # Description and name for the notebook, should be overridden by subclasses.
    # These are used when registering tools with meta-tool support.
    description: str = "Base notebook class."
    name: str = "base_notebook"
    
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Initialize each subclass with its own class-level hooks dictionary."""
        super().__init_subclass__(**kwargs)
        # Each subclass gets its own independent class-level hooks dictionary.
        cls._class_hooks = OrderedDict()
    
    def __init__(self) -> None:
        """Initialize the notebook with an empty instance-level hooks dictionary."""
        super().__init__()
        # Instance-level hooks
        self._hooks = OrderedDict()
    
    @abstractmethod
    def list_tools(self) -> list[Callable[..., Coroutine[Any, Any, ToolResponse]]]:
        """
        List all tool functions provided to agent.
        
        This method should return all async tool functions that the agent can call
        when using this notebook. Each tool function should:
        - Be an async method that returns a `ToolResponse`
        - Have proper type annotations for the agent to understand the parameters
        - Include docstrings that describe the tool's purpose and usage
        
        Returns:
            `list[Callable[..., Coroutine[Any, Any, ToolResponse]]]`:
                A list of all tool functions provided by the graph refinement notebook to
                the agent.
        """
        ...
    
    @abstractmethod
    async def get_current_hint(self) -> Msg | None:
        """
        Get the hint message based on the current notebook state.
        
        This method is called during the agent's reasoning process to provide
        contextual hints about what actions are available or recommended.
        The hint message guides the agent on next steps based on the current state.
        
        Returns:
            `Msg | None`:
                The hint message wrapped by <system-hint></system-hint>, or
                None if there is no relevant hint.
        """
        ...

    @abstractmethod 
    def is_finished(self) -> ToolResponse:
        """
        Check whether the current state of the notebook is the final state. It is useful to detect whether 
        the agent early stops the task.
        
        Returns:
            `ToolResponse`:
                The response of the tool call, confirming the notebook is in the final state.
        """
        ... 
    
    def register_hook(
        self,
        hook_name: str,
        hook: Callable[..., None],
    ) -> None:
        """Register an instance-level hook that will be triggered when the notebook state changes.
        
        Args:
            hook_name (`str`):
                The name of the hook, should be unique within this instance.
                If a hook with the same name already exists, it will be overwritten.
            hook (`Callable[..., None]`):
                The hook function to be called when state changes. 
        """
        self._hooks[hook_name] = hook
    
    def remove_hook(self, hook_name: str) -> None:
        """Remove an instance-level hook by given name.

        Args:
            hook_name (`str`):
                The name of the hook to be removed.
        """
        if hook_name in self._hooks:
            self._hooks.pop(hook_name)
        else:
            raise ValueError(f"Hook '{hook_name}' is not found.")

    def clear_hooks(self) -> None:
        """Clear all instance-level hooks."""
        self._hooks.clear()
    
    @classmethod
    def register_class_hook(
        cls,
        hook_name: str,
        hook: Callable[..., None],
    ) -> None:
        """Register a class-level hook that will be triggered for all instances of this class.
        
        Args:
            hook_name (`str`):
                The name of the hook, should be unique within this class.
                If a hook with the same name already exists, it will be overwritten.
            hook (`Callable[..., None]`):
                The hook function to be called when state changes. 
        """
        cls._class_hooks[hook_name] = hook
    
    @classmethod
    def remove_class_hook(cls, hook_name: str) -> None:
        """Remove a class-level hook by given name.
        
        Args:
            hook_name (`str`):
                The name of the hook to be removed.
        """
        if hook_name in cls._class_hooks:
            cls._class_hooks.pop(hook_name)
        else:
            raise ValueError(f"Global hook '{hook_name}' is not found.")
    
    @classmethod
    def clear_class_hooks(cls) -> None:
        """Clear all class-level hooks."""
        cls._class_hooks.clear()
    
    async def _trigger_hooks(self, *args: Any) -> None:
        """Trigger all hooks (both class-level and instance-level).
        
        Execution order:
        1. Class-level hooks are triggered first (in registration order)
        2. Instance-level hooks are triggered second (in registration order)
        
        Args:
            *args (`Any`):
                Additional arguments to pass to the hook functions. 
        """
        # Trigger global hooks first. 
        for hook in self._class_hooks.values():
            await execute_async_or_sync_func(
                hook, 
                self, 
                *args,
            )
        
        # Then trigger instance-specific hooks. 
        for hook in self._hooks.values():
            await execute_async_or_sync_func(
                hook, 
                self, 
                *args,
            )

