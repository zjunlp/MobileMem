"""Profile creation utilities for KEME."""
import os
from pydantic import create_model, Field
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.formatter import OpenAIChatFormatter
from ..toolkits.agent import SynthesisAgent
from ..models.persona._base import PersonBase, PersonDimensionBase
from ..utils import PROFILE_CREATION_SYSTEM_PROMPT
from typing import Any


# Default agent name used for profile creation.
DEFAULT_PROFILE_CREATION_AGENT_NAME = "profile_creation_agent"

# Default instruction template for dimension synthesis.
DEFAULT_DIMENSION_TASK_TEMPLATE = (
    "Please synthesize the content for the required profile dimension(s) "
    "based on the persona seed description and the already-synthesized parts "
    "of the person profile.\n\n"
    "Persona Seed: {persona_seed}\n\n"
    "Current Person Profile (already synthesized parts):\n"
    "{current_profile}\n\n"
    "Generate realistic, coherent, and detailed content for all required fields."
)

# Default instruction template for meta-field synthesis.
DEFAULT_META_TASK_TEMPLATE = (
    "Based on the following synthesized person profile, please generate "
    "the required fields for this person. You can write a side note to comment on the person's profile.\n\n"
    "Person Profile:\n{current_profile}\n\n"
    "Generate realistic and coherent values for all required fields."
)


def _build_default_model() -> OpenAIChatModel:
    """Build the default chat model from environment variables.

    Returns:
        `OpenAIChatModel`:
            An ``OpenAIChatModel`` initialised with ``gpt-4.1``, using
            ``OPENAI_API_KEY`` and ``OPENAI_API_BASE`` from the environment.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_API_BASE")
    client_args = {"base_url": base_url} if base_url else None
    return OpenAIChatModel(
        model_name="gpt-4.1",
        api_key=api_key,
        client_args=client_args,
    )


def _prepare_agent_kwargs(agent_kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prepare agent keyword arguments.

    Args:
        agent_kwargs (`dict[str, Any] | None`, optional):
            User-supplied keyword arguments.

    Returns:
        `dict[str, Any]`:
            A dictionary ready to be unpacked into agent constructor.
    """
    if agent_kwargs is None:
        return {
            "name": DEFAULT_PROFILE_CREATION_AGENT_NAME,
            "sys_prompt": PROFILE_CREATION_SYSTEM_PROMPT,
            "model": _build_default_model(),
            "formatter": OpenAIChatFormatter(),
        }

    prepared = agent_kwargs.copy()
    if "name" not in prepared:
        prepared["name"] = DEFAULT_PROFILE_CREATION_AGENT_NAME
    if "sys_prompt" not in prepared:
        prepared["sys_prompt"] = PROFILE_CREATION_SYSTEM_PROMPT
    if "model" not in prepared:
        prepared["model"] = _build_default_model()
    if "formatter" not in prepared:
        prepared["formatter"] = OpenAIChatFormatter()
    return prepared


def _normalize_dimension_order(
    dimension_order: list[str] | list[list[str]],
    valid_field_names: set[str],
) -> list[list[str]]:
    """Normalise the dimension order to a 2-D list and validate field names.

    Args:
        dimension_order (`list[str] | list[list[str]]`):
            User-supplied dimension ordering or grouping.
        valid_field_names (`set[str]`):
            The set of valid dimension field names from the profile schema.

    Returns:
        `list[list[str]]`:
            A normalised 2-D list of field-name groups.
    """
    if not dimension_order:
        raise ValueError("`dimension_order` must be a non-empty list.")

    # Determine the dimension order type.
    if all(isinstance(item, str) for item in dimension_order):
        groups = [[item] for item in dimension_order]
    elif all(isinstance(item, list) for item in dimension_order):
        for group in dimension_order:
            if not group:
                raise ValueError(
                    "Each group in `dimension_order` must be a non-empty list."
                )
            if not all(isinstance(name, str) for name in group):
                raise TypeError(
                    "Each element in a dimension group must be a string field name."
                )
        groups = dimension_order
    else:
        raise TypeError(
            "`dimension_order` must be either a list of strings or "
            "a list of lists of strings."
        )

    # Validate field names and check for duplicates.
    seen = set()
    for group in groups:
        for field_name in group:
            if field_name not in valid_field_names:
                raise ValueError(
                    f"Field name '{field_name}' is not a valid dimension field. "
                    f"Valid dimension fields are: {sorted(valid_field_names)}."
                )
            if field_name in seen:
                raise ValueError(
                    f"Field name '{field_name}' appears more than once in "
                    "`dimension_order`."
                )
            seen.add(field_name)

    return groups


def _build_current_profile_text(
    synthesized_dimensions: dict[str, PersonDimensionBase],
) -> str:
    """Build a markdown representation of the already-synthesized dimensions.

    Args:
        synthesized_dimensions (`dict[str, PersonDimensionBase]`):
            Mapping from field name to the synthesized dimension model instance.

    Returns:
        `str`:
            A human-readable markdown string describing the synthesized profile
            so far, or a placeholder when nothing has been synthesized yet.
    """
    if not synthesized_dimensions:
        return "No dimensions have been synthesized yet."

    markdown_strs = []
    for dim_instance in synthesized_dimensions.values():
        markdown_strs.append(
            dim_instance.to_markdown(level=0)
        )
    return "\n".join(markdown_strs)


def _strip_base_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove ``last_modified`` and ``operations`` from a synthesized dimension dict.

    Args:
        data (`dict[str, Any]`):
            The raw synthesized dimension data (from structured output metadata).

    Returns:
        `dict[str, Any]`:
            A new dictionary with ``last_modified`` and ``operations`` removed.
    """
    return {
        k: v for k, v in data.items()
        if k not in ("last_modified", "operations")
    }


async def create_profile(
    profile_schema: type[PersonBase],
    persona_seed: str | None = None,
    agent_kwargs: dict[str, Any] | None = None,
    task_template: str | None = None,
    dimension_order: list[str] | list[list[str]] | None = None,
    name: str | None = None,
    trajectory_start: str | None = None,
    trajectory_end: str | None = None,
    use_simplified_schema: bool = True,
) -> PersonBase:
    """Create a person profile by incrementally synthesizing each dimension.

    The function uses an agent to generate dimension content one
    (or a group) at a time in a specified order.

    Args:
        profile_schema (`type[PersonBase]`):
            A subclass of ``PersonBase`` that defines the target profile schema.  
            Dimension fields are discovered automatically from the model fields.
        persona_seed (`str | None`, optional):
            An optional textual description of the persona to guide synthesis.
        agent_kwargs (`dict[str, Any] | None`, optional):
            Keyword arguments passed to the agent constructor.
            If it is not provided, a default agent is created with an OpenAI model (`gpt-4.1`), 
            and a default system prompt.
            If it is provided, any missing required key among ``name``, ``sys_prompt``, ``model``, 
            and ``formatter`` is filled with its default value. 
        task_template (`str | None`, optional):
            The instruction template used for each dimension synthesis call.  It
            must contain ``{persona_seed}`` and ``{current_profile}`` placeholders.
            If it is not provided, the default template is used.
        dimension_order (`list[str] | list[list[str]] | None`, optional):
            It controls the synthesis order and grouping of dimensions.
            A 1-D list of field names means each dimension is synthesized
            individually in the given order.  A 2-D list of field-name groups
            means dimensions in the same inner list are synthesized together
            as a single structured output.  If it is not provided, dimensions are
            synthesized one-by-one in their declaration order.
        name (`str | None`, optional):
            The person's name.  If it is not provided, the agent synthesizes it.
        trajectory_start (`str | None`, optional):
            The trajectory start timestamp (ISO 8601).  It must be provided together
            with `trajectory_end` or both omitted.
        trajectory_end (`str | None`, optional):
            The trajectory end timestamp (ISO 8601).  It must be provided together
            with `trajectory_start` or both omitted.
        use_simplified_schema (`bool`, defaults to `True`):
            If True, it uses simplified dimension schemas for the large language model structured output,
            then convert the result back to the original dimension models. This avoids exposing the internal
            ``TrackedAttribute`` structure to the large language model.

    Returns:
        `PersonBase`:
            A validated instance of provided profile schema with all dimensions and meta
            fields populated.
    """
    if not (isinstance(profile_schema, type) and issubclass(profile_schema, PersonBase)):
        raise TypeError(
            "`profile_schema` must be a subclass of `PersonBase`, but "
            f"{profile_schema!r} is not a subclass of `PersonBase`."
        )

    has_start = trajectory_start is not None
    has_end = trajectory_end is not None
    if has_start != has_end:
        raise ValueError(
            "`trajectory_start` and `trajectory_end` must be both provided or both omitted."
        )

    dim_fields = profile_schema.get_dimension_fields()
    field_to_class = {
        field_name: dim_cls 
        for field_name, dim_cls in dim_fields
    }
    valid_field_names = set(field_to_class.keys())
    
    if dimension_order is not None:
        dimension_groups = _normalize_dimension_order(
            dimension_order, 
            valid_field_names,
        )
    else:
        dimension_groups = [[field_name] for field_name, _ in dim_fields]

    prepared_kwargs = _prepare_agent_kwargs(agent_kwargs)
    agent = SynthesisAgent(**prepared_kwargs)

    if task_template is None:
        task_template = DEFAULT_DIMENSION_TASK_TEMPLATE

    seed_text = (
        persona_seed
        if persona_seed is not None
        else "No specific persona seed is provided."
    )

    # Start to build the profile by incrementally synthesizing each dimension.
    synthesized = {}

    for group in dimension_groups:
        # Build the task instruction.
        current_profile_text = _build_current_profile_text(synthesized)
        task_instruction = task_template.format(
            persona_seed=seed_text,
            current_profile=current_profile_text,
        )

        if len(group) == 1:
            dim_cls = field_to_class[group[0]]
            structured_model = (
                dim_cls.to_simplified_model()
                if use_simplified_schema
                else dim_cls
            )
        else:
            # Dynamically create a grouped pydantic model. 
            # See https://docs.pydantic.dev/2.10/concepts/models/#dynamic-model-creation. 
            grouped_fields = {}
            for field_name in group:
                dim_cls = field_to_class[field_name]
                resolved_cls = (
                    dim_cls.to_simplified_model()
                    if use_simplified_schema
                    else dim_cls
                )
                # Format: <name>=(<type>, <FieldInfo>).
                # Note that only the description is preserved, other metadata are not preserved.
                original_fi = profile_schema.model_fields[field_name]
                field_info = Field(description=original_fi.description)
                grouped_fields[field_name] = (resolved_cls, field_info)
            structured_model = create_model(
                "_TempDimensionGroup", **grouped_fields,
            )

        response_msg = await agent(
            msg=Msg("user", task_instruction, "user"),
            structured_model=structured_model,
        )
        if response_msg.metadata is None:
            raise RuntimeError(
                "The agent failed to generate structured output for "
                f"dimension(s): {group}."
            )
        result_data = response_msg.metadata

        # Extract and validate each dimension in the group.
        if len(group) == 1:
            field_name = group[0]
            dim_data = _strip_base_fields(result_data)
            synthesized[field_name] = field_to_class[field_name].model_validate(
                dim_data,
            )
        else:
            for field_name in group:
                dim_data = result_data.get(field_name, {})
                if isinstance(dim_data, dict):
                    dim_data = _strip_base_fields(dim_data)
                synthesized[field_name] = field_to_class[field_name].model_validate(
                    dim_data,
                )

        # Each synthesis call is independent so the internal memory must be cleared.
        # Independence means that the agent has no knowledge of how the current person profile is obtained.
        await agent.memory.clear()

    # Synthesize the remaining meta fields (name, trajectory range, and side note).
    meta_fields = {}
    if name is None:
        meta_fields["name"] = (
            profile_schema.model_fields["name"].annotation, 
            profile_schema.model_fields["name"],
        )
    if trajectory_start is None:
        meta_fields["trajectory_start"] = (
            profile_schema.model_fields["trajectory_start"].annotation, 
            profile_schema.model_fields["trajectory_start"],
        )
        meta_fields["trajectory_end"] = (
            profile_schema.model_fields["trajectory_end"].annotation, 
            profile_schema.model_fields["trajectory_end"],
        )
    meta_fields["side_note"] = (
        profile_schema.model_fields["side_note"].annotation, 
        profile_schema.model_fields["side_note"],
    )

    TempExtraInfoModel = create_model(
        "_PersonExtraInfo", **meta_fields,
    )

    current_profile_text = _build_current_profile_text(synthesized)
    meta_task = DEFAULT_META_TASK_TEMPLATE.format(
        current_profile=current_profile_text,
    )

    response_msg = await agent(
        msg=Msg("user", meta_task, "user"),
        structured_model=TempExtraInfoModel,
    )
    if response_msg.metadata is None:
        raise RuntimeError(
            "The agent failed to generate structured output for the "
            "person metadata fields (name, trajectory range, and side note)."
        )

    meta_data = response_msg.metadata
    await agent.memory.clear()

    # Assemble and return the final profile.
    profile_data = synthesized
    profile_data["name"] = (
        name
        if name is not None
        else meta_data["name"]
    )
    profile_data["trajectory_start"] = (
        trajectory_start
        if trajectory_start is not None
        else meta_data["trajectory_start"]
    )
    profile_data["trajectory_end"] = (
        trajectory_end
        if trajectory_end is not None
        else meta_data["trajectory_end"]
    )
    profile_data["side_note"] = meta_data["side_note"]

    return profile_schema.model_validate(profile_data)
