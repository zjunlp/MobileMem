"""Builtin dimension models for trajectory synthesis."""
from pydantic import Field
from ._base import PersonDimensionBase, TrackedStr
from .._constants import EMPTY_LIST_STR_REPR
from typing import Literal, ClassVar


class BasicInfo(PersonDimensionBase):
    """Basic personal information dimension.
    
    It contains fundamental demographic information such as gender, age,
    marital status, location, and economic status.
    """
    
    _dimension_description: ClassVar[str] = "Basic personal information dimension."
    _dimension_name: ClassVar[str] = "basic_info"
    _string_fields: ClassVar[list[str]] = [
        "marital_status", 
        "location", 
        "hometown", 
        "economic_status", 
        "description", 
    ]
    _list_fields: ClassVar[list[str]] = []
    
    gender: Literal["male", "female"] = Field(
        description="Person's gender.",
    )
    age: int = Field(
        ge=13,
        le=80,
        description="Person's current age in years. Must be between 13 and 80.",
    )
    marital_status: TrackedStr = Field(
        description=(
            "Current marital status of the person. "
            "Here are some examples: 'single', 'married', 'divorced', 'widowed'."
        ),
    )
    location: TrackedStr = Field(
        description=(
            "Current residential location at city/district level. "
            "Here are some examples: 'San Francisco, CA', 'London, UK', 'Beijing, Haidian District'."
        ),
    )
    hometown: TrackedStr = Field(
        description=(
            "Person's hometown or place of origin at city level. "
            "Here are some examples: 'Chicago, IL', 'Manchester, UK'."
        ),
    )
    economic_status: TrackedStr = Field(
        description=(
            "General economic/financial status description. "
            "Here are some examples: 'good', 'average', 'difficult', 'wealthy'."
        ),
    )


class Personality(PersonDimensionBase):
    """Personality traits and behavioral characteristics dimension.
    
    It captures personality traits, social activity level, and work style
    that influence how the person interacts with others and approaches tasks.
    """
    
    _dimension_description: ClassVar[str] = "Personality"
    _dimension_name: ClassVar[str] = "personality"
    _string_fields: ClassVar[list[str]] = ["social_activity", "work_style", "description"]
    _list_fields: ClassVar[list[str]] = ["traits"]
    
    traits: list[TrackedStr] = Field(
        default_factory=list, 
        description=(
            "List of personality traits. Each trait should be a concise descriptor. "
            "Here is an example: ['analytical', 'detail-oriented', 'collaborative', 'ambitious']."
        ),
    )
    social_activity: TrackedStr = Field(
        description=(
            "Description of social activity level and preferences. "
            "Here are some examples: 'extroverted, active in offline social activities', 'introverted, prefers small gatherings'."
        ),
    )
    work_style: TrackedStr = Field(
        description=(
            "Description of work habits and professional approach. "
            "Here are some examples: 'well-organized and hardworking', 'creative and flexible'."
        ),
    )


class Career(PersonDimensionBase):
    """Career and professional information dimension.
    
    It contains occupation, company, industry, work location, work hours,
    and other job-related information.
    """
    
    _dimension_description: ClassVar[str] = "Career-related Information"
    _dimension_name: ClassVar[str] = "career"
    _string_fields: ClassVar[list[str]] = [
        "occupation", 
        "company", 
        "industry", 
        "work_location",
        "work_hours", 
        "commute_time", 
        "overtime_frequency",
        "description",
    ]
    _list_fields: ClassVar[list[str]] = []
    
    occupation: TrackedStr = Field(
        description=(
            "Current job title or professional role. "
            "Here are some examples: 'Product Manager', 'Software Engineer', 'Data Scientist'."
        ),
    )
    company: TrackedStr = Field(
        description=(
            "Current employer or company name. "
            "Here are some examples: 'Google', 'Microsoft', 'ByteDance'."
        ),
    )
    industry: TrackedStr = Field(
        description=(
            "Industry sector of current employment. "
            "Here are some examples: 'Technology', 'Finance', 'Healthcare'."
        ),
    )
    work_location: TrackedStr = Field(
        description=(
            "Primary work location or office area. "
            "Here are some examples: 'Downtown San Francisco', 'Remote', 'Beijing CBD'."
        ),
    )
    work_hours: TrackedStr = Field(
        description=(
            "Typical daily work hours description. "
            "Here are some examples: 'average 8 hours per day', 'flexible hours, around 10 hours daily'."
        ),
    )
    commute_time: TrackedStr = Field(
        description=(
            "Description of daily commute duration. "
            "Here are some examples: 'relatively long commute, about 1 hour', 'short 15-minute walk'."
        ),
    )
    overtime_frequency: TrackedStr = Field(
        description=(
            "How often the person works overtime. "
            "Here are some examples: 'frequently', 'occasionally', 'rarely', 'never'."
        ),
    )


class Diet(PersonDimensionBase):
    """Dietary preferences and eating habits dimension.
    
    It contains information about the person's dietary preferences, dining style, preferred dining locations,
    and attitudes toward food exploration.
    """
    
    _dimension_description: ClassVar[str] = "Dietary Preferences and Eating Habits"
    _dimension_name: ClassVar[str] = "diet"
    _string_fields: ClassVar[list[str]] = [
        "dining_style", 
        "dining_location",
        "food_exploration", 
        "description",
    ]
    _list_fields: ClassVar[list[str]] = ["preferences"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "dining_location": "Preferred Dining Location",
        "food_exploration": "Attitude Toward Trying New Foods and Cuisines",
    }
    
    preferences: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of preferred cuisine types or food categories. "
            "Here is an example: ['Chinese', 'Italian', 'Japanese', 'Fast Food', 'Vegetarian']."
        ),
    )
    dining_style: TrackedStr = Field(
        description=(
            "General dining habits and preferences. "
            "Here are some examples: 'mainly fast food and casual dining', 'fine dining enthusiast'."
        ),
    )
    dining_location: TrackedStr = Field(
        description=(
            "Preferred dining locations. "
            "Here are some examples: 'near office and commercial areas', 'home cooking preferred'."
        ),
    )
    food_exploration: TrackedStr = Field(
        description=(
            "Attitude toward trying new foods and cuisines. "
            "Here are some examples: 'enjoys trying different types of food', 'prefers familiar cuisines'."
        ),
    )


class Health(PersonDimensionBase):
    """Health awareness and habits dimension.
    
    It contains information about the person's fitness habits, health awareness level, and health-related behaviors
    such as medical checkups and use of health products.
    """
    
    _dimension_description: ClassVar[str] = "Health Awareness and Fitness Habits"
    _dimension_name: ClassVar[str] = "health"
    _string_fields: ClassVar[list[str]] = [
        "health_awareness", 
        "medical_checkup",
        "health_products",
        "description",
    ]
    _list_fields: ClassVar[list[str]] = ["fitness_habits"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "health_awareness": "Level of Health Consciousness and Awareness",
        "medical_checkup": "Whether the Person Regularly Gets Medical Checkups",
        "health_products": "Whether the Person Uses Health Supplements or Products",
    }
    
    fitness_habits: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of regular fitness activities. "
            "Here is an example: ['gym workouts', 'running', 'yoga', 'swimming']."
        ),
    )
    health_awareness: TrackedStr = Field(
        description=(
            "Level of health consciousness and awareness. "
            "Here are some examples: 'high health awareness', 'moderate', 'limited awareness'."
        ),
    )
    medical_checkup: TrackedStr = Field(
        description=(
            "Whether the person regularly gets medical checkups. "
            "Here are some examples: 'Yes', 'No'."
        ),
    )
    health_products: TrackedStr = Field(
        description=(
            "Whether the person uses health supplements or products. "
            "Here are some examples: 'Yes', 'No'."
        ),
    )


class Restaurants(PersonDimensionBase):
    """Restaurant preferences and dining-out habits dimension.
    
    It contains information about the person's preferred restaurant types, dining frequency, review habits,
    and online ordering preferences.
    """
    
    _dimension_description: ClassVar[str] = "Restaurant Preferences and Dining-Out Habits"
    _dimension_name: ClassVar[str] = "restaurants"
    _string_fields: ClassVar[list[str]] = [
        "dining_frequency", 
        "review_habits", 
        "online_ordering", 
        "description",
        "photo_sharing", 
    ]
    _list_fields: ClassVar[list[str]] = ["preferred_types"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "preferred_types": "Preferred Restaurant Types",
        "dining_frequency": "How Often the Person Dines Out",
        "review_habits": "Habits Regarding Restaurant Reviews and Ratings",
        "photo_sharing": "Whether the Person Takes and Shares Food Photos When Dining",
        "online_ordering": "Online Food Ordering Habits and Frequency",
    }
    
    preferred_types: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of preferred restaurant types or categories. "
            "Here is an example: ['Chinese', 'Hot Pot', 'Cafe', 'Japanese', 'Italian']."
        ),
    )
    dining_frequency: TrackedStr = Field(
        description=(
            "How often the person dines out. "
            "Here are some examples: 'frequently dines out', 'occasionally', 'rarely'."
        ),
    )
    review_habits: TrackedStr = Field(
        description=(
            "Habits regarding restaurant reviews and ratings. "
            "Here are some examples: 'occasionally writes reviews', 'active reviewer', 'never reviews'."
        ),
    )
    photo_sharing: TrackedStr = Field(
        description=(
            "Whether the person takes and shares food photos when dining. "
            "Here are some examples: 'Yes', 'No'."
        ),
    )
    online_ordering: TrackedStr = Field(
        description=(
            "Online food ordering habits and frequency. "
            "Here are some examples: 'frequently uses food delivery apps', 'rarely orders online'."
        ),
    )


class Sport(PersonDimensionBase):
    """Sports and exercise habits dimension.
    
    It contains information about the person's sports activities, exercise frequency, schedule,
    and preferred venues.
    """
    
    _dimension_description: ClassVar[str] = "Sports and Exercise Habits"
    _dimension_name: ClassVar[str] = "sport"
    _string_fields: ClassVar[list[str]] = ["frequency", "schedule", "description"]
    _list_fields: ClassVar[list[str]] = ["activities", "venues"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "activities": "Sports and Physical Activities",
        "frequency": "How Often the Person Exercises",
        "schedule": "Typical Exercise Schedule",
        "venues": "Venues where the Person Exercises",
    }

    activities: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of sports or physical activities the person engages in. "
            "Here is an example: ['tennis', 'swimming', 'cycling', 'badminton', 'gym']."
        ),
    )
    frequency: TrackedStr = Field(
        description=(
            "How often the person exercises. "
            "Here are some examples: 'Wednesdays and weekends', 'daily', '3 times a week'."
        ),
    )
    schedule: TrackedStr = Field(
        description=(
            "Typical exercise schedule description. "
            "Here is an example: 'plays tennis on weekends, goes to gym on weekdays'."
        ),
    )
    venues: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of venues where the person exercises. "
            "Here is an example: ['gym', 'tennis court', 'park', 'swimming pool']."
        ),
    )


class Pet(PersonDimensionBase):
    """Pet information dimension.
    
    It contains information about the person's pet information.
    """
    
    _dimension_description: ClassVar[str] = "Pet Information"
    _dimension_name: ClassVar[str] = "pet"
    _string_fields: ClassVar[list[str]] = ["has_pet", "description"]
    _list_fields: ClassVar[list[str]] = []
    _field_display_names: ClassVar[dict[str, str]] = {
        "has_pet": "Whether the Person Currently Owns a Pet",
    }

    has_pet: TrackedStr = Field(
        description=(
            "Whether the person currently owns a pet. "
            "Here are some examples: 'Yes', 'No'."
        ),
    )


class Shopping(PersonDimensionBase):
    """Shopping habits and preferences dimension.
    
    It contains information about the person's shopping preferences, platforms, brand preferences,
    price sensitivity, and promotion usage habits.
    """
    
    _dimension_description: ClassVar[str] = "Shopping Habits and Preferences"
    _dimension_name: ClassVar[str] = "shopping"
    _string_fields: ClassVar[list[str]] = [
        "brand_preference", 
        "price_sensitivity", 
        "promotion_habits", 
        "description", 
    ]
    _list_fields: ClassVar[list[str]] = ["preferences", "platforms"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "platforms": "Preferred Shopping Platforms",
        "brand_preference": "General Brand Preference",
        "price_sensitivity": "Attitude Toward Pricing When Shopping",
        "promotion_habits": "How the Person Uses Promotions and Discounts",
    }

    preferences: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of preferred shopping categories or product types. "
            "Here is an example: ['electronics', 'smart devices', 'health products', 'imported food']."
        ),
    )
    platforms: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of preferred shopping platforms. "
            "Here is an example: ['Amazon', 'eBay', 'local stores']."
        ),
    )
    brand_preference: TrackedStr = Field(
        description=(
            "General brand preference description. "
            "Here are some examples: 'prefers high-end quality brands', 'no brand preference'."
        ),
    )
    price_sensitivity: TrackedStr = Field(
        description=(
            "Attitude toward pricing when shopping. "
            "Here are some examples: 'values cost-effectiveness', 'price-conscious', 'not price-sensitive'."
        ),
    )
    promotion_habits: TrackedStr = Field(
        description=(
            "How the person uses promotions and discounts. "
            "Here are some examples: 'actively uses coupons and deals', 'rarely looks for promotions'."
        ),
    )
    

class Transportation(PersonDimensionBase):
    """Transportation and commuting habits dimension.
    
    It contains information about the person's transportation and commuting habits,
    and public transport usage.
    """
    
    _dimension_description: ClassVar[str] = "Transportation and Commuting Habits"
    _dimension_name: ClassVar[str] = "transportation"
    _string_fields: ClassVar[list[str]] = [
        "commute_method", 
        "commute_time", 
        "commute_peak",
        "long_distance", 
        "public_transport", 
        "description",
    ]
    _list_fields: ClassVar[list[str]] = ["travel_preferences"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "commute_method": "Primary Method of Commuting",
        "commute_time": "Typical Commute Duration",
        "commute_peak": "When Commuting Typically Occurs",
        "long_distance": "Long-Distance Travel Habits",
        "travel_preferences": "Preferred Modes of Long-Distance Transportation",
        "public_transport": "Public Transport Usage Habits",
    }

    commute_method: TrackedStr = Field(
        description=(
            "Primary method of commuting. "
            "Here are some examples: 'driving', 'public transit', 'cycling', 'walking'."
        ),
    )
    commute_time: TrackedStr = Field(
        description=(
            "Typical commute duration. "
            "Here are some examples: 'about 1 hour each way', 'short 15-minute commute'."
        ),
    )
    commute_peak: TrackedStr = Field(
        description=(
            "When commuting typically occurs. "
            "Here are some examples: 'morning and evening rush hours', 'flexible hours'."
        ),
    )
    long_distance: TrackedStr = Field(
        description=(
            "Long-distance travel habits. "
            "Here are some examples: 'inter-city travel during holidays', 'frequent business travel'."
        ),
    )
    travel_preferences: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Preferred modes of long-distance transportation. "
            "Here is an example: ['train', 'flight', 'driving', 'bus']."
        ),
    )
    public_transport: TrackedStr = Field(
        description=(
            "Public transport usage habits. "
            "Here are some examples: 'occasionally uses public transport', 'primary mode of transport'."
        ),
    )


class Car(PersonDimensionBase):
    """Car ownership and usage dimension.
    
    It contains information about car ownership, brand, model, type,
    and usage patterns.
    """
    
    _dimension_description: ClassVar[str] = "Car Ownership and Usage"
    _dimension_name: ClassVar[str] = "car"
    _string_fields: ClassVar[list[str]] = [
        "has_car", 
        "car_brand", 
        "car_model", 
        "car_type", 
        "usage_pattern", 
        "description",
    ]
    _list_fields: ClassVar[list[str]] = []
    _field_display_names: ClassVar[dict[str, str]] = {
        "has_car": "Whether the Person Owns a Car",
        "car_brand": "Brand of the Car",
        "car_model": "Model of the Car",
        "car_type": "Type of the Car",
        "usage_pattern": "Usage Pattern of the Car",
    }
    
    has_car: TrackedStr = Field(
        description=(
            "Whether the person owns a car. "
            "Here are some examples: 'Yes', 'No'."
        ),
    )
    car_brand: TrackedStr = Field(
        description=(
            "Brand of the car if the person owns one. "
            "Here are some examples: 'Tesla', 'Toyota', 'BMW'."
        ),
    )
    car_model: TrackedStr = Field(
        description=(
            "Model of the car if applicable. "
            "Here are some examples: 'Model Y', 'Camry', 'X3'."
        ),
    )
    car_type: TrackedStr = Field(
        description=(
            "Type/category of the car. "
            "Here are some examples: 'EV', 'SUV', 'sedan', 'hybrid'."
        ),
    )
    usage_pattern: TrackedStr = Field(
        description=(
            "How the car is typically used. "
            "Here are some examples: 'mainly for daily commute', 'weekend trips only'. None if no car."
        ),
    )


class LongTravel(PersonDimensionBase):
    """Long-distance travel preferences dimension.
    
    It contains information about the person's travel style, preferred destinations, interests,
    frequency, and transportation preferences for long trips.
    """
    
    _dimension_description: ClassVar[str] = "Long-Distance Travel Preferences"
    _dimension_name: ClassVar[str] = "long_travel"
    _string_fields: ClassVar[list[str]] = [
        "travel_style", 
        "travel_frequency", 
        "travel_transport", 
        "description",
    ]
    _list_fields: ClassVar[list[str]] = ["preferred_destinations", "travel_interests"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "travel_style": "Preferred Style of Traveling",
        "travel_frequency": "How Often the Person Takes Long Trips",
        "travel_transport": "Preferred Transportation for Long-Distance Travel",
        "preferred_destinations": "Types of Preferred Travel Destinations",
        "travel_interests": "Activities or Interests during Travel",
    }

    travel_style: TrackedStr = Field(
        description=(
            "Preferred style of traveling. "
            "Here are some examples: 'independent travel', 'guided tour', 'road trip', 'backpacking'."
        ),
    )
    preferred_destinations: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Types of preferred travel destinations. "
            "Here is an example: ['beaches', 'mountains', 'cities', 'historical sites']."
        ),
    )
    travel_interests: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Activities or interests during travel. "
            "Here is an example: ['food tours', 'photography', 'hiking', 'cultural experiences']."
        ),
    )
    travel_frequency: TrackedStr = Field(
        description=(
            "How often the person takes long trips. "
            "Here are some examples: 'during holidays', 'monthly', 'twice a year'."
        ),
    )
    travel_transport: TrackedStr = Field(
        description=(
            "Preferred transportation for long-distance travel. "
            "Here are some examples: 'driving or train', 'flying', 'mixed modes'."
        ),
    )


class Technology(PersonDimensionBase):
    """Technology interests and usage dimension.
    
    It contains the person's tech interests, focus areas, devices owned,
    and overall tech-savviness level.
    """
    
    _dimension_description: ClassVar[str] = "Technology Interests and Usage"
    _dimension_name: ClassVar[str] = "technology"
    _string_fields: ClassVar[list[str]] = ["tech_savvy_level", "description"]
    _list_fields: ClassVar[list[str]] = ["interests", "focus_areas", "devices"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "interests": "Areas of Technology Interest",
        "focus_areas": "Specific Focus Areas",
        "devices": "Tech Devices Owned",
        "tech_savvy_level": "Overall Tech Proficiency Level",
    }

    interests: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Areas of technology interest. "
            "Here is an example: ['AI', 'blockchain', 'VR', 'mobile apps', 'robotics']."
        ),
    )
    focus_areas: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Specific focus areas within tech interests. "
            "Here is an example: ['cutting-edge research', 'practical applications', 'industry trends']."
        ),
    )
    devices: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Tech devices owned by the person. "
            "Here is an example: ['iPhone', 'MacBook Pro', 'iPad', 'Android phone', 'Windows laptop']."
        ),
    )
    tech_savvy_level: TrackedStr = Field(
        description=(
            "Overall tech proficiency level. "
            "Here are some examples: 'high', 'medium', 'low', 'expert', 'beginner'."
        ),
    )


class Photography(PersonDimensionBase):
    """Photography habits and preferences dimension.
    
    It contains the person's shooting subjects, style, focus, and equipment used.
    """
    
    _dimension_description: ClassVar[str] = "Photography Habits and Preferences"
    _dimension_name: ClassVar[str] = "photography"
    _string_fields: ClassVar[list[str]] = ["style", "focus", "description"]
    _list_fields: ClassVar[list[str]] = ["shooting_subjects", "equipment"]
    _field_display_names: ClassVar[dict[str, str]] = {
        "equipment": "Photography Equipment Used",
    }
    
    shooting_subjects: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Types of subjects the person photographs. "
            "Here is an example: ['portraits', 'landscapes', 'food', 'street', 'wildlife']."
        ),
    )
    style: TrackedStr = Field(
        description=(
            "Photography style preference. "
            "Here are some examples: 'documentary', 'artistic', 'casual', 'professional'."
        ),
    )
    focus: TrackedStr = Field(
        description=(
            "What the person focuses on when taking photos. "
            "Here are some examples: 'capturing real moments', 'aesthetic composition', 'storytelling'."
        ),
    )
    equipment: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Photography equipment used. "
            "Here is an example: ['iPhone', 'DSLR camera', 'drone', 'mirrorless camera']."
        ),
    )


class Entertainment(PersonDimensionBase):
    """Entertainment preferences and activities dimension.
    
    It contains the person's entertainment activities, content preferences, apps used,
    social activities, and offline participation level.
    """
    
    _dimension_description: ClassVar[str] = "Entertainment Preferences and Activities"
    _dimension_name: ClassVar[str] = "entertainment"
    _string_fields: ClassVar[list[str]] = ["offline_participation", "description"]
    _list_fields: ClassVar[list[str]] = [
        "activities", 
        "content_preferences", 
        "apps", 
        "social_activities",
    ]
    _field_display_names: ClassVar[dict[str, str]] = {
        "activities": "General Entertainment Activities",
        "content_preferences": "Types of Content Preferred for Entertainment",
        "apps": "Entertainment Apps Frequently Used",
        "social_activities": "Social/Offline Entertainment Activities",
        "offline_participation": "Level of Offline Activity Participation",
    }
    
    activities: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "General entertainment activities. "
            "Here is an example: ['streaming', 'gaming', 'reading', 'short videos', 'news reading']."
        ),
    )
    content_preferences: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Types of content preferred for entertainment. "
            "Here is an example: ['movies', 'podcasts', 'sports', 'music', 'documentaries']."
        ),
    )
    apps: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Entertainment apps frequently used. "
            "Here is an example: ['Netflix', 'Spotify', 'YouTube', 'TikTok']."
        ),
    )
    social_activities: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Social/offline entertainment activities. "
            "Here is an example: ['parties', 'concerts', 'sports events', 'dining out', 'travel']."
        ),
    )
    offline_participation: TrackedStr = Field(
        description=(
            "Level of offline activity participation. "
            "Here are some examples: 'high', 'moderate', 'low', 'very active'."
        ),
    )


class Finance(PersonDimensionBase):
    """Financial habits and preferences dimension.
    
    It contains the person's investment types, financial tools, awareness level,
    daily operations, risk preference, and activity patterns.
    """
    
    _dimension_description: ClassVar[str] = "Financial Habits and Preferences"
    _dimension_name: ClassVar[str] = "finance"
    _string_fields: ClassVar[list[str]] = [
        "financial_awareness", 
        "risk_preference", 
        "activity_pattern", 
        "description",
    ]
    _list_fields: ClassVar[list[str]] = [
        "investment_types", 
        "financial_tools", 
        "daily_operations", 
    ]

    investment_types: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Types of investments the person makes. "
            "Here is an example: ['stocks', 'bonds', 'crypto', 'mutual funds', 'real estate']."
        ),
    )
    financial_tools: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Financial apps and tools used. "
            "Here is an example: ['banking app', 'investment app', 'budgeting tool', 'tax software']."
        ),
    )
    financial_awareness: TrackedStr = Field(
        description=(
            "Level of financial literacy and awareness. "
            "Here are some examples: 'high', 'moderate', 'limited', 'expert'."
        ),
    )
    daily_operations: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "Common daily financial operations. "
            "Here is an example: ['account management', 'transfers', 'bill payments', 'budgeting']."
        ),
    )
    risk_preference: TrackedStr = Field(
        description=(
            "Investment risk tolerance preference. "
            "Here are some examples: 'conservative', 'moderate', 'aggressive', 'balanced'."
        ),
    )
    activity_pattern: TrackedStr = Field(
        description=(
            "Pattern of financial activity. "
            "Here is an example: 'active on both weekdays and weekends', 'weekly reviews only'."
        ),
    )


class SocialCircle(PersonDimensionBase):
    """Social circle and relationships dimension.
    
    This dimension contains all social connections including family members,
    friends, colleagues, and other relationships. Each connection is stored 
    in the format `'{Role}: {Name}'` (e.g., `'Friend: Bob'`, `'Spouse: Alice'`).
    
    Common role examples:
    - Family: 'Spouse', 'Child', 'Father', 'Mother', 'Sibling', 'Uncle', 'Aunt', 'Cousin'
    - Professional: 'Colleague', 'Boss', 'Mentor', 'Business Partner'
    - Social: 'Friend', 'Neighbor', 'Acquaintance'
    """
    
    _dimension_description: ClassVar[str] = "Social Circle and Relationships"
    _dimension_name: ClassVar[str] = "social_circle"
    _string_fields: ClassVar[list[str]] = []
    _list_fields: ClassVar[list[str]] = ["connections"]
    
    connections: list[TrackedStr] = Field(
        default_factory=list,
        description=(
            "List of social connections in the format `'{Role}: {Name}'`. "
            "Each entry must contain a colon separating the role from the name. "
            "Here is an example: "
            "['Spouse: Alice', 'Friend: Bob', 'Colleague: Charlie', 'Father: David', 'Child: Emma']."
        ),
    )
    
    def validate_instance(self) -> None:
        """Validate that each connection follows the `'{Role}: {Name}'` format."""
        invalid_entries = []
        for i, entry in enumerate(self.connections):
            entry_ = str(entry)
            if ": " not in entry_:
                invalid_entries.append(
                    f"Entry at index {i} ('{entry_}') is invalid. "
                    "It must follow the format `'{Role}: {Name}'`."
                )
            else:
                parts = entry_.split(": ", 1)
                if len(parts) != 2:
                    invalid_entries.append(
                        f"Entry at index {i} ('{entry_}') is invalid. "
                        "It must follow the format `'{Role}: {Name}'`."
                    )
                elif not parts[0].strip() or not parts[1].strip():
                    invalid_entries.append(
                        f"Entry at index {i} ('{entry_}') is invalid. "
                        "Both role and name must be non-empty after splitting by ': '."
                    )

        if invalid_entries:
            raise ValueError(
                "Find invalid connection format(s):\n" + "\n".join(invalid_entries)
            )
    
    def get_connections_by_role(self, role: str) -> list[str]:
        """Get all names for a specific role.
        
        Args:
            role (`str`):
                The role to filter by (case-insensitive).
                
        Returns:
            `list[str]`:
                List of names associated with the given role.
        """
        role_lower = role.lower()
        names = [] 
        for entry in self.connections:
            entry_ = str(entry)
            if entry_.lower().startswith(f"{role_lower}: "):
                name = entry_.split(": ", 1)[1] 
                names.append(name)
        return names
    
    def get_all_roles(self) -> list[str]:
        """Get all unique roles in the connections list.
        
        Returns:
            `list[str]`:
                List of unique roles.
        """
        roles = set()
        for entry in self.connections:
            entry_ = str(entry)
            if ": " in entry_:
                roles.add(entry_.split(": ", 1)[0])
        return sorted(roles)
    
    def to_markdown(self, detailed: bool = False, level: int = 0) -> str:
        indent = "\t" * level
        markdown_strs = [
            f"{indent}- {self._dimension_description} (Dimension Name: `{self._dimension_name}`):",
        ]
        
        if self.connections:
            markdown_strs.append(f"{indent}\t- Connections (Attribute Name: `connections (list of strings, format: '{{Role}}: {{Name}}')`):")
            markdown_strs.extend([f"{indent}\t\t- {entry} (Mentioned: {entry.has_connections})" for entry in self.connections])
        else:
            markdown_strs.append(f"{indent}\t- Connections (Attribute Name: `connections (list of strings, format: '{{Role}}: {{Name}}')`): {EMPTY_LIST_STR_REPR}")
        
        markdown_strs.append(f"{indent}\t- Last Modified: {self.last_modified}")
        
        if detailed:
            markdown_strs.extend(self.format_operations_markdown(level + 1))
        return "\n".join(markdown_strs)