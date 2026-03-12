# -*- coding: utf-8 -*-
"""Constant question-answer pairs synthesis notebook state scheduler."""
import random
from ._qa_base import QANotebookStateSchedulerBase
from ..models import (
    Event, 
    PersonBase, 
    QuestionAnswerPair,
) 
from ..models.persona import PersonDimensionBase


class ConstantQANotebookStateScheduler(QANotebookStateSchedulerBase):
    """The scheduler that uses constant values for question-answer pairs synthesis parameters."""
    
    def __init__(
        self,
        min_qa_pairs: int = 3,
        max_qa_pairs: int = 10,
        max_attempts: int = 5,
        total_select: int = 10,
        random_seed: int | None = None,
    ) -> None:
        """Initialize the constant question-answer pairs synthesis scheduler.
        
        Args:
            min_qa_pairs (`int`, defaults to `3`):
                Minimum number of question-answer pairs to generate at each level.
            max_qa_pairs (`int`, defaults to `10`):
                Maximum number of question-answer pairs to generate at each level.
            max_attempts (`int`, defaults to `5`):
                Maximum number of question-answer pairs synthesis attempts allowed.
            total_select (`int`, defaults to `10`):
                Number of question-answer pairs to randomly select from unconsumed and unexpired 
                question-answer pairs for propagation to upper hierarchy levels.
            random_seed (`int | None`, optional):
                Random seed for reproducible random selection.
        """
        super().__init__()
        
        # Validate parameters
        if min_qa_pairs < 1:
            raise ValueError(
                "The minimum number of question-answer pairs must be greater than 0. "
                f"However, you provided {min_qa_pairs}."
            )
        if max_qa_pairs < min_qa_pairs:
            raise ValueError(
                "The maximum number of question-answer pairs must be greater than or equal to the minimum number of question-answer pairs. "
                f"However, you provided {max_qa_pairs}, which is less than {min_qa_pairs}."
            )
        if max_attempts < 1:
            raise ValueError(
                "The maximum number of attempts must be greater than 0. "
                f"However, you provided {max_attempts}."
            )
        if total_select < 1:
            raise ValueError(
                "The number of question-answer pairs to randomly select from unconsumed and unexpired "
                "question-answer pairs for propagation to upper hierarchy levels must be greater than 0. "
                f"However, you provided {total_select}."
            )
        
        self.min_qa_pairs = min_qa_pairs
        self.max_qa_pairs = max_qa_pairs
        self.max_attempts = max_attempts
        self.total_select = total_select

        self._rng = random.Random(random_seed)
        
        self.register_state("min_qa_pairs")
        self.register_state("max_qa_pairs")
        self.register_state("max_attempts")
        self.register_state("total_select")
        
        def _to_json(rng: random.Random) -> list[int | list[int] | None]:
            state = rng.getstate()
            return [
                state[0], 
                list(state[1]), 
                state[2], 
            ]
        
        def _from_json(state: list[int | list[int] | None]) -> random.Random:
            rng = random.Random()
            state = (
                state[0], 
                tuple(state[1]), 
                state[2], 
            )
            rng.setstate(state)
            return rng

        self.register_state(
            "_rng", 
            custom_to_json=lambda _: _to_json(_) if _ else None,
            custom_from_json=lambda _: _from_json(_) if _ else None,
        )
    
    def get_qa_count_range(
        self,
        target: Event | PersonDimensionBase | PersonBase,
        level: int = 0,
    ) -> tuple[int, int]:
        return (self.min_qa_pairs, self.max_qa_pairs)
    
    def get_max_attempts(
        self,
        target: Event | PersonDimensionBase | PersonBase,
        level: int = 0,
    ) -> int: 
        return self.max_attempts
    
    def get_propagation_params(
        self,
        level: int = 0,
    ) -> int:
        return self.total_select

    def random_select_for_propagation(
        self,
        qa_pairs: list[QuestionAnswerPair],
        reference_timestamp: str | None = None,
        level: int = 0,
    ) -> tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]:
        """Randomly select question-answer pairs for propagation to the upper hierarchy level.
        
        Args:
            qa_pairs (`list[QuestionAnswerPair]`):
                All question-answer pairs at the current level.
            reference_timestamp (`str | None`, optional):
                Reference timestamp for expiry checks (ISO 8601). If None, uses the current time.
            level (`int`, defaults to `0`):
                The current hierarchy level.
        
        Returns:
            `tuple[list[QuestionAnswerPair], list[QuestionAnswerPair]]`:
                A tuple containing the selected question-answer pairs and the remaining question-answer pairs.
        """
        candidates = self.get_propagation_candidates(
            qa_pairs,
            reference_timestamp=reference_timestamp,
        )
        k = min(self.get_propagation_params(level=level), len(candidates))
        selected = self._rng.sample(candidates, k)
        selected_ids = {qa.id for qa in selected}
        remaining = [qa for qa in qa_pairs if qa.id not in selected_ids]
        return selected, remaining
