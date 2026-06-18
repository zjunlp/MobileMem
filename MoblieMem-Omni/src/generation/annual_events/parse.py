"""Annual-events per-record LLM call + parse / validate."""
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Tuple

import config
from backends.llm import (
    calculate_cumulative_cost,
    llm_request,
)
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger("generation.annual_events")


# Retry configuration (centralized in config)
RETRY_TIMES = config.RETRY_TIMES
WAIT_TIME_LOWER = config.WAIT_TIME_LOWER
WAIT_TIME_UPPER = config.WAIT_TIME_UPPER

# Max tolerated number of consecutive empty/failed results from a single LLM call loop
MAX_EMPTY_RETRIES = 5
# Max events requested per single LLM call (to avoid output exceeding the model's max_output_tokens)
MAX_EVENTS_PER_CALL = 15


def load_prompt(prompt_path: str) -> str:
    """Load prompt file from specified path"""
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise FileNotFoundError(f"Failed to load prompt file {prompt_path}: {e}:{traceback.format_exc()}")


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_random_exponential(min=WAIT_TIME_LOWER, max=WAIT_TIME_UPPER),
    stop=stop_after_attempt(RETRY_TIMES),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def generate_events_with_llm(persona_record: Dict, prompt: str, max_events: int = 100) -> Tuple[List[Dict], Dict]:
    """
    Generate annual events for a persona using LLM

    Args:
        persona_record: Complete persona record from stage3 (with Basic_Profile, Init_State and Important_Dates)
        prompt: The system prompt to use
        max_events: Maximum number of events to generate (default: 100)

    Returns:
        Tuple of (events_list, cost_info)
    """
    api_key = config.OPENAI_API_KEY

    if not api_key:
        print("[ERROR] OpenAI API key not set in environment variables")
        raise ValueError("OpenAI API key is required")

    try:
        persona_uuid = persona_record.get('uuid', 'unknown')
        print(f"[INFO] Generating annual events for persona {persona_uuid}...")

        # Extract background, initial state and important dates
        basic_profile = persona_record.get('Basic_Profile', {})
        init_state = persona_record.get('Init_State', {})
        important_dates = persona_record.get('Important_Dates', {})

        # Format the system prompt
        system_prompt = prompt

        # Create user content with persona information including important dates
        user_content = f"""
Please generate annual events for this persona in 2025.

Persona Background:
- Name: {basic_profile.get('name', 'Unknown')}
- Gender: {basic_profile.get('gender', 'Unknown')}
- Birth Date: {basic_profile.get('birth_date', 'Unknown')}
- Nationality: {basic_profile.get('nationality', 'Unknown')}
- Personality Traits: {basic_profile.get('personality_traits', 'Unknown')}
- Life Experiences: {basic_profile.get('life_experiences', 'Unknown')}

Initial State (as of 2025-01-01):
- Description: {init_state.get('description', 'Unknown')}
- Education: {init_state.get('education', 'Unknown')}
- Location: {init_state.get('location', 'Unknown')}
- Career: {init_state.get('career', 'Unknown')}
- Preferences: {json.dumps(init_state.get('preferences', {}), ensure_ascii=False, indent=2)}
- Social Relationships: {json.dumps(init_state.get('social_relationships', {}), ensure_ascii=False, indent=2)}
- Health: {init_state.get('health', 'Unknown')}
- Emotion: {init_state.get('emotion', 'Unknown')}
- Finance: {init_state.get('finance', 'Unknown')}

Important Dates for this persona in 2025:
- Festivals: {json.dumps(important_dates.get('festivals', []), ensure_ascii=False, indent=2)}
- Memorial Dates: {json.dumps(important_dates.get('memorial_dates', []), ensure_ascii=False, indent=2)}
- Event Milestones: {json.dumps(important_dates.get('event_milestones', []), ensure_ascii=False, indent=2)}

Please generate at least {max_events} realistic events for the year 2025, starting from this initial state and incorporating the important dates where relevant.
Each event should represent a plausible situation where the persona might naturally seek guidance or support from a chatbot.

IMPORTANT: For EVERY event, you MUST include ONE of the following info fields based on the additional_info type:
- If additional_info contains 'ticket': include complete ticket_info with all required fields
- If additional_info contains 'food': include complete food_info with all required fields  
- If additional_info contains 'money': include complete money_info with all required fields
- If additional_info contains 'friend': include complete friend_info with all required fields
- If additional_info contains 'wechat': include complete wechat_info with all required fields

Do NOT generate events that are missing their corresponding info fields!
"""

        print(f"[INFO] Sending request for persona {persona_uuid}")
        response, cost_info = llm_request(
            system_prompt,
            user_content,
            return_parsed_json=True,
            extract_json=True,
            json_markers=[]
        )

        cost_info = calculate_cumulative_cost(None, cost_info)

        print(f"[INFO] Successfully generated annual events for persona {persona_uuid}")

        if cost_info and 'cumulative' in cost_info:
            cum_cost = cost_info['cumulative']
            print(
                f"[INFO] Token usage - Input: {cum_cost.get('input_tokens', 'N/A')}, "
                f"Output: {cum_cost.get('output_tokens', 'N/A')}, "
                f"Cost: ${cum_cost.get('total_cost_usd', 'N/A')}"
            )

        # Extract events from response
        events_list = extract_events_from_response(response)

        if not events_list:
            raise ValueError(f"Failed to extract events from response for persona {persona_uuid}")

        # Validate and normalize events
        normalized_events = validate_and_normalize_events(events_list, persona_uuid)
        
        # Limit to max_events if specified
        if max_events > 0 and len(normalized_events) > max_events:
            print(f"[INFO] Limiting events from {len(normalized_events)} to {max_events} for persona {persona_uuid}")
            normalized_events = normalized_events[:max_events]

        return normalized_events, cost_info

    except Exception as e:
        print(f"[ERROR] Annual events generation failed for persona {persona_record.get('uuid', 'unknown')}: {e}")
        print("[ERROR] Full traceback:")
        traceback.print_exc()
        raise


def extract_events_from_response(parsed_data) -> List[Dict]:
    """
    Extract JSON array from LLM response

    Handles both direct JSON array and JSON wrapped in markdown code blocks

    Args:
        parsed_data: Parsed data from LLM

    Returns:
        List of event dictionaries
    """
    try:
        # Handle different response formats
        if isinstance(parsed_data, dict):
            # Check if response has "Events" key
            if 'Events' in parsed_data:
                events_list = parsed_data['Events']
            else:
                # Try to find any array in the response
                for key, value in parsed_data.items():
                    if isinstance(value, list):
                        events_list = value
                        break
                else:
                    # If no array found, return empty list
                    print("[WARNING] No array found in JSON response")
                    return []
        elif isinstance(parsed_data, list):
            events_list = parsed_data
        else:
            print(f"[WARNING] Unexpected JSON format: {type(parsed_data)}")
            return []

        return events_list

    except json.JSONDecodeError as e:
        print(f"[WARNING] Failed to parse JSON from response: {e}")
        # Try to extract JSON using regex as fallback
        try:
            import re
            json_pattern = r'(\[[\s\S]*\])'
            match = re.search(json_pattern, str(parsed_data))
            if match:
                potential_json = match.group(1)
                events_list = json.loads(potential_json)
                return events_list
        except:  # noqa: E722
            pass
        return []
    except Exception as e:
        print(f"[WARNING] Error extracting events from response: {e}")
        return []


def validate_and_normalize_events(events_list: List[Dict], persona_uuid: int) -> List[Dict]:
    """
    Validate and normalize events based on stage4 requirements

    Args:
        events_list: List of event dictionaries to validate
        persona_uuid: UUID of the persona for error reporting

    Returns:
        List of validated and normalized events
    """
    if not isinstance(events_list, list):
        print(f"[ERROR] Persona {persona_uuid}: Events should be a list, got {type(events_list)}")
        return []

    if len(events_list) < 100:
        print(f"[WARNING] Persona {persona_uuid}: Only {len(events_list)} events generated, expected at least 100")

    required_fields = ['event_id', 'event_name', 'event_start_time', 'event_end_time',
                       'duration_type', 'participants', 'description', 'importance', 'additional_info']

    normalized_events = []

    for i, event in enumerate(events_list):
        # Check for missing required fields
        missing_fields = [field for field in required_fields if field not in event]
        if missing_fields:
            print(f"[WARNING] Persona {persona_uuid}: Event {i} missing fields: {missing_fields}, skipping")
            continue

        # Validate and fix event_id if needed
        try:
            event_id = int(event['event_id'])
            if event_id != i:
                print(
                    f"[WARNING] Persona {persona_uuid}: Event {i} has mismatched event_id {event_id}, correcting to {i}")
                event['event_id'] = i
        except (ValueError, TypeError):
            print(f"[WARNING] Persona {persona_uuid}: Event {i} has invalid event_id, setting to {i}")
            event['event_id'] = i

        # Validate date formats
        try:
            start_time = datetime.strptime(event['event_start_time'], '%Y-%m-%d %H:%M:%S')
            end_time = datetime.strptime(event['event_end_time'], '%Y-%m-%d %H:%M:%S')

            if end_time <= start_time:
                print(f"[WARNING] Persona {persona_uuid}: Event {i} end_time must be later than start_time, adjusting")
                # Add 1 hour to end_time as default
                event['event_end_time'] = (start_time.replace(hour=start_time.hour + 1)).strftime('%Y-%m-%d %H:%M:%S')

            # Ensure dates are in 2025
            if start_time.year != 2025 or end_time.year != 2025:
                print(
                    f"[WARNING] Persona {persona_uuid}: Event {i} dates should be in 2025, found {start_time.year}-{end_time.year}")
        except ValueError as e:
            print(f"[WARNING] Persona {persona_uuid}: Event {i} has invalid date format: {e}")
            continue

        # Normalize duration_type to lowercase and validate
        duration_type = event['duration_type'].lower()
        if duration_type not in ['short-term', 'mid-term', 'long-term']:
            print(
                f"[WARNING] Persona {persona_uuid}: Event {i} has invalid duration_type '{event['duration_type']}', defaulting to 'short-term'")
            event['duration_type'] = 'short-term'
        else:
            event['duration_type'] = duration_type

        # Ensure participants is a list and contains only 0-2 people
        if not isinstance(event['participants'], list):
            print(f"[WARNING] Persona {persona_uuid}: Event {i} participants is not a list, converting")
            if isinstance(event['participants'], str):
                # Split by comma if it's a string
                event['participants'] = [p.strip() for p in event['participants'].split(',') if p.strip()]
            else:
                event['participants'] = []

        # Validate participants count
        if len(event['participants']) > 2:
            print(
                f"[WARNING] Persona {persona_uuid}: Event {i} has {len(event['participants'])} participants, limiting to 2")
            event['participants'] = event['participants'][:2]

        # Validate description - check if it's in first person
        description = event['description']
        first_person_indicators = [" I ", " my ", " me ", " I'm ", " I've ", " I'll "]
        if not any(indicator.lower() in description.lower() for indicator in first_person_indicators):
            print(f"[WARNING] Persona {persona_uuid}: Event {i} description may not be in first person perspective")

        # Normalize importance to lowercase and validate
        importance = event['importance'].lower()
        if importance not in ['high', 'medium', 'low']:
            print(
                f"[WARNING] Persona {persona_uuid}: Event {i} has invalid importance '{event['importance']}', defaulting to 'medium'")
            event['importance'] = 'medium'
        else:
            event['importance'] = importance
        
        # Validate additional_info
        additional_info = event.get('additional_info', [])
        if not isinstance(additional_info, list):
            print(f"[WARNING] Persona {persona_uuid}: Event {i} additional_info is not a list, converting")
            event['additional_info'] = [additional_info] if additional_info else []
        elif len(additional_info) == 0:
            print(f"[WARNING] Persona {persona_uuid}: Event {i} has empty additional_info")
        elif len(additional_info) > 1:
            print(f"[WARNING] Persona {persona_uuid}: Event {i} has multiple additional_info items, keeping only first")
            event['additional_info'] = [additional_info[0]]
        
        # Validate additional_info values
        valid_types = ['food', 'friend', 'money', 'ticket', 'wechat']
        if additional_info and additional_info[0] not in valid_types:
            print(f"[WARNING] Persona {persona_uuid}: Event {i} has invalid additional_info '{additional_info[0]}', should be one of {valid_types}")
        
        # Validate corresponding info fields based on additional_info
        if additional_info:
            info_type = additional_info[0]
            
            if info_type == 'ticket':
                ticket_info = event.get('ticket_info', {})
                if not ticket_info:
                    print(f"[WARNING] Persona {persona_uuid}: Event {i} has 'ticket' in additional_info but missing ticket_info, removing additional_info")
                    event['additional_info'] = []
                else:
                    info_required = ['departure_station', 'arrival_station', 'departure_time',
                                     'travel_date', 'train_number', 'seat_type',
                                     'seat_number', 'price', 'passenger_name']
                    info_missing = [field for field in info_required if field not in ticket_info]
                    if info_missing:
                        print(f"[WARNING] Persona {persona_uuid}: Event {i} ticket_info missing fields: {info_missing}, removing additional_info")
                        event['additional_info'] = []
                        event.pop('ticket_info', None)
            
            elif info_type == 'food':
                food_info = event.get('food_info', {})
                if not food_info:
                    print(f"[WARNING] Persona {persona_uuid}: Event {i} has 'food' in additional_info but missing food_info, removing additional_info")
                    event['additional_info'] = []
                else:
                    info_required = ['delivery_time', 'delivery_address', 'rider_name', 
                                     'order_number', 'order_time', 'payment_method']
                    info_missing = [field for field in info_required if field not in food_info]
                    if info_missing:
                        print(f"[WARNING] Persona {persona_uuid}: Event {i} food_info missing fields: {info_missing}, removing additional_info")
                        event['additional_info'] = []
                        event.pop('food_info', None)
            
            elif info_type == 'money':
                money_info = event.get('money_info', {})
                if not money_info:
                    print(f"[WARNING] Persona {persona_uuid}: Event {i} has 'money' in additional_info but missing money_info, removing additional_info")
                    event['additional_info'] = []
                else:
                    info_required = ['recipient_name', 'amount', 'transfer_time', 'receive_time',
                                     'status', 'description', 'payment_method', 'transaction_id']
                    info_missing = [field for field in info_required if field not in money_info]
                    if info_missing:
                        print(f"[WARNING] Persona {persona_uuid}: Event {i} money_info missing fields: {info_missing}, removing additional_info")
                        event['additional_info'] = []
                        event.pop('money_info', None)
            
            elif info_type == 'friend':
                friend_info = event.get('friend_info', {})
                if not friend_info:
                    print(f"[WARNING] Persona {persona_uuid}: Event {i} has 'friend' in additional_info but missing friend_info, removing additional_info")
                    event['additional_info'] = []
                else:
                    info_required = ['post_text', 'post_time', 'likes', 'comments']
                    info_missing = [field for field in info_required if field not in friend_info]
                    if info_missing:
                        print(f"[WARNING] Persona {persona_uuid}: Event {i} friend_info missing fields: {info_missing}, removing additional_info")
                        event['additional_info'] = []
                        event.pop('friend_info', None)
            
            elif info_type == 'wechat':
                wechat_info = event.get('wechat_info', {})
                if not wechat_info:
                    print(f"[WARNING] Persona {persona_uuid}: Event {i} has 'wechat' in additional_info but missing wechat_info, removing additional_info")
                    event['additional_info'] = []
                else:
                    info_required = ['chat_partner', 'messages']
                    info_missing = [field for field in info_required if field not in wechat_info]
                    if info_missing:
                        print(f"[WARNING] Persona {persona_uuid}: Event {i} wechat_info missing fields: {info_missing}, removing additional_info")
                        event['additional_info'] = []
                        event.pop('wechat_info', None)

        normalized_events.append(event)

    # Sort events by start time and renumber event_id
    try:
        normalized_events.sort(key=lambda x: datetime.strptime(x['event_start_time'], '%Y-%m-%d %H:%M:%S'))
        for i, event in enumerate(normalized_events):
            event['event_id'] = i
    except Exception as e:
        print(f"[WARNING] Persona {persona_uuid}: Could not sort events by time: {e}")

    # Calculate duration type distribution
    duration_counts = {
        'short-term': 0,
        'mid-term': 0,
        'long-term': 0
    }

    for event in normalized_events:
        duration_counts[event['duration_type']] += 1

    total_events = len(normalized_events)
    if total_events > 0:
        print(f"[INFO] Persona {persona_uuid}: Duration distribution - "
              f"Short-term: {duration_counts['short-term']} ({duration_counts['short-term'] / total_events * 100:.1f}%), "
              f"Mid-term: {duration_counts['mid-term']} ({duration_counts['mid-term'] / total_events * 100:.1f}%), "
              f"Long-term: {duration_counts['long-term']} ({duration_counts['long-term'] / total_events * 100:.1f}%)")

    return normalized_events


def process_single_persona(persona_record: Dict, prompt: str, max_events: int = 100) -> Dict:
    """Process single persona to generate annual events
    
    Args:
        persona_record: Complete persona record from stage3
        prompt: The system prompt to use
        max_events: Maximum number of events to generate per persona
        
    Returns:
        Output record with Events
    """
    try:
        # Generate annual events using LLM (includes validation)
        Events, cost_info = generate_events_with_llm(persona_record, prompt, max_events)

        # Create output record with UUID and Events
        output_record = persona_record.copy()
        output_record["Events"] = Events

        return output_record

    except Exception as e:
        print(f"[ERROR] Failed to process persona {persona_record.get('uuid', 0)}: {e}")
        raise


# Name strategy (Social-Graph driven, with legacy word-pool fallback)
