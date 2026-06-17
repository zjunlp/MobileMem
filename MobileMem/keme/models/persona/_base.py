"""Base class for all person dimension models."""
from pydantic import (
    BaseModel, 
    Field, 
    model_validator,
    field_validator,
    create_model,
    PrivateAttr, 
    computed_field,
    BeforeValidator,
    PlainSerializer,
    TypeAdapter, 
    ValidationError, 
    ConfigDict,
    ValidationInfo, 
)
import shortuuid
import inspect 
from datetime import datetime
from ...utils import get_timestamp
from .._constants import EMPTY_LIST_STR_REPR, NO_SIDE_NOTE 
from ..session import Session
from typing import(
    Any, 
    Literal, 
    ClassVar,
    Self,
    TypedDict,
    Annotated,
    get_type_hints, 
    get_origin, 
    get_args, 
)


NO_LAST_MODIFIED = "[UNKNOWN]"
NO_OPERATIONS = "[NO OPERATIONS]"
DEFAULT_DIMENSION_DESCRIPTION = "The summary of this dimension is not provided."


class AttributeVersion(TypedDict):
    """Maintain versioning and linkage relationships for trackable attributes.
    
    Each version records a historical value of an attribute along with the message IDs 
    that are connected to this attribute value.
    """

    value: str
    """The attribute value for this version."""
    
    connections: set[str]
    """Set of message IDs that are connected to this attribute version."""


class TrackedAttribute(BaseModel):
    """Maintain the current value of an attribute and a history of all previous versions,
    where each version records the value and the message IDs that are connected to it."""

    value: str = Field(
        description="The current version's value of the attribute.",
    )
    _history: list[AttributeVersion] = PrivateAttr(default_factory=list)

    def model_post_init(self, context: Any) -> None:
        """Initialize the history with the current value after model creation."""
        self._history.append(AttributeVersion(value=self.value, connections=set()))

    def add_connections(self, message_ids: list[str]) -> None:
        """Add message IDs to the current version's connections.
        
        Args:
            message_ids (`list[str]`):
                The list of message IDs to add to the current version's connections.
        """    
        current_version = self._history[-1]
        for msg_id in message_ids:
            current_version["connections"].add(msg_id)
    
    def update_value(self, new_value: str) -> None:
        """Update the attribute value and create a new version in history.
        
        Args:
            new_value (`str`):
                The new value for the attribute.
        """
        self.value = new_value
        self._history.append(AttributeVersion(value=new_value, connections=set()))

    @computed_field
    @property
    def history(self) -> list[AttributeVersion]:
        """Get the complete history of this attribute.
        
        Returns:
            `list[AttributeVersion]`:
                A list of all versions with their values and connections.
        """
        return self._history.copy()
    
    @computed_field
    @property
    def has_connections(self) -> bool:
        """Check if the current value has any message connections.
        
        Returns:
            `bool`:
                True if the current value is linked to at least one message, False otherwise.
        """
        return len(self._history[-1]["connections"]) > 0

    @computed_field
    @property
    def current_connections(self) -> set[str]:
        """Get the connections for the current version.
        
        Returns:
            `set[str]`:
                The set of message IDs connected to the current version.
        """
        return self._history[-1]["connections"].copy()

    def __str__(self) -> str:
        """Return the string representation (just the current value)."""
        return self.value

    def __repr__(self) -> str:
        """Return a detailed representation of the tracked attribute."""
        return f"TrackedAttribute(value={self.value!r}, history_length={len(self._history)})"

    def __eq__(self, other: object) -> bool:
        """Compare equality based on the current value."""
        if isinstance(other, str):
            return self.value == other
        if isinstance(other, TrackedAttribute):
            return self.value == other.value
        # Return `NotImplemented` in `__eq__` enables symmetric, extensible, and type-cooperative equality 
        # semantics by delegating unsupported comparisons back to the interpreter.
        return NotImplemented

    def __hash__(self) -> int:
        """Hash based on the current value."""
        return hash(self.value)


def _coerce_to_tracked_attribute(v: Any) -> TrackedAttribute:
    """Coerce input to a `TrackedAttribute` for Pydantic validation."""
    if isinstance(v, TrackedAttribute):
        return v
    if isinstance(v, str):
        return TrackedAttribute(value=v)
    if isinstance(v, dict) and "value" in v:
        if "history" not in v or not isinstance(v["history"], list):
            return TrackedAttribute(value=v["value"])
        try: 
            history = v["history"]
            tracked_attr = None 
            for attr_version in history: 
                attr_version = TypeAdapter(AttributeVersion).validate_python(attr_version)
                if tracked_attr is None:
                    tracked_attr = TrackedAttribute(value=attr_version["value"])
                else:
                    tracked_attr.update_value(attr_version["value"])
                tracked_attr.add_connections(attr_version["connections"])
            return tracked_attr
        except ValidationError:
            return TrackedAttribute(value=v["value"]) 
    raise ValueError(f"Cannot convert `{type(v)}` to `TrackedAttribute`")


def _serialize_tracked_attribute(v: TrackedAttribute) -> dict[str, str | list[dict[str, str | list[str]]]]:
    """Serialize a `TrackedAttribute` to string for JSON output."""
    return {
        "value": v.value,
        "history": [
            {
                "value": version["value"],
                "connections": list(version["connections"]),
            }
            for version in v.history
        ],
    }


# Annotated type for TrackedAttribute fields that accept string input
TrackedStr = Annotated[
    TrackedAttribute,
    BeforeValidator(_coerce_to_tracked_attribute),
    PlainSerializer(_serialize_tracked_attribute),
]


class PersonDimensionBase(BaseModel):
    """Base class for all person dimension models.
    
    Each dimension model represents a specific aspect of a person's profile
    (e.g., career, health, entertainment). This base class provides common
    functionality for change tracking, attribute modification via tools, and 
    markdown conversion.

    Subclassing:
        To create a custom dimension, subclass ``PersonDimensionBase`` and configure 
        the following class variables:

        - ``_dimension_description``: A human-readable description shown in the 
        markdown header (e.g., ``"Career-related Information"``).
        - ``_dimension_name``: A machine-readable identifier used by modification 
        tools (e.g., ``"career"``).
        - ``_string_fields``: A list of ``TrackedStr`` field names that can be 
        modified via ``set_string_attribute`` and linked via ``link_string_attribute``.
        By default it contains ``["description"]`` to include the base 
        ``description`` field. Override this to add more fields or remove 
        ``"description"`` if not needed.
        - ``_list_fields``: A list of ``list[TrackedStr]`` field names that can be 
        modified via ``set_list_attribute`` and linked via ``link_list_attribute_item``.
        - ``_field_display_names``: An optional mapping from field names to their 
        human-readable display names in the markdown output. If a field name is 
        not present, the display name is auto-generated from the field name by 
        replacing underscores with spaces and title-casing 
        (e.g., ``"marital_status"`` → ``"Marital Status"``).

        Then declare dimension-specific fields using ``TrackedStr`` for trackable 
        string attributes and ``list[TrackedStr]`` for trackable list attributes.

        The default ``to_markdown`` implementation renders fields based on their type:

        - Fields in ``_string_fields``: They are shown as modifiable strings with 
        ``(Mentioned: True)`` or ``(Mentioned: False)`` indicator, except the ``description`` field 
        which omits the indicator.
        - Fields in ``_list_fields``: They are shown as modifiable lists with 
        ``(Mentioned: True)`` or ``(Mentioned: False)`` indicator per item.
        - Other fields (not in ``_string_fields`` or ``_list_fields``): They are shown as read-only values.

        The rendering order follows the field declaration order in the subclass.

        Optionally, subclasses can override ``validate_instance`` for custom validation logic.
    """

    # Automatically validate the default value of the fields.
    model_config = ConfigDict(validate_default=True) 
    
    # Class variable to define the dimension description for display purposes.
    _dimension_description: ClassVar[str] = "Comprehensive Profile"
    # Class variable to define the dimension name for tool calling.
    _dimension_name: ClassVar[str] = "comprehensive_profile"

    # Class variable to store modifiable TrackedStr field names.
    # Fields listed here must be of type ``TrackedStr``.
    _string_fields: ClassVar[list[str]] = ["description"]
    # Class variable to store modifiable list[TrackedStr] field names.
    # Fields listed here must be of type ``list[TrackedStr]``.
    _list_fields: ClassVar[list[str]] = []
    # Class variable mapping field names to human-readable display names.
    # If a field name is not present, the display name is auto-generated.
    _field_display_names: ClassVar[dict[str, str]] = {}
    
    # Base optional description field, available to all dimensions.
    # Subclasses can use it by including "description" in ``_string_fields`` 
    # and providing a value at instantiation, or ignore it (a default description will be used).
    description: TrackedStr = Field(
        default=DEFAULT_DIMENSION_DESCRIPTION,
        description=(
            "A comprehensive description summarizing this dimension. "
            "It should integrate all fields into a coherent narrative."
        ),
    )

    # NOTE: `last_modified` and `operations` are not directly modified by the agent.
    last_modified: str = Field(
        default=NO_LAST_MODIFIED,
        description=(
            "Timestamp of last modification to this dimension. "
            "This field should be set to the `ended_at` time of the event that caused the modification. "
            "Initially, it should be set to the starting time of the trajectory."
        ),
    )
    operations: list[str] = Field(
        default_factory=list,
        description=(
            "Record of data operations and significant changes to this dimension. "
            "Each entry should describe what changed and why."
        ),
    )
    _removed_attributes: list[TrackedStr] = PrivateAttr(default_factory=list)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Check the type consistency of the fields declared in ``_string_fields`` and ``_list_fields``.
        
        For any field in ``_string_fields``, the type annotation should be ``TrackedStr``.
        For any field in ``_list_fields``, the type annotation should be ``list[TrackedStr]``.

        This hook is called by Pydantic after the subclass and its ``model_fields``
        are fully initialized, making it the correct place to validate class-level
        configuration.

        Args:
            **kwargs (`Any`): 
                Any keyword arguments passed to the class definition that aren't used internally 
                by pydantic.
        """
        super().__pydantic_init_subclass__(**kwargs) 

        # Get the clean type hints of the fields in the class.
        # `Annotated` will be removed.
        hints = get_type_hints(cls, include_extras=False)

        for field_name in cls._string_fields:
            if field_name not in cls.model_fields:
                raise TypeError(
                    f"Field '{field_name}' is declared in `_string_fields` of "
                    f"'{cls.__name__}', but it is not a model field."
                )
            hint = hints[field_name]
            if hint is not TrackedAttribute:
                raise TypeError(
                    f"Field '{field_name}' is declared in `_string_fields` of "
                    f"'{cls.__name__}', but its type annotation is `{hint}`, "
                    f"not `TrackedAttribute` or `TrackedStr`."
                )

        for field_name in cls._list_fields:
            is_valid = True  
            if field_name not in cls.model_fields:
                raise TypeError(
                    f"Field '{field_name}' is declared in `_list_fields` of "
                    f"'{cls.__name__}', but it is not a model field."
                )
            hint = hints[field_name]
            origin = get_origin(hint) 
            if origin is not list:
                is_valid = False 
            else: 
                args = get_args(hint)
                if len(args) != 1 or args[0] is not TrackedAttribute:
                    is_valid = False
            if not is_valid:
                raise TypeError(
                    f"Field '{field_name}' is declared in `_list_fields` of "
                    f"'{cls.__name__}', but its type annotation is `{hint}`, "
                    f"not `list[TrackedStr]` or `list[TrackedAttribute]`."
                )

    def validate_instance(self) -> None:
        """Validate the instance after initialization.
        
        This method is called after the model is initialized via `model_validator`.
        Subclasses can override this method to implement custom validation logic.
        By default, this method does nothing.
        """
        ...

    @model_validator(mode="after")
    def _run_validate_instance(self) -> Self:
        """Run instance validation after model initialization."""
        self.validate_instance()
        return self
    
    @classmethod
    def get_string_fields(cls) -> list[str]:
        """Get the list of modifiable string field names."""
        return cls._string_fields
    
    @classmethod
    def get_list_fields(cls) -> list[str]:
        """Get the list of modifiable list field names."""
        return cls._list_fields

    @classmethod
    def to_simplified_model(cls) -> type[BaseModel]:
        """Dynamically generate a simplified Pydantic model for large language model structured output.

        ``TrackedStr`` fields are replaced with ``str``, ``list[TrackedStr]``
        fields are replaced with ``list[str]``.  Only the ``description``
        metadata and default value (if any) are preserved for each field.
        Fields without a ``description`` and internal tracking fields
        (``last_modified``, ``operations``) are excluded.

        Returns:
            `type[BaseModel]`:
                A dynamically created Pydantic model class suitable for large language model structured output.
        """
        simplified_fields = {}
        skip_fields = {"last_modified", "operations"}

        for field_name, field_info in cls.model_fields.items():
            if field_name in skip_fields or not field_info.description:
                continue

            field_kwargs = {"description": field_info.description}

            # Preserve default value if present.
            if not field_info.is_required():
                if field_info.default_factory is not None:
                    field_kwargs["default_factory"] = field_info.default_factory
                else:
                    field_kwargs["default"] = field_info.default

            if field_name in cls._string_fields:
                simplified_fields[field_name] = (str, Field(**field_kwargs))
            elif field_name in cls._list_fields:
                simplified_fields[field_name] = (list[str], Field(**field_kwargs))
            else:
                simplified_fields[field_name] = (
                    field_info.annotation,
                    Field(**field_kwargs),
                )

        return create_model(
            f"{cls.__name__}Simplified",
            **simplified_fields,
        )

    @computed_field
    @property
    def removed_attributes(self) -> list[TrackedStr]:
        """Get the list of removed attributes.

        Returns:
            `list[TrackedStr]`:
                A list of removed attributes.
        """
        return self._removed_attributes.copy()

    def set_string_attribute(
        self,
        attribute_name: str,
        attribute_value: str,
        operation_description: str, 
        modified_at: str,
    ) -> str:
        """Set a string attribute value and record the operation.
        
        Args:
            attribute_name (`str`):
                The name of the attribute to update.
            attribute_value (`str`):
                The new value for the attribute.
            operation_description (`str`):
                Description of the operation to be recorded in the operation log.
                It should describe what changed and why. 
            modified_at (`str`):
                The timestamp when the modification occurred.

        Returns:
            `str`:
                The message confirming the attribute update or reporting errors.
        """
        if attribute_name not in self._string_fields:
            return (
                f"Error: Attribute '{attribute_name}' is not a valid string field for the person profile's aspect '{self._dimension_name}'. "
                f"The valid string fields are [{', '.join(sorted(self._string_fields))}]."
            )
        
        # Get the attribute and update its value
        tracked_attr = getattr(self, attribute_name)
        if tracked_attr == attribute_value:
            return (
                f"Warning: Attribute '{attribute_name}' from person profile's aspect '{self._dimension_name}' is already set to the value '{attribute_value}'. "
                "No change is needed. The operation is skipped."
            )
        tracked_attr.update_value(attribute_value)

        self.operations.append(f"Timestamp {modified_at}: {operation_description}")
        self.last_modified = modified_at

        return f"Attribute '{attribute_name}' from person profile's aspect '{self._dimension_name}' is updated successfully."

    def set_list_attribute(
        self,
        attribute_name: str,
        action: Literal["add", "revise", "delete"],
        operation_description: str,  
        modified_at: str,
        item_index: int | None = None,
        item_value: str | None = None,
    ) -> str:
        """Modify a list attribute and record the operation.
        
        Args:
            attribute_name (`str`):
                The name of the list attribute to modify.
            action (`Literal["add", "revise", "delete"]`):
                The action to perform on the list.
            operation_description (`str`):
                Description of the operation to be recorded in the operations log.
                It should describe what changed and why. 
            modified_at (`str`):
                The timestamp when the modification occurred.
            item_index (`int | None`, optional):
                The index of the item to revise or delete. Required for 'revise' and 'delete' actions.
                Ignored for 'add' action.
            item_value (`str | None`, optional):
                The value for the item to add or revise. Required for 'add' and 'revise' actions.
                Ignored for 'delete' action.
        
        Notes:
            - 'add': Add a new item to the list. 
            - 'revise': Revise an existing item at `item_index`. 
            - 'delete': Delete an item at `item_index`. 

        Returns:
            `str`:
                The message confirming the attribute update or reporting errors.
        """
        if attribute_name not in self._list_fields:
            return (
                f"Error: Attribute '{attribute_name}' is not a valid list field for the person profile's aspect '{self._dimension_name}'. "
                f"The valid list fields are [{', '.join(sorted(self._list_fields))}]."
            )
        
        if action not in ["add", "revise", "delete"]:
            return f"Error: Action '{action}' is invalid. Valid actions are ['add', 'revise', 'delete']."
        
        current_list = getattr(self, attribute_name)
        
        if action == "add":
            if item_value is None:
                return "Error: item_value is required for 'add' action."
            # Create a new attribute for the new item
            current_list.append(TrackedAttribute(value=item_value))
            text = f"The new item is added to '{attribute_name}' from the person profile's aspect '{self._dimension_name}' successfully."

            
        elif action == "revise":
            if item_index is None or item_value is None:
                return "Error: item_index and item_value are required for 'revise' action."
            if item_index < 0 or item_index >= len(current_list):
                return (
                    f"Error: item_index {item_index} is out of bounds. "
                    f"The list has {len(current_list)} item(s) (valid indices: 0 to {len(current_list) - 1})."
                )
            # Update the attribute's value
            if current_list[item_index] == item_value:
                return (
                    f"Warning: The item at index {item_index} in '{attribute_name}' from person profile's aspect '{self._dimension_name}' is already set to the value '{item_value}'. "
                    "No change is needed. The operation is skipped."
                )
            current_list[item_index].update_value(item_value)
            text = f"The item at index {item_index} in '{attribute_name}' from the person profile's aspect '{self._dimension_name}' is revised successfully."

        else:  # delete
            if item_index is None:
                return "Error: item_index is required for 'delete' action."
            if item_index < 0 or item_index >= len(current_list):
                return (
                    f"Error: item_index {item_index} is out of bounds. "
                    f"The list has {len(current_list)} item(s) (valid indices: 0 to {len(current_list) - 1})."
                )
            removed_attribute = current_list.pop(item_index)
            self._removed_attributes.append(removed_attribute)
            text = f"The item at index {item_index} in '{attribute_name}' from the person profile's aspect '{self._dimension_name}' is deleted successfully."
        
        self.operations.append(f"Timestamp {modified_at}: {operation_description}")
        self.last_modified = modified_at
        return text

    def link_string_attribute(
        self,
        attribute_name: str,
        message_ids: list[str],
    ) -> str:
        """Link session messages to a string attribute.
        
        This establishes a connection indicating that the specified messages 
        reflect this string attribute's value.
        
        Args:
            attribute_name (`str`):
                The name of the string attribute to link.
            message_ids (`list[str]`):
                The list of message IDs to link to this attribute.
        
        Returns:
            `str`:
                A message confirming the link or reporting errors.
        """
        if attribute_name not in self._string_fields:
            return (
                f"Error: Attribute '{attribute_name}' is not a valid string field for the person profile's aspect '{self._dimension_name}'. "
                f"The valid string fields are [{', '.join(sorted(self._string_fields))}]."
            )
        
        if not message_ids:
            return "Error: At least one message id is required to create a link."
        
        tracked_attr = getattr(self, attribute_name)
        tracked_attr.add_connections(message_ids)
        
        return (
            f"{len(message_ids)} message(s) are successfully linked to attribute '{attribute_name}' "
            f"from person profile's aspect '{self._dimension_name}'."
        )

    def link_list_attribute_item(
        self,
        attribute_name: str,
        item_index: int,
        message_ids: list[str],
    ) -> str:
        """Link session messages to a specific item in a list attribute.
        
        This establishes a connection indicating that the specified messages 
        reflect this list item's value.
        
        Args:
            attribute_name (`str`):
                The name of the list attribute.
            item_index (`int`):
                The index of the item in the list to link.
            message_ids (`list[str]`):
                The list of message IDs to link to this item.
        
        Returns:
            `str`:
                A message confirming the link or reporting errors.
        """
        if attribute_name not in self._list_fields:
            return (
                f"Error: Attribute '{attribute_name}' is not a valid list field for the person profile's aspect '{self._dimension_name}'. "
                f"The valid list fields are [{', '.join(sorted(self._list_fields))}]."
            )
        
        if not message_ids:
            return "Error: At least one message id is required to create a link."
        
        current_list = getattr(self, attribute_name)
        if item_index < 0 or item_index >= len(current_list):
            return (
                f"Error: item_index {item_index} is out of bounds. "
                f"The list has {len(current_list)} item(s) (valid indices: 0 to {len(current_list) - 1})."
            )
        
        current_list[item_index].add_connections(message_ids)
        
        return (
            f"{len(message_ids)} message(s) are successfully linked to " 
            f"the item at index {item_index} in '{attribute_name}' "
            f"from person profile's aspect '{self._dimension_name}'."
        )

    def get_attribute_connections(self, attribute_name: str, item_index: int | None = None) -> set[str]:
        """Get the message IDs connected to an attribute.
        
        Args:
            attribute_name (`str`):
                The name of the attribute.
            item_index (`int | None`, optional):
                For list attributes, the index of the item. If None, returns connections 
                for a string attribute.
        
        Returns:
            `set[str]`:
                The set of message IDs connected to this attribute.
        """
        if item_index is not None:
            if attribute_name not in self._list_fields:
                raise ValueError(
                    "`item_index` is provided. "
                    f"However, there is no field named '{attribute_name}' among the supported list fields."
                )
            current_list = getattr(self, attribute_name)
            if item_index < 0 or item_index >= len(current_list):
                raise ValueError(
                    f"`item_index` {item_index} is out of bounds. "
                    f"The list has {len(current_list)} item(s) " 
                    f"(valid indices: 0 to {len(current_list) - 1})."
                )
            return current_list[item_index].current_connections
        else:
            if attribute_name not in self._string_fields:
                raise ValueError(
                    "`item_index` is not provided " 
                    f"However, there is no field named '{attribute_name}' among the supported string fields."
                )
            tracked_attr = getattr(self, attribute_name)
            return tracked_attr.current_connections

    def to_markdown(self, detailed: bool = False, level: int = 0) -> str:
        """Convert the dimension model to a markdown-formatted string.

        Args:
            detailed (`bool`, defaults to `False`):
                Whether to include operation history records.
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.

        Returns:
            `str`:
                The markdown representation of this dimension.
        """
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- {self._dimension_description} "
            f"(Dimension Name: `{self._dimension_name}`):",
        ]

        # The following fields are managed by the base class and will be rendered last.
        base_field_names = {"description", "last_modified", "operations"}

        for field_name in type(self).model_fields:
            if field_name in base_field_names:
                continue
            
            # If a field's value is `None`, it will be skipped.
            value = getattr(self, field_name)
            if value is None:
                continue

            display_name = self._field_display_names.get(
                field_name,
                field_name.replace("_", " ").title(),
            )

            if field_name in self._list_fields:
                # These fields are modifiable `list[TrackedAttribute]` fields.
                if value:
                    markdown_strs.append(
                        f"{indent}\t- {display_name} "
                        f"(Attribute Name: `{field_name} (list of strings)`):",
                    )
                    markdown_strs.extend(
                        [
                            f"{indent}\t\t- {item} "
                            f"(Mentioned: {item.has_connections})"
                            for item in value
                        ]
                    )
                else:
                    markdown_strs.append(
                        f"{indent}\t- {display_name} "
                        f"(Attribute Name: `{field_name} (list of strings)`): "
                        f"{EMPTY_LIST_STR_REPR}",
                    )

            elif field_name in self._string_fields:
                # These fields are modifiable `TrackedAttribute` fields.
                markdown_strs.append(
                    f"{indent}\t- {display_name} "
                    f"(Attribute Name: `{field_name} (string)`): "
                    f"{value} (Mentioned: {value.has_connections})",
                )

            else:
                # These fields are read-only fields.
                markdown_strs.append(f"{indent}\t- {display_name}: {value}")

        # Render the base `description` field last among dimension fields.
        description_display = self._field_display_names.get(
            "description",
            "Description",
        )
        if "description" in self._string_fields:
            markdown_strs.append(
                f"{indent}\t- {description_display} "
                f"(Attribute Name: `description (string)`): "
                f"{self.description}",
            )

        markdown_strs.append(f"{indent}\t- Last Modified: {self.last_modified}")

        if detailed:
            markdown_strs.extend(self.format_operations_markdown(level + 1))
        return "\n".join(markdown_strs)

    def format_operations_markdown(self, level: int = 0) -> list[str]:
        """A helper method to format the operation list for markdown output.
        
        Args:
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.

        Returns:
            `list[str]`:
                The formatted operation list for the markdown output.
        """
        indent = "\t" * level
        if len(self.operations) > 0:
            return [
                f"{indent}- The Operation History of Dimension '{self._dimension_name}'",
                *[f"{indent}\t- {op}" for op in self.operations],
            ]
        return [f"{indent}- The Operation History of Dimension '{self._dimension_name}': {NO_OPERATIONS}"]


class PersonBase(BaseModel):
    """The root node representing the user's global identity and context.
    
    This model captures the user's complete profile through multiple dimensions,
    each managed independently for fine-grained change tracking. The person model
    uses a compositional design pattern where each dimension is a separate model
    with its own `last_modified` and `operations` fields.

    Subclass this and declare `PersonDimensionBase` fields to compose a custom persona profile schema.
    The dimension mapping is auto-discovered from model fields.
    """

    # Mapping from dimension name to `PersonBase` instance attribute name for tool access. 
    # This mapping is auto-discovered from model fields.
    # The mapping is unique for each subclass and will not be polluted by other subclasses.
    _dimension_mapping: ClassVar[dict[str, str]] = {}

    id: str = Field(
        default_factory=lambda: f"person_{shortuuid.uuid()}",
        description="Unique person identifier.",
    )
    name: str = Field(
        description="Person's full name (1-10 words).",
    )
    
    trajectory_start: str = Field(
        description=(
            "Global start timestamp for the entire trajectory in ISO 8601 format (YYYY-MM-DD HH:MM:SS). "
            "This defines the earliest possible time for any event or conversation in the trajectory."
        ),
    )
    trajectory_end: str = Field(
        description=(
            "Global end timestamp for the entire trajectory in ISO 8601 format (YYYY-MM-DD HH:MM:SS). "
            "This defines the latest possible time for any event or conversation in the trajectory."
        ),
    )
    
    # Side note for Person-level commentary (dimensions don't have side notes)
    side_note: str = Field(
        default=NO_SIDE_NOTE,
        description=(
            "Commentary on why this user profile supports the overall objectives "
            "of the synthesis task and what makes it interesting or challenging."
        ),
    )

    created_at: str = Field(
        default_factory=get_timestamp,
        description="Timestamp of creation of the person object **in real-world system time**.",
    )
    finished_at: str | None = Field(
        default=None,
        description="Timestamp of completion of the synthesis task **in real-world system time**.",
    )

    # The off-the-shelf external sessions are allocated from the top persona root node 
    # to the bottom session leaf nodes.
    _grounded_sessions: list[Session] = PrivateAttr(default_factory=list)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Initialize the dimension mapping for the subclass based on its model fields.
        
        The mapping is unique for each subclass and will not be polluted by other subclasses.

        Args:
            **kwargs (`Any`): 
                Any keyword arguments passed to the class definition that aren't used internally 
                by pydantic.
        """
        super().__pydantic_init_subclass__(**kwargs)

        mapping = {}
        for field_name, field_info in cls.model_fields.items():
            annotation = field_info.annotation
            # `str | None` is not a class.
            if inspect.isclass(annotation) and issubclass(annotation, PersonDimensionBase):
                dim_name = annotation._dimension_name
                if dim_name in mapping:
                    raise TypeError(
                        f"Dimension name '{dim_name}' is duplicated in the class '{cls.__name__}'. "
                        f"Fields '{mapping[dim_name]}' and '{field_name}' both use the same dimension name."
                    )
                mapping[dim_name] = field_name

        cls._dimension_mapping = mapping

    @field_validator("trajectory_start")
    @classmethod
    def validate_trajectory_start(cls, v: str) -> str:
        """Validate that `trajectory_start` is a valid ISO 8601 string."""
        try:
            _ = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"The trajectory start time '{v}' is not in a valid format. "
                "Please use the format YYYY-MM-DD HH:MM:SS, for example: "
                "'2024-08-25 12:01:42'."
            )
        return v

    @field_validator("trajectory_end")
    @classmethod
    def validate_trajectory_end(cls, v: str, info: ValidationInfo) -> str:
        """Validate that `trajectory_end` is after `trajectory_start`."""
        if "trajectory_start" not in info.data:
            # If `trajectory_start` failed its own validation, we skip the cross-field check.
            return v
        start = datetime.fromisoformat(info.data["trajectory_start"])
        try:
            end = datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(
                f"The trajectory end time '{v}' is not in a valid format. "
                "Please use the format YYYY-MM-DD HH:MM:SS, for example: "
                "'2024-06-01 09:30:00'."
            )
        if end <= start:
            raise ValueError(
                f"The trajectory end time '{v}' must be after "
                f"the trajectory start time '{info.data['trajectory_start']}'. Please ensure "
                "the trajectory has a valid time range."
            )   
        return v
    
    def add_grounded_session(self, session: Session) -> None:
        """Add a grounded (pre-existing) session to this person profile.
        
        Grounded sessions are pre-existing session data belong to this person profile. 
        They are stored in chronological order based on their start time.
        
        Args:
            session (`Session`):
                The session to add to the grounded sessions list.
                The session will be inserted in chronological order.
        """
        sess_start = datetime.fromisoformat(session.started_at)
        sessions = self._grounded_sessions

        left, right = 0, len(sessions)
        while left < right:
            mid = (left + right) // 2
            mid_start = datetime.fromisoformat(sessions[mid].started_at)
            if sess_start < mid_start:
                right = mid
            else:
                left = mid + 1
        sessions.insert(left, session)

    @computed_field
    @property
    def grounded_sessions(self) -> list[Session]:
        """Get all grounded sessions belong to this person profile.
        
        Returns:
            `list[Session]`:
                A list of grounded sessions in chronological order
                based on their start time.
        """
        return self._grounded_sessions.copy()

    @computed_field
    @property
    def num_grounded_sessions(self) -> int:
        """Get the number of grounded sessions belong to this person profile.
        
        Returns:
            `int`:
                The number of grounded sessions.
        """
        return len(self._grounded_sessions)

    @computed_field
    @property
    def has_grounded_sessions(self) -> bool:
        """Check if this person profile has any grounded sessions.
        
        Returns:
            `bool`:
                True if the person profile has grounded sessions, False otherwise.
        """
        return len(self._grounded_sessions) > 0
    
    @classmethod
    def get_dimension_names(cls) -> list[str]:
        """Get list of all dimension names.""" 
        return sorted(cls._dimension_mapping.keys())

    @classmethod
    def get_dimension_fields(cls) -> list[tuple[str, type[PersonDimensionBase]]]:
        """Get a list of tuples for all dimension fields.
        
        Returns:
            `list[tuple[str, type[PersonDimensionBase]]]`:
                A list of tuples where each tuple contains the 
                attribute name on this model and the corresponding ``PersonDimensionBase`` 
                subclass type.
        """
        result = []
        for field_name, field_info in cls.model_fields.items():
            annotation = field_info.annotation
            if inspect.isclass(annotation) and issubclass(annotation, PersonDimensionBase):
                result.append((field_name, annotation))
        return result
    
    def get_dimension(self, dimension_name: str) -> PersonDimensionBase | None:
        """Get a dimension model by name.
        
        Args:
            dimension_name (`str`):
                The name of the dimension to retrieve.
            
        Returns:
            `PersonDimensionBase | None`:
                The dimension model if found, None otherwise.
        """
        if dimension_name not in self._dimension_mapping:
            return None
        field_name = self._dimension_mapping[dimension_name]
        return getattr(self, field_name)

    def set_dimension_string_attribute(
        self,
        dimension_name: str,
        attribute_name: str,
        attribute_value: str,
        operation_description: str,  
        modified_at: str,
    ) -> str:
        """Set a string attribute value in a specific dimension.
        
        Args:
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the attribute to update.
            attribute_value (`str`):
                The new value for the attribute.
            operation_description (`str`):
                Description of the operation to be recorded.
            modified_at (`str`):
                The timestamp when the modification occurred.
            
        Returns:
            `str`:
                The message confirming the attribute update or reporting errors.
        """
        dimension = self.get_dimension(dimension_name)
        if dimension is None:
            return (
                f"Error: Dimension '{dimension_name}' is not found. "
                f"The valid dimensions are {', '.join(sorted(self._dimension_mapping.keys()))}."
            )
        return dimension.set_string_attribute(
            attribute_name, 
            attribute_value, 
            operation_description,  
            modified_at, 
        )

    def set_dimension_list_attribute(
        self,
        dimension_name: str,
        attribute_name: str,
        action: Literal["add", "revise", "delete"],
        operation_description: str,   
        modified_at: str,
        item_index: int | None = None,
        item_value: str | None = None,
    ) -> str:
        """Modify a list attribute in a specific dimension.
        
        Args:
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the list attribute to modify.
            action (`Literal["add", "revise", "delete"]`):
                The action to perform on the list.
            operation_description (`str`):
                Description of the operation to be recorded.
            modified_at (`str`):
                The timestamp when the modification occurred.
            item_index (`int | None`, optional):
                The index of the item to revise or delete.
            item_value (`str | None`, optional):
                The value for the item to add or revise.

        Returns:
            `str`:
                The message confirming the attribute update or reporting errors.
        """
        dimension = self.get_dimension(dimension_name)
        if dimension is None:
            return (
                f"Error: Dimension '{dimension_name}' is not found. "
                f"The valid dimensions are {', '.join(sorted(self._dimension_mapping.keys()))}."
            )
        return dimension.set_list_attribute(
            attribute_name, 
            action, 
            operation_description,   
            modified_at, 
            item_index=item_index, 
            item_value=item_value, 
        )

    def get_dimension_operations(self, dimension_name: str) -> str:
        """Get the operation history of a specific dimension.
        
        Args:
            dimension_name (`str`):
                The name of the dimension.
            
        Returns:
            `str`:
                The operation history of the dimension. If the dimension is not found, return an string indicating the error.
        """
        dimension = self.get_dimension(dimension_name)
        if dimension is None:
            return f"Error: Dimension '{dimension_name}' is not found. The valid dimensions are {', '.join(sorted(self._dimension_mapping.keys()))}."
        return "\n".join(dimension.format_operations_markdown(level=0))

    def link_string_attribute(
        self,
        dimension_name: str,
        attribute_name: str,
        message_ids: list[str],
    ) -> str:
        """Link session messages to a string attribute in a specific dimension.
        
        This establishes a connection indicating that the specified messages 
        reflect this string attribute's value.
        
        Args:
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the string attribute to link.
            message_ids (`list[str]`):
                The list of message IDs to link to this attribute.
        
        Returns:
            `str`:
                A message confirming the link or reporting errors.
        """
        dimension = self.get_dimension(dimension_name)
        if dimension is None:
            return (
                f"Error: Dimension '{dimension_name}' is not found. "
                f"The valid dimensions are {', '.join(sorted(self._dimension_mapping.keys()))}."
            )
        return dimension.link_string_attribute(attribute_name, message_ids)

    def link_list_attribute_item(
        self,
        dimension_name: str,
        attribute_name: str,
        item_index: int,
        message_ids: list[str],
    ) -> str:
        """Link session messages to a specific item in a list attribute.
        
        This establishes a connection indicating that the specified messages 
        reflect this list item's value.
        
        Args:
            dimension_name (`str`):
                The name of the dimension containing the attribute.
            attribute_name (`str`):
                The name of the list attribute.
            item_index (`int`):
                The index of the item in the list to link.
            message_ids (`list[str]`):
                The list of message IDs to link to this item.
        
        Returns:
            `str`:
                A message confirming the link or reporting errors.
        """
        dimension = self.get_dimension(dimension_name)
        if dimension is None:
            return (
                f"Error: Dimension '{dimension_name}' is not found. "
                f"The valid dimensions are {', '.join(sorted(self._dimension_mapping.keys()))}."
            )
        return dimension.link_list_attribute_item(attribute_name, item_index, message_ids)

    def to_markdown(
        self, 
        include_side_note: bool = False, 
        detailed: bool = False,
        level: int = 0,
        exclude: list[str] | None = None, 
    ) -> str:
        """Convert the person profile to MarkDown format.
        
        Args:
            include_side_note (`bool`, defaults to `False`):
                Whether to include side note of the person object.
            detailed (`bool`, defaults to `False`):
                Whether to include operation history of the person profile.
            level (`int`, defaults to `0`):
                The indentation level for the markdown output.
            exclude (`list[str] | None`, defaults to `None`):
                The list of dimension names to exclude from the markdown output.
            
        Returns:
            `str`:
                The markdown representation of this person.
        """
        indent = "\t" * level
        
        if exclude is None:
            exclude = []
        markdown_strs = [
            f"{indent}- Person: {self.name}",
            *[
                self.get_dimension(dimension_name).to_markdown(detailed=detailed, level=level + 1)
                for dimension_name in sorted(self._dimension_mapping.keys()) if dimension_name not in exclude
            ],
        ]
                
        markdown_strs.extend(
            [
                f"{indent}\t- Trajectory Time Range: {self.trajectory_start} to {self.trajectory_end}",
                f"{indent}\t- Created At In Real-World System Time: {self.created_at}",
            ]
        )

        if include_side_note:
            markdown_strs.append(f"{indent}\t- Side Note: {self.side_note}")
        
        if self.finished_at is not None:
            markdown_strs.append(f"{indent}\t- Finished At In Real-World System Time: {self.finished_at}")
        return "\n".join(markdown_strs)
