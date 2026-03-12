from pydantic import Field
from ._base import PersonBase
from ._builtin_dimensions import (
    BasicInfo,
    Personality,
    Career,
    Diet,
    Health,
    Restaurants,
    Sport,
    Pet,
    Shopping,
    Transportation,
    Car,
    LongTravel,
    Technology,
    Photography,
    Entertainment,
    Finance,
    SocialCircle,
)


class Person(PersonBase): 
    """The default person profile schema for trajectory synthesis.
    
    This model is used to represent the user's global identity and context.
    It is the root node of the persona hierarchy and contains all builtin dimensions.
    """

    # Dimension models
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
    restaurants: Restaurants = Field(
        description="Restaurant preferences and dining-out habits dimension.",
    )
    sport: Sport = Field(
        description="Sports and exercise habits dimension.",
    )
    pet: Pet = Field(
        description="Pet ownership information dimension.",
    )
    shopping: Shopping = Field(
        description="Shopping habits and preferences dimension.",
    )
    transportation: Transportation = Field(
        description="Commuting and transportation habits dimension.",
    )
    car: Car = Field(
        description="Car ownership and usage dimension.",
    )
    long_travel: LongTravel = Field(
        description="Long-distance travel preferences dimension.",
    )
    technology: Technology = Field(
        description="Technology interests and usage dimension.",
    )
    photography: Photography = Field(
        description="Photography habits and preferences dimension.",
    )
    entertainment: Entertainment = Field(
        description="Entertainment preferences and activities dimension.",
    )
    finance: Finance = Field(
        description="Financial habits and preferences dimension.",
    )
    social_circle: SocialCircle = Field(
        description="Social connections and relationships dimension (including family, friends, colleagues).",
    )    