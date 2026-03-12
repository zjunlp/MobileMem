"""Custom person profile schemas for the profile-schema ablation study.

This module defines two reduced-dimension profile schemas to study the impact
of profile schema complexity on trajectory diversity:

- ``PersonMedium``: 8 dimensions (from the full 17 dimensions).
- ``PersonCompact``: 6 dimensions (from the full 17 dimensions).

The full 17-dimension schema is available in ``keme.models.persona._builtin_person.Person``.

Dimension Selection Strategy
----------------------------
Dimensions are selected to maximize life-domain coverage under the count
constraint. The 17 builtin dimensions fall into several overlapping clusters:

    ============  ====================================================
    Life Domain   Builtin Dimensions
    ============  ====================================================
    Identity      BasicInfo
    Character     Personality
    Work          Career
    Food          Diet, Restaurants  (overlap)
    Wellness      Health, Sport  (overlap)
    Consumption   Shopping
    Mobility      Transportation, Car, LongTravel  (overlap)
    Tech          Technology
    Hobbies       Photography, Entertainment  (overlap)
    Finance       Finance
    Relationships SocialCircle
    Animals       Pet  (narrow)
    ============  ====================================================

When a cluster has multiple dimensions, we keep the broader one (e.g. Health
over Sport, Entertainment over Photography, Diet over Restaurants).  When
cutting from 8 to 6, we drop the two domains (Food, Finance) whose removal
least affects overall trajectory diversity.
"""

from pydantic import Field
from keme.models.persona import PersonBase
from keme.models import Person 
from keme.models.persona import (
    BasicInfo,
    Personality,
    Career,
    Diet,
    Health,
    Entertainment,
    Finance,
    SocialCircle,
)


class PersonCompact(PersonBase):
    """A compact person profile schema with 6 dimensions.

    It covers 6 essential life domains: Identity, Character, Work,
    Wellness, Leisure, and Relationships.
    """

    basic_info: BasicInfo = Field(
        description="Basic demographic information dimension.",
    )
    personality: Personality = Field(
        description="Personality traits and behavioral characteristics dimension.",
    )
    career: Career = Field(
        description="Professional and work-related information dimension.",
    )
    health: Health = Field(
        description="Health awareness and fitness habits dimension.",
    )
    entertainment: Entertainment = Field(
        description="Entertainment preferences and activities dimension.",
    )
    social_circle: SocialCircle = Field(
        description="Social connections and relationships dimension.",
    )


class PersonMedium(PersonBase):
    """A medium-complexity person profile schema with 8 dimensions.

    It covers 8 distinct life domains: Identity, Character, Work, Food,
    Wellness, Leisure, Finance, and Relationships.
    """

    basic_info: BasicInfo = Field(
        description="Basic demographic information dimension.",
    )
    personality: Personality = Field(
        description="Personality traits and behavioral characteristics dimension.",
    )
    career: Career = Field(
        description="Professional and work-related information dimension.",
    )
    diet: Diet = Field(
        description="Dietary preferences and eating habits dimension.",
    )
    health: Health = Field(
        description="Health awareness and fitness habits dimension.",
    )
    entertainment: Entertainment = Field(
        description="Entertainment preferences and activities dimension.",
    )
    finance: Finance = Field(
        description="Financial habits and preferences dimension.",
    )
    social_circle: SocialCircle = Field(
        description="Social connections and relationships dimension.",
    )


class PersonFull(Person):
    """The full 17-dimension person profile schema."""
    ... 