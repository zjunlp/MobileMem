"""Annual-events generator (Life / Timeline AnnualEvents): parallel runner + entry.

Holds the thread-safe ``_Stage4Runner`` (iterative top-up via the LLM with a
Social-Graph-driven name strategy), the ``AnnualEventsGenerator`` and the
``generate_annual_events`` entry. Per-record parse/validate lives in ``.parse``; the name
strategy + prompt building in ``.names``.
"""
import logging
import os
import random
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from backends.llm import get_text_llm_model, set_log_context
from infra.base_generator import Generator

from .parse import (
    MAX_EMPTY_RETRIES,
    MAX_EVENTS_PER_CALL,
    load_prompt,
    process_single_persona,
)
from .names import (
    _apply_event_name_strategy,
    _build_event_name_strategy,
    _build_incremental_prompt,
    _call_llm_for_events,
    _merge_and_sort_events,
)

logger = logging.getLogger("generation.annual_events")


# Default number of parallel workers
DEFAULT_WORKERS = 3


class _Stage4Runner:
    """
    Thread-safe parallel Stage 4 runner.

    Core mechanism:
    - self.records: Dict[uuid -> record], the current state of all personas
    - self.lock: a thread lock protecting records and file writes
    - after each LLM call: acquire lock -> update records -> save file -> release lock
    """

    def __init__(self, system_prompt: str, system_prompt_cn: str, max_events: int,
                 ordered_uuids: list, existing: Dict,
                 save_callback=None):
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self.system_prompt = system_prompt
        self.system_prompt_cn = system_prompt_cn
        self.max_events = max_events
        self.ordered_uuids = ordered_uuids
        self.save_callback = save_callback
        self.lock = threading.Lock()

        # Initialization: existing checkpoint data
        self.records = {}
        if existing:
            for uid, record in existing.items():
                self.records[uid] = record

    def _get_ordered_records(self) -> List[Dict]:
        """Return all existing records as a list, in the original order."""
        return [self.records[uid] for uid in self.ordered_uuids
                if uid in self.records]

    def _save_checkpoint(self):
        """Save all current records. Must be called while holding self.lock."""
        if self.save_callback:
            records_list = self._get_ordered_records()
            self.save_callback(records_list)

    def _process_persona(self, persona: Dict):
        """
        Process a single persona: call the LLM repeatedly until enough events are collected.
        Runs inside the thread pool; saves a checkpoint via the lock after each LLM call.
        """
        uid = persona.get('uuid')
        set_log_context(uuid=uid, stage="stage4_events")

        # The actual target event count per uuid = a random value in [0.8*max_events, max_events]
        # Seeded by uuid so the target stays consistent across checkpoint/resume
        _rng = random.Random(uid * 7919 + self.max_events)
        min_events = max(1, int(self.max_events * 0.8))
        persona_max = _rng.randint(min_events, self.max_events)

        # Select the prompt based on nationality
        nationality = persona.get('Basic_Profile', {}).get('nationality', '')
        is_chinese = '中国' in nationality or 'China' in nationality or 'Chinese' in nationality
        active_prompt = self.system_prompt_cn if is_chinese else self.system_prompt
        active_model = get_text_llm_model(is_chinese)

        # Read the currently existing events
        with self.lock:
            existing_record = self.records.get(uid, {})
            current_events = list(existing_record.get('Events', []))

        n_start = len(current_events)
        if n_start >= persona_max:
            print(f"  [uid={uid}] Target={persona_max} events (from max_events={self.max_events}), "
                  f"already have {n_start}, skip")
            return

        print(f"  [uid={uid}] Target={persona_max} events "
              f"(randomized from max_events={self.max_events})")

        empty_count = 0
        call_count = 0

        while len(current_events) < persona_max:
            remaining = persona_max - len(current_events)
            events_to_request = min(remaining, MAX_EVENTS_PER_CALL)
            call_count += 1

            print(f"  [uid={uid}] Round {call_count}: "
                  f"{len(current_events)}/{persona_max}, "
                  f"requesting {events_to_request} (need {remaining} total)")

            # Build the prompt and call the LLM (this step needs no lock and can run in parallel)
            name_strategy = _build_event_name_strategy(persona, current_events, is_chinese)
            user_content = _build_incremental_prompt(
                persona, current_events, events_to_request,
                is_chinese=is_chinese,
                name_strategy=name_strategy)

            try:
                new_events = _call_llm_for_events(
                    active_prompt, user_content, uid, model=active_model)
            except Exception as e:
                # A single failed LLM call should not kill the whole persona's loop
                empty_count += 1
                print(f"  [uid={uid}] Round {call_count}: LLM call FAILED: {e} "
                      f"({empty_count}/{MAX_EMPTY_RETRIES})")
                if empty_count >= MAX_EMPTY_RETRIES:
                    print(f"  [uid={uid}] ABORT: {MAX_EMPTY_RETRIES} "
                          f"consecutive failures/empty results")
                    break
                continue

            if not new_events:
                empty_count += 1
                print(f"  [uid={uid}] Round {call_count}: empty "
                      f"({empty_count}/{MAX_EMPTY_RETRIES})")
                if empty_count >= MAX_EMPTY_RETRIES:
                    print(f"  [uid={uid}] ABORT: {MAX_EMPTY_RETRIES} "
                          f"consecutive failures/empty results")
                    break
                continue

            # New events arrived; reset the empty counter
            empty_count = 0
            new_events = _apply_event_name_strategy(new_events, name_strategy, is_chinese)
            n_before = len(current_events)
            current_events = _merge_and_sort_events(
                current_events, new_events, persona_max)
            n_added = len(current_events) - n_before

            # Update the record and save a checkpoint (thread-safe)
            record = persona.copy()
            record['Events'] = current_events
            with self.lock:
                self.records[uid] = record
                self._save_checkpoint()

            print(f"  [uid={uid}] Round {call_count}: +{n_added}, "
                  f"now {len(current_events)}/{persona_max} (saved)")

        # Final update (ensure the last round's result is recorded)
        record = persona.copy()
        record['Events'] = current_events
        with self.lock:
            self.records[uid] = record

        if not current_events:
            raise RuntimeError(f"uuid={uid} produced no annual events")

        total_added = len(current_events) - n_start
        print(f"  [uid={uid}] COMPLETE: {len(current_events)} events "
              f"(+{total_added} new)")

    def run(self, stage3_records: List[Dict], max_workers: int = DEFAULT_WORKERS):
        """
        Process all personas in parallel.

        Returns: the records list in the original order
        """
        # Classify: skip / needs processing
        to_process = []
        for persona in stage3_records:
            uid = persona.get('uuid')
            ex = self.records.get(uid)
            n = len(ex.get('Events', [])) if ex else 0

            if n >= self.max_events:
                # Truncate to max_events (if there are too many)
                if n > self.max_events:
                    record = ex.copy()
                    record['Events'] = ex['Events'][:self.max_events]
                    for idx, evt in enumerate(record['Events']):
                        evt['event_id'] = idx
                    self.records[uid] = record
                print(f"[Stage4] uid={uid}: SKIP ({n} events >= {self.max_events})")
            else:
                to_process.append(persona)
                # Ensure this persona has an initial record in records
                if uid not in self.records:
                    self.records[uid] = persona.copy()
                    self.records[uid]['Events'] = []
                if n > 0:
                    print(f"[Stage4] uid={uid}: INCREMENTAL "
                          f"({n} existing, need {self.max_events - n} more)")
                else:
                    print(f"[Stage4] uid={uid}: FULL ({self.max_events} events)")

        if not to_process:
            print("[Stage4] All personas already complete!")
            return self._get_ordered_records()

        actual_workers = min(max_workers, len(to_process))
        print(f"\n[Stage4] Processing {len(to_process)} personas "
              f"with {actual_workers} parallel workers...\n")

        # Run in parallel
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = {}
            for p in to_process:
                uid = p.get('uuid')
                future = executor.submit(self._process_persona, p)
                futures[future] = uid

            for future in as_completed(futures):
                uid = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"[Stage4] ERROR uid={uid}: {e}")
                    traceback.print_exc()

        # Final save
        with self.lock:
            self._save_checkpoint()

        empty_uids = [
            uid for uid in self.ordered_uuids
            if uid in self.records and not self.records[uid].get('Events')
        ]
        if empty_uids:
            raise RuntimeError(f"Stage4 produced no events for uuid(s): {empty_uids}")

        return self._get_ordered_records()

# ============================================================================
# Public API
# ============================================================================

class AnnualEventsGenerator(Generator):
    """Generate each persona's 2025 annual events (iterative top-up to a target).

    Domain generator for the old stage 4. The standalone batch run uses
    :func:`generate_annual_events` (a parallel :class:`_Stage4Runner` with per-persona
    iterative top-up + a Social-Graph name strategy). This class is a thin
    uniform per-persona entry point for the future pipeline DAG, delegating to
    the single-shot :func:`process_single_persona`.
    """

    stage_label = "Stage4"
    stage_num = 4
    index_key = "uuid"
    produces = "annual_events"

    def __init__(self, prompt: str, max_events: int = 100) -> None:
        self.prompt = prompt
        self.max_events = max_events

    def produce(self, record: Dict, ctx=None) -> Dict:
        return process_single_persona(record, self.prompt, self.max_events)


def generate_annual_events(stage3_records: List[Dict], prompts_dir: str,
                    max_events: int = 10,
                    existing: Optional[Dict[str, Dict]] = None,
                    save_callback=None,
                    max_workers: int = DEFAULT_WORKERS) -> List[Dict]:
    """
    Generate annual events in parallel, with checkpoint/resume and iterative top-up support.

    Args:
        stage3_records: list of stage3 output records
        prompts_dir: path to the prompts/ directory
        max_events: final target total events per persona
        existing: uuid -> existing stage4 record (checkpoint data)
        save_callback: save callback fn(records_list), triggered after each LLM call
        max_workers: number of parallel workers

    Returns:
        The complete records list (in the original persona order)
    """
    existing = existing or {}
    prompt_path = os.path.join(prompts_dir, 'stage4_annual_events.txt')
    system_prompt = load_prompt(prompt_path)
    
    # Load the Chinese prompt file
    prompt_path_cn = os.path.join(prompts_dir, 'stage4_annual_events_cn.txt')
    system_prompt_cn = load_prompt(prompt_path_cn)

    print(f"[Stage4] Target: {max_events} events/person, "
          f"Workers: {max_workers}")

    ordered_uuids = [p.get('uuid') for p in stage3_records]

    runner = _Stage4Runner(
        system_prompt=system_prompt,
        system_prompt_cn=system_prompt_cn,
        max_events=max_events,
        ordered_uuids=ordered_uuids,
        existing=existing,
        save_callback=save_callback
    )

    return runner.run(stage3_records, max_workers=max_workers)
