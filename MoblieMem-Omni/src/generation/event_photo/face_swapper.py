# -*- coding: utf-8 -*-
"""Post-generation face swap for event images.

After an event scene image is generated, the protagonist (and any matched
participant) faces are swapped to their canonical reference faces using
insightface's ``inswapper`` model. This pins identity far more reliably than
text prompts / img2img alone (observed cosine similarity ~0.5 -> ~0.9), while
inswapper's affine alignment + mask blend keeps the result natural (no hard
paste edges).

Design:
* Reuses the shared FaceAnalysis app and the unicode-safe imread/imwrite from
  :mod:`backends.faces` (no second model load, Chinese paths handled).
* The candidate identity pool is the protagonist plus the participant avatars
  the caller already matched for this event, so a face is only ever swapped to
  someone who actually belongs in the scene (places/strangers are left alone).
* Assignment is two-stage: the protagonist locks its most-similar face first,
  then participants are matched to the remaining faces by optimal (max-weight)
  assignment rather than a sequential greedy, so look-alike participants are not
  given the wrong face or skipped.
* Degrades gracefully: if the inswapper model file or insightface is missing,
  every entry point is a no-op and event generation is unaffected.
"""
from __future__ import annotations

import os
import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from backends.faces import FaceEngine

if TYPE_CHECKING:  # numpy stays an optional runtime dep, imported only where used
    import numpy as np

# Identity/recognition logger, shared with backends.faces. Loggers here are
# per-capability channels (not per-module), so all face-consistency logs group.
logger = logging.getLogger('fix_event_images')

# inswapper model location: insightface cache by default, override via env.
_DEFAULT_MODEL = os.path.join(os.path.expanduser("~"), ".insightface", "models", "inswapper_128.onnx")
INSWAPPER_PATH = os.environ.get("INSWAPPER_MODEL", _DEFAULT_MODEL)
# The candidate pool is already constrained to the event's real participants
# (places/strangers are not in it), so a low bar lets every attendee get swapped
# while a face that matches no candidate is simply left untouched.
SWAP_MATCH_MIN = 0.10

# event_photo generation runs under a ThreadPoolExecutor, so the shared model and
# the reference-face cache are guarded. The inswapper session itself is safe to
# call concurrently once loaded.
_swapper: Optional[Any] = None
_swapper_failed = False
_swapper_lock = threading.Lock()
_ref_cache: Dict[str, Any] = {}
_ref_cache_lock = threading.Lock()


def _get_swapper() -> Optional[Any]:
    """Lazily load the inswapper model once; cache the failure to stay a no-op.

    Thread-safe: concurrent callers serialize on ``_swapper_lock`` while loading,
    then share the single session (inswapper inference is safe to call in parallel).
    """
    global _swapper, _swapper_failed
    if _swapper is not None:
        return _swapper
    if _swapper_failed:
        return None
    with _swapper_lock:
        if _swapper is not None:
            return _swapper
        if _swapper_failed:
            return None
        if not os.path.exists(INSWAPPER_PATH):
            logger.warning(f"face swap disabled: inswapper model not found at {INSWAPPER_PATH}")
            _swapper_failed = True
            return None
        try:
            os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            import insightface
            _swapper = insightface.model_zoo.get_model(INSWAPPER_PATH, providers=['CPUExecutionProvider'])
            logger.info(f"face swap enabled: loaded inswapper from {INSWAPPER_PATH}")
            return _swapper
        except Exception as e:  # pragma: no cover - optional dependency path
            logger.warning(f"face swap disabled: failed to load inswapper ({e})")
            _swapper_failed = True
            return None


def _largest(faces: List[Any]) -> Any:
    """Return the face with the largest bounding-box area."""
    return max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))


def _ref_face(app: Any, path: str) -> Optional[Any]:
    """Largest face object of a reference image (thread-safe cache, per path)."""
    with _ref_cache_lock:
        if path in _ref_cache:
            return _ref_cache[path]
    face = None
    img = FaceEngine.imread(path)
    if img is not None:
        faces = app.get(img)
        if faces:
            face = _largest(faces)
    with _ref_cache_lock:
        _ref_cache[path] = face
    return face


def _optimal_pairs(sim: "np.ndarray") -> List[Tuple[int, int]]:
    """Row/col index pairs maximizing total similarity, one row & col each.

    Uses Hungarian assignment (scipy) for the global optimum; falls back to a
    numpy greedy (take the highest remaining cell, strike its row + col) when
    scipy is unavailable. ``sim`` is a ``rows x cols`` similarity matrix.
    """
    import numpy as np
    if sim.size == 0:
        return []
    try:
        from scipy.optimize import linear_sum_assignment
        rows, cols = linear_sum_assignment(sim, maximize=True)
        return list(zip(rows.tolist(), cols.tolist()))
    except Exception:  # pragma: no cover - scipy missing fallback
        m = sim.astype(float).copy()
        pairs = []
        for _ in range(min(m.shape)):
            r, c = np.unravel_index(int(np.argmax(m)), m.shape)
            if not np.isfinite(m[r, c]):
                break
            pairs.append((int(r), int(c)))
            m[r, :] = -np.inf
            m[:, c] = -np.inf
        return pairs


def apply_face_swap(image_path: str,
                    person_image_paths: List[str],
                    participant_avatar_map: Optional[Dict[str, str]] = None,
                    swap_min: float = SWAP_MATCH_MIN) -> Optional[Dict[str, float]]:
    """Swap protagonist + matched participants in ``image_path`` to their refs.

    The image is overwritten in place on success. Returns ``{label: similarity}``
    of the swaps that were applied, or ``None`` when the swap was skipped
    (model/deps unavailable, no detectable faces, or no usable references).
    """
    swapper = _get_swapper()
    app = FaceEngine.app()
    if swapper is None or app is None:
        return None

    img = FaceEngine.imread(image_path)
    if img is None:
        return None
    faces = app.get(img)
    if not faces:
        return None

    # Identity pool, split into protagonist + participants. Assign in two stages
    # so the protagonist's face is pinned first (it must be the most accurate),
    # then participants are matched optimally among the *remaining* faces. This
    # avoids the protagonist-grabs-a-participant's-face errors a sequential
    # greedy makes when AI-generated faces are hard to tell apart.
    protagonist = None
    for p in (person_image_paths or []):
        protagonist = _ref_face(app, p)
        if protagonist is not None:
            break
    participants: List[Tuple[str, Any]] = []  # (name, source_face)
    for name, path in (participant_avatar_map or {}).items():
        rf = _ref_face(app, path)
        if rf is not None:
            participants.append((name, rf))
    if protagonist is None and not participants:
        return None

    used: Set[int] = set()
    applied: Dict[str, float] = {}
    res = img

    # Stage 1: protagonist locks the single most-similar face globally.
    if protagonist is not None:
        best_s, best_i = -1.0, -1
        for i, fc in enumerate(faces):
            s = FaceEngine.cosine_similarity(fc.embedding, protagonist.embedding)
            if s > best_s:
                best_s, best_i = s, i
        if best_i >= 0 and best_s >= swap_min:
            used.add(best_i)
            res = swapper.get(res, faces[best_i], protagonist, paste_back=True)
            applied["protagonist"] = round(float(best_s), 4)

    # Stage 2: optimal (max-weight) matching of participants to the faces the
    # protagonist did not take; keep only pairs above the threshold.
    free = [i for i in range(len(faces)) if i not in used]
    if participants and free:
        import numpy as np
        sim = np.empty((len(participants), len(free)), dtype=float)
        for r, (_, pf) in enumerate(participants):
            for c, fi in enumerate(free):
                sim[r, c] = FaceEngine.cosine_similarity(faces[fi].embedding, pf.embedding)
        for r, c in _optimal_pairs(sim):
            s = float(sim[r, c])
            if s < swap_min:
                continue
            fi = free[c]
            name, pf = participants[r]
            used.add(fi)
            res = swapper.get(res, faces[fi], pf, paste_back=True)
            applied[name] = round(s, 4)

    if not applied:
        return None
    FaceEngine.imwrite(image_path, res)
    return applied
