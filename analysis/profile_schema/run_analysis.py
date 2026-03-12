import json
import os
import re
import glob
import random
import numpy as np
import nltk
import asyncio
from pathlib import Path
from agentscope.embedding import (
    OpenAITextEmbedding, 
    EmbeddingModelBase, 
    FileEmbeddingCache,
)
from keme.models.persona import PersonBase
from custom_profile_schema import (
    PersonFull, 
    PersonMedium, 
    PersonCompact,
)


_ALL_SCHEMAS = [PersonFull, PersonMedium, PersonCompact]
SCHEMA_MAP = {cls.__name__: cls for cls in _ALL_SCHEMAS}


def compute_ratio_distinct_ngram(
    sentences: np.ndarray,
    sentence_labels: np.ndarray | None = None,
    n: int = 1, 
) -> float:
    """
    Compute the ratio of distinct n-grams for grouped sentences. This function calculates the 
    distinct n-grams within each group of sentences and returns the average ratio of unique 
    n-grams across all groups.

    The sentences are divided into groups based on the ``sentence_labels``. If no labels are 
    provided, all sentences are treated as part of the same group.

    Args:
        sentences (`np.ndarray`):
            A numpy array of sentences.
        sentence_labels (`np.ndarray`, optional):
            An array of labels corresponding to each sentence. If not provided, all sentences 
            are treated as a single group.
        n (`int`, defaults to `1`):
            The size of the n-grams to compute. For example, `n=1` computes unigrams, `n=2` computes 
            bigrams, and so on.

    Returns: 
        `float`:
            The average ratio of distinct n-grams across all groups. The ratio is computed as the 
            number of unique n-grams divided by the total number of n-grams in each group, averaged 
            over all groups.
    """
    if sentence_labels is None:
        sentence_labels = np.full_like(sentences, fill_value=0)
    group_num_distinct_ngram = {} 
    group_total_num_ngram = {} 

    for i, sentence in enumerate(sentences): 
        group = sentence_labels[i]
        if group not in group_num_distinct_ngram: 
            group_num_distinct_ngram[group] = set() 
            group_total_num_ngram[group] = 0 
        # The tokenization is done by the regex. 
        # This follows https://github.com/CHATS-lab/verbalized-sampling/blob/main/verbalized_sampling/evals/dialogue/linguistic.py#L178.
        words = re.findall(r"\b\w+\b", sentence.lower()) 
        current_ngram = nltk.ngrams(words, n=n)
        for ngram in current_ngram: 
            group_num_distinct_ngram[group].add(ngram)
            group_total_num_ngram[group] += 1 
    
    return sum(
        len(group_num_distinct_ngram[key]) / group_total_num_ngram[key] for key in group_num_distinct_ngram
    ) / len(group_total_num_ngram)


async def compute_semantic_score(
    sentences: np.ndarray,
    embedding_model: EmbeddingModelBase,
    sentence_labels: np.ndarray | None = None,
    batch_size: int = 1,
) -> tuple[float, np.ndarray]:
    """
    Compute the semantic diversity score for grouped sentences. It embeds all 
    sentences, computes pairwise cosine similarities within each group (clipped 
    to [0, 1]), and returns 1 minus the average similarity as the diversity score.

    Args:
        sentences (`np.ndarray`):
            A numpy array of sentences.
        embedding_model (`EmbeddingModelBase`):
            The embedding model used to encode sentences.
        sentence_labels (`np.ndarray`, optional):
            An array of labels corresponding to each sentence. If not provided, all
            sentences are treated as a single group.
        batch_size (`int`, defaults to `1`):
            The number of sentences per embedding API call.

    Returns:
        `tuple[float, np.ndarray]`:
            A tuple containing the semantic diversity score and sentence embeddings.
    """
    # Encode all sentences in batches. 
    all_embeddings = []
    for start in range(0, len(sentences), batch_size):
        batch = sentences[start:start + batch_size].tolist()
        response = await embedding_model(batch)
        all_embeddings.extend(response.embeddings)
    embeddings = np.array(all_embeddings, dtype=np.float64)

    # L2-normalise for cosine similarity via dot product.
    # This ensures the similarity is between -1 and 1.
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings_normed = embeddings / norms

    if sentence_labels is None:
        sentence_labels = np.full_like(sentences, fill_value=0)

    groups = np.unique(sentence_labels)
    group_scores = []

    for group in groups:
        mask = sentence_labels == group
        group_emb = embeddings_normed[mask]
        n = len(group_emb)
        if n < 2:
            raise ValueError(
                f"Sentence group {group} has less than 2 sentences. "
                "At least 2 sentences are required to compute the semantic diversity score."
            )
        sim_matrix = group_emb @ group_emb.T
        # Negative similarities are clipped to 0 to avoid inflating diversity scores.
        # See https://arxiv.org/pdf/2510.01171. 
        sim_matrix = np.clip(sim_matrix, 0.0, 1.0)
        triu_indices = np.triu_indices(n, k=1)
        mean_sim = sim_matrix[triu_indices].mean()
        group_scores.append(mean_sim)

    diversity = 1.0 - np.mean(group_scores)
    return diversity, embeddings


def compute_field_activation(person: PersonBase) -> tuple[int, int, float]:
    """Compute the field activation ratio for a person profile.

    A field is "activated" if it has been linked to at least one message
    (i.e. ``has_connections`` is True). For list fields, activation means
    at least one element has connections.

    Only fields declared in ``get_string_fields`` and ``get_list_fields``
    (excluding ``description``) are counted.

    Args:
        person (`PersonBase`):
            The person profile to compute the field activation ratio for.

    Returns:
        `tuple[int, int, float]`:
            A tuple containing the number of activated fields, the total number of fields, 
            and the activation ratio.
    """
    total = 0
    activated = 0

    for field_name, dim_cls in type(person).get_dimension_fields():
        dim = getattr(person, field_name)

        # String fields (excluding description).
        for sf in dim_cls.get_string_fields():
            if sf == "description":
                continue
            total += 1
            attr = getattr(dim, sf)
            if attr.has_connections:
                activated += 1

        # List fields.
        for lf in dim_cls.get_list_fields():
            total += 1
            items = getattr(dim, lf)
            if any(item.has_connections for item in items):
                activated += 1

    ratio = activated / total if total > 0 else 0.0
    return activated, total, ratio


_SCRIPT_DIR = Path(__file__).resolve().parent

TRAJECTORY_DIR = str(_SCRIPT_DIR / "output" / "trajectories")

EMBEDDING_MODEL_NAME = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBEDDING_API_KEY = "YOUR_API_KEY"
EMBEDDING_BASE_URL = "YOUR_BASE_URL"
EMBEDDING_BATCH_SIZE = 16
EMBEDDING_CACHE_DIR = str(_SCRIPT_DIR / "output" / ".cache" / "embeddings")

NGRAM_N = 2
NUM_SAMPLING_ROUNDS = 5

RANDOM_SEED = 0


async def main():
    # Load all trajectory JSONs, extract user-role messages, and deserialize persons.
    trajectories = {}
    persons = {}

    for path in sorted(glob.glob(os.path.join(TRAJECTORY_DIR, "*_trajectory.json"))):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        person_name = data["person"]["name"]
        profile_type = data["profile_type"]

        # Deserialize person into the correct schema class.
        schema_cls = SCHEMA_MAP.get(profile_type)
        if schema_cls is not None:
            persons[(person_name, profile_type)] = schema_cls.model_validate(data["person"])

        user_messages = []
        for session in data["sessions"]:
            for msg in session["messages"]:
                if msg["role"] == "user":
                    user_messages.append(f"{msg['role']}: {msg['content']}")

        trajectories[(person_name, profile_type)] = user_messages

    # Derive person names and profile types from loaded data.
    PERSON_NAMES = sorted(set(pn for pn, _ in trajectories.keys()))
    PROFILE_TYPES = sorted(set(pt for _, pt in trajectories.keys()))

    # Compute per-person minimum message count (across its profile types).
    person_sample_sizes = {}
    for pn in PERSON_NAMES:
        counts = [len(trajectories[(pn, pt)]) for pt in PROFILE_TYPES if (pn, pt) in trajectories]
        person_sample_sizes[pn] = min(counts)

    # Print message counts per trajectory.
    print(f"{'Person':<22} {'Profile Type':<18} {'# Msgs':>8} {'Sample N':>10}")
    print("-" * 62)
    for (pn, pt) in sorted(trajectories.keys()):
        count = len(trajectories[(pn, pt)])
        print(f"{pn:<22} {pt:<18} {count:>8} {person_sample_sizes[pn]:>10}")

    print(f"\nProfile types: {PROFILE_TYPES}")
    print(f"Per-person sample sizes: {person_sample_sizes}")


    # Generate `NUM_SAMPLING_ROUNDS` independent samples per trajectory.
    # Each person uses its own per-person minimum message count as the sample size,
    # so different persons may have different sample sizes.
    all_sampled_rounds: list[dict[tuple, list[str]]] = []

    for round_idx in range(NUM_SAMPLING_ROUNDS):
        rng = random.Random(RANDOM_SEED + round_idx)
        sampled_round = {}
        for (pn, pt), messages in trajectories.items():
            n_sample = person_sample_sizes[pn]
            if len(messages) <= n_sample:
                sampled_round[(pn, pt)] = messages[:]
            else:
                sampled_round[(pn, pt)] = rng.sample(messages, n_sample)
        all_sampled_rounds.append(sampled_round)

    print(f"Prepared {len(all_sampled_rounds)} sampling rounds x {NUM_SAMPLING_ROUNDS} seeds.")


    # Build embedding model with a embedding cache to avoid redundant API calls.
    embedding_cache = FileEmbeddingCache(cache_dir=EMBEDDING_CACHE_DIR)
    embedding_model = OpenAITextEmbedding(
        api_key=EMBEDDING_API_KEY,
        model_name=EMBEDDING_MODEL_NAME,
        dimensions=EMBEDDING_DIMENSIONS,
        base_url=EMBEDDING_BASE_URL,
        embedding_cache=embedding_cache,
    )

    # Accumulate per-key metrics across all sampling rounds.
    ngram_accum = {k: [] for k in trajectories}
    semantic_accum = {k: [] for k in trajectories}

    for round_idx, sampled_round in enumerate(all_sampled_rounds):
        print(f"  Round {round_idx + 1}/{NUM_SAMPLING_ROUNDS} ...", end="")
        for key, messages in sampled_round.items():
            sentences = np.array(messages)
            ngram_score = compute_ratio_distinct_ngram(sentences, n=NGRAM_N)
            ngram_accum[key].append(ngram_score)

            sem_score, _ = await compute_semantic_score(
                sentences, 
                embedding_model, 
                batch_size=EMBEDDING_BATCH_SIZE,
            )
            semantic_accum[key].append(sem_score)
        print(" Done!")

    # Average across rounds.
    ngram_avg = {k: np.mean(v) for k, v in ngram_accum.items()}
    semantic_avg = {k: np.mean(v) for k, v in semantic_accum.items()}

    # Compute field activation for each person profile.
    activation_info = {}
    for key, person in persons.items():
        activation_info[key] = compute_field_activation(person)

    header = (
        f"{'Person':<22} {'Profile Type':<18} {'Dist-2-gram':>12} {'Sem. Div.':>12}"
        f" {'Fields':>7} {'Active':>7} {'Act.%':>7}"
    )
    print(f"\n{header}")
    print("-" * len(header))
    for key in sorted(ngram_avg.keys()):
        pn, pt = key
        act, total, ratio = activation_info[key]
        print(
            f"{pn:<22} {pt:<18} {ngram_avg[key]:>12.4f} {semantic_avg[key]:>12.4f}"
            f" {total:>7} {act:>7} {ratio:>7.1%}"
        )

    agg_header = (
        f"{'Profile Type':<18} {'Dist-2-gram':>12} {'Sem. Div.':>12}"
        f" {'Fields':>7} {'Act.%':>7}"
    )
    print(f"\n{agg_header}")
    print("-" * len(agg_header))
    for pt in PROFILE_TYPES:
        pt_ngram = np.mean([v for (_, p), v in ngram_avg.items() if p == pt])
        pt_sem   = np.mean([v for (_, p), v in semantic_avg.items() if p == pt])
        pt_fields = np.mean([t for (_, p), (_, t, _) in activation_info.items() if p == pt])
        pt_ratio  = np.mean([r for (_, p), (_, _, r) in activation_info.items() if p == pt])
        print(
            f"{pt:<18} {pt_ngram:>12.4f} {pt_sem:>12.4f}"
            f" {pt_fields:>7.0f} {pt_ratio:>7.1%}"
        )


if __name__ == "__main__":
    asyncio.run(main())
