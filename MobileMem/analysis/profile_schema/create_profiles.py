"""Create person profiles for the profile-schema ablation study.

For each sampled persona seed, a full 17-dimension profile is synthesized
via the LLM-based ``create_profile`` function.  The 8-dim and 6-dim profiles
are then derived from the full profile (no extra LLM calls needed).
"""

import os
import json
import random
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from custom_profile_schema import PersonFull, PersonMedium, PersonCompact
from MobileMem.keme.data import create_profile
from agentscope.model import OpenAIChatModel
from agentscope.formatter import OpenAIChatFormatter


_SCRIPT_DIR = Path(__file__).resolve().parent

MODEL_NAME = "gpt-4.1"
AGENT_NAME = "profile_creation_agent"

RANDOM_SEED = 42
NUM_SAMPLES = 3
SEED_PROFILES_PATH = str(_SCRIPT_DIR / "data" / "stage1_3_preferences.jsonl")
OUTPUT_DIR = str(_SCRIPT_DIR / "output" / "profiles")

# Trajectory time range for random generation
TRAJECTORY_YEAR_RANGE = (2024, 2025)
TRAJECTORY_DURATION_DAYS_RANGE = (30, 180)

DERIVED_SCHEMAS = [PersonMedium, PersonCompact]


def load_seed_profiles(path: str) -> list[dict]:
    """Load seed profiles from a JSONL file."""
    profiles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            profiles.append(json.loads(line))
    return profiles


def build_agent_kwargs() -> dict:
    """Build agent keyword arguments from constants and environment variables."""
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_API_BASE")
    client_args = {"base_url": base_url} if base_url else None
    return {
        "name": AGENT_NAME,
        "model": OpenAIChatModel(
            model_name=MODEL_NAME,
            api_key=api_key,
            client_args=client_args,
        ),
        "formatter": OpenAIChatFormatter(),
    }


def generate_random_trajectory_times() -> tuple[str, str]:
    """Generate a random (start, end) trajectory time pair in ISO 8601 format."""
    start_year = random.randint(*TRAJECTORY_YEAR_RANGE)
    start = datetime(
        start_year,
        random.randint(1, 12),
        random.randint(1, 28),
        random.randint(6, 22),
        random.randint(0, 59),
        0,
    )
    end = start + timedelta(days=random.randint(*TRAJECTORY_DURATION_DAYS_RANGE))
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def derive_profile(full_profile, target_schema):
    """Derive a reduced-dimension profile by extracting a subset of dimensions
    from the full profile.  No LLM call is needed because the reduced schemas
    are strict subsets of the full schema.
    """
    kwargs = {
        "name": full_profile.name,
        "trajectory_start": full_profile.trajectory_start,
        "trajectory_end": full_profile.trajectory_end,
        "side_note": full_profile.side_note,
    }
    for field_name, _ in target_schema.get_dimension_fields():
        kwargs[field_name] = getattr(full_profile, field_name)
    return target_schema(**kwargs)


def save_profile(
    profile,
    seed_index: int,
    output_dir: str,
) -> str:
    """Serialize a profile to JSON and write it to disk.

    It returns the path of the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)

    profile_type = type(profile).__name__
    data = profile.model_dump(mode="json")
    data["profile_type"] = profile_type

    safe_name = profile.name.replace(" ", "_")
    filename = f"seed{seed_index}_{safe_name}_{profile_type}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"  Saved: {filepath}")
    return filepath


async def main():
    random.seed(RANDOM_SEED)

    # Load and sample seed profiles
    all_profiles = load_seed_profiles(SEED_PROFILES_PATH)
    sampled = random.sample(all_profiles, min(NUM_SAMPLES, len(all_profiles)))

    agent_kwargs = build_agent_kwargs()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Sampled {len(sampled)} seed profiles from {len(all_profiles)} total")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 60)

    # Generate a single trajectory time pair shared by all seeds
    traj_start, traj_end = generate_random_trajectory_times()
    print(f"Shared trajectory: {traj_start} -> {traj_end}")

    for i, seed_profile in enumerate(sampled):
        persona_seed = seed_profile["metadata"]["persona_seed"]
        name = seed_profile["profile"]["fixed"]["basic_info"]["name"]

        print(f"\n[{i + 1}/{len(sampled)}] Seed: {name}")
        print(f"  Persona: {persona_seed}")

        # Step 1: Synthesize the full profile (17 dimensions) via LLM
        print("  Creating PersonFull (17 dimensions)...")
        full_profile = await create_profile(
            profile_schema=PersonFull,
            persona_seed=persona_seed,
            agent_kwargs=agent_kwargs,
            name=name,
            trajectory_start=traj_start,
            trajectory_end=traj_end,
            use_simplified_schema=True,
        )
        save_profile(full_profile, i, OUTPUT_DIR)

        # Step 2: Derive reduced profiles from the full profile
        for schema_cls in DERIVED_SCHEMAS:
            n_dims = len(schema_cls.get_dimension_fields())
            print(f"  Deriving {schema_cls.__name__} ({n_dims} dimensions)...")
            derived = derive_profile(full_profile, schema_cls)
            save_profile(derived, i, OUTPUT_DIR)

    print("\n" + "=" * 60)
    print(f"Done. {len(sampled) * 3} profiles saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
