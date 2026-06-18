# -*- coding: utf-8 -*-
"""Unified face capability (L1 backend) — FaceEngine.

Two groups of helpers:

* recognition / consistency verification: lazily loads insightface, caches
  reference embeddings per uuid, and verifies that a generated event image
  contains the reference person — logs under the ``fix_event_images`` logger.
* avatar image processing: face detection, auto-orientation, and face-centered
  cropping of generated member avatars — logs under the ``stage7`` logger.

``FaceEngine`` is a thin facade for generators. The heavy native deps
(cv2 / numpy / insightface) stay lazily imported inside the functions, so
importing this module has no side effects.
"""
from __future__ import annotations

import os
import logging
import threading
from typing import Dict, List, Optional, Tuple

# Avatar-processing logger.
logger = logging.getLogger('stage7')
# Recognition logger.
_REC_LOGGER = logging.getLogger('fix_event_images')


# ====================================================================== #
# Recognition / consistency verification  (origin: stage7_1_faces)       #
# ====================================================================== #

FACE_SIMILARITY_THRESHOLD = 0.35
FACE_SIMILARITY_THRESHOLD_INTL = 0.22  # non-Chinese nationalities: generated faces vary more, so the threshold is relaxed

def get_face_threshold(nationality: str) -> float:
    """Return an appropriate face similarity threshold based on nationality."""
    return FACE_SIMILARITY_THRESHOLD if nationality == "Chinese" else FACE_SIMILARITY_THRESHOLD_INTL

_THREAD_LOCAL = threading.local()
_REFERENCE_EMBEDDINGS_CACHE: Dict[int, List] = {}
_REFERENCE_EMBEDDINGS_LOCK = threading.Lock()
_FACE_IMPORT_FAILED = False


def _load_face_modules():
    """Lazily load optional face verification dependencies."""
    global _FACE_IMPORT_FAILED
    if _FACE_IMPORT_FAILED:
        return None

    try:
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
        import cv2
        import numpy as np
        from insightface.app import FaceAnalysis
        return cv2, np, FaceAnalysis
    except ImportError as e:
        _REC_LOGGER.warning(f"Face verification disabled: missing dependency ({e})")
        _FACE_IMPORT_FAILED = True
        return None

def get_face_app():
    """Get a thread-local FaceAnalysis app."""
    modules = _load_face_modules()
    if not modules:
        return None

    if not hasattr(_THREAD_LOCAL, 'face_app'):
        _, _, FaceAnalysis = modules
        app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=0, det_size=(640, 640))
        _THREAD_LOCAL.face_app = app
    return _THREAD_LOCAL.face_app

def cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two face embeddings."""
    modules = _load_face_modules()
    if not modules:
        return -1.0
    _, np, _ = modules
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def extract_reference_embeddings(person_image_paths: List[str]) -> List:
    """Extract face embeddings from the reference person images."""
    app = get_face_app()
    modules = _load_face_modules()
    if not app or not modules:
        return []

    cv2, _, _ = modules
    embeddings = []
    for image_path in person_image_paths:
        img = _imread_safe(image_path)
        if img is None:
            _REC_LOGGER.warning(f"Failed to read reference image: {image_path}")
            continue

        faces = app.get(img)
        if not faces:
            _REC_LOGGER.warning(f"No face detected in reference image: {image_path}")
            continue

        face = max(faces, key=lambda item: (item.bbox[2] - item.bbox[0]) * (item.bbox[3] - item.bbox[1]))
        embeddings.append(face.embedding)

    return embeddings

def get_reference_embeddings_for_uuid(uuid: int, person_image_paths: List[str]) -> List:
    """Cache reference embeddings per uuid to avoid repeated face analysis."""
    with _REFERENCE_EMBEDDINGS_LOCK:
        if uuid in _REFERENCE_EMBEDDINGS_CACHE:
            return _REFERENCE_EMBEDDINGS_CACHE[uuid]

    embeddings = extract_reference_embeddings(person_image_paths)
    with _REFERENCE_EMBEDDINGS_LOCK:
        _REFERENCE_EMBEDDINGS_CACHE[uuid] = embeddings
    return embeddings

def verify_face_match(image_path: str, reference_embeddings: List, threshold: float) -> Tuple[bool, Optional[float], str]:
    """Verify whether a generated event image contains the reference person."""
    if not reference_embeddings:
        return False, None, 'no reference embeddings'

    app = get_face_app()
    modules = _load_face_modules()
    if not app or not modules:
        return False, None, 'face verifier unavailable'

    cv2, _, _ = modules
    img = _imread_safe(image_path)
    if img is None:
        return False, None, 'failed to read generated image'

    faces = app.get(img)
    if not faces:
        return False, None, 'no face detected'

    best_similarity = -1.0
    for face in faces:
        for reference_embedding in reference_embeddings:
            similarity = cosine_similarity(face.embedding, reference_embedding)
            if similarity > best_similarity:
                best_similarity = similarity

    if best_similarity >= threshold:
        return True, best_similarity, f'max_similarity={best_similarity:.4f}'
    return False, best_similarity, f'max_similarity={best_similarity:.4f} < {threshold}'


def verify_named_identities(image_path: str, named_embeddings: Dict[str, List],
                            threshold: float) -> Dict[str, Tuple[bool, Optional[float]]]:
    """Verify that each named identity appears in the generated image.

    Faces are detected once; every identity is matched against its most-similar
    detected face. Returns ``{name: (is_match, best_similarity)}``. Identities with
    no usable reference embedding are skipped.
    """
    results: Dict[str, Tuple[bool, Optional[float]]] = {}
    named_embeddings = {n: e for n, e in (named_embeddings or {}).items() if e}
    if not named_embeddings:
        return results

    app = get_face_app()
    modules = _load_face_modules()
    if not app or not modules:
        return {name: (False, None) for name in named_embeddings}

    cv2, _, _ = modules
    img = _imread_safe(image_path)
    if img is None:
        return {name: (False, None) for name in named_embeddings}

    faces = app.get(img)
    if not faces:
        return {name: (False, None) for name in named_embeddings}

    face_embeddings = [face.embedding for face in faces]
    for name, refs in named_embeddings.items():
        best = -1.0
        for face_embedding in face_embeddings:
            for ref in refs:
                similarity = cosine_similarity(face_embedding, ref)
                if similarity > best:
                    best = similarity
        results[name] = (best >= threshold, best if best > -1.0 else None)
    return results


# ====================================================================== #
# Avatar image processing  (origin: stage7_gc_faces)                     #
# ====================================================================== #

# Lazily-initialized InsightFace detector shared across avatar crops. Was a
# module-level global in the original stage7_group_chats.
_FACE_ANALYSIS_APP = None


def _get_face_analysis_app():
    """Lazy-load the face detector used for avatar cropping."""
    global _FACE_ANALYSIS_APP
    if _FACE_ANALYSIS_APP is not None:
        return _FACE_ANALYSIS_APP

    try:
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        _FACE_ANALYSIS_APP = app
        return _FACE_ANALYSIS_APP
    except Exception as exc:
        logger.warning(f"FaceAnalysis unavailable, avatar cropping will fall back: {exc}")
        _FACE_ANALYSIS_APP = False
        return None


def _orient_face_from_kps(kps):
    """Return rotation degrees CW (0/90/180/270) to make face upright from 5-point kps."""
    import math
    eye_center = (kps[0] + kps[1]) / 2.0
    mouth_center = (kps[3] + kps[4]) / 2.0
    dx = eye_center[0] - mouth_center[0]
    dy = eye_center[1] - mouth_center[1]
    angle = math.degrees(math.atan2(-dy, dx))
    if 45 <= angle <= 135:
        return 0
    elif -45 <= angle < 45:
        return 270
    elif -135 <= angle < -45:
        return 180
    else:
        return 90


def _imread_safe(path: str):
    """cv2.imread with fallback for non-ASCII paths on Windows."""
    import cv2
    import numpy as np
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass
    return cv2.imread(path)


def _imwrite_safe(path: str, img) -> bool:
    """cv2.imwrite with fallback for non-ASCII paths on Windows."""
    import cv2
    try:
        ext = os.path.splitext(path)[1] or '.png'
        success, buf = cv2.imencode(ext, img)
        if success:
            with open(path, 'wb') as wf:
                wf.write(buf.tobytes())
            return True
    except Exception:
        pass
    ok = cv2.imwrite(path, img)
    if ok:
        return True
    return False


def _normalize_avatar_file(path: str) -> bool:
    """Re-encode an avatar file to match its target extension and strip metadata."""
    if not os.path.exists(path):
        return False

    img = _imread_safe(path)
    if img is None:
        return False

    folder = os.path.dirname(path)
    ext = os.path.splitext(path)[1] or '.png'
    tmp_path = os.path.join(folder, f"__avatar_normalized_tmp{ext}")
    try:
        if not _imwrite_safe(tmp_path, img):
            return False
        os.replace(tmp_path, path)
        return True
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _auto_orient_image(img, app):
    """Auto-orient a face image. Returns (oriented_img, rotation_degrees)."""
    import cv2
    faces = app.get(img)
    if faces:
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
        rot = _orient_face_from_kps(face.kps)
        if rot == 0:
            return img, 0
        rotations = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
        return cv2.rotate(img, rotations[rot]), rot
    # No face in original - try 90/180/270
    best_rot, best_score = 0, -1
    for try_rot, cv_code in [(90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180), (270, cv2.ROTATE_90_COUNTERCLOCKWISE)]:
        rotated = cv2.rotate(img, cv_code)
        faces = app.get(rotated)
        if faces:
            face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
            inner_rot = _orient_face_from_kps(face.kps)
            if inner_rot == 0 and float(face.det_score) > best_score:
                best_score = float(face.det_score)
                best_rot = try_rot
    if best_rot > 0:
        rotations = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
        return cv2.rotate(img, rotations[best_rot]), best_rot
    return img, 0


def _crop_avatar_to_face(image_path: str, output_path: str, padding_ratio: float = 0.35) -> bool:
    """Detect the largest face and save a face-centered crop only."""
    try:
        import cv2  # noqa: F401  # availability probe; OpenCV is an optional dependency
    except Exception as exc:
        logger.warning(f"OpenCV unavailable, cannot crop avatar {image_path}: {exc}")
        return False

    app = _get_face_analysis_app()
    if app is None:
        return False

    img = _imread_safe(image_path)
    if img is None:
        logger.warning(f"Cannot read avatar image for cropping: {image_path}")
        return False

    # Auto-orient face before cropping
    img, orient_rot = _auto_orient_image(img, app)
    if orient_rot > 0:
        logger.info(f"Auto-oriented avatar {orient_rot} degrees: {os.path.basename(image_path)}")

    faces = app.get(img)
    if not faces:
        logger.warning(f"No face detected in avatar image: {image_path}, falling back to center crop")
        side = min(img.shape[0], img.shape[1])
        side = int(side * 0.85)
        side = max(1, min(side, img.shape[0], img.shape[1]))
        left = max(0, (img.shape[1] - side) // 2)
        top = max(0, (img.shape[0] - side) // 2)
        cropped = img[top:top + side, left:left + side]
        if cropped.size == 0:
            logger.warning(f"Empty center crop produced for avatar image: {image_path}")
            return False
        _imwrite_safe(output_path, cropped)
        return True

    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    face_w = max(1, x2 - x1)
    face_h = max(1, y2 - y1)
    face_cx = x1 + face_w // 2
    face_cy = y1 + face_h // 2

    crop_size = int(max(face_w, face_h) * (1.0 + padding_ratio) * 2.0)
    crop_size = max(crop_size, int(min(img.shape[0], img.shape[1]) * 0.55))
    crop_size = min(crop_size, img.shape[0], img.shape[1])

    crop_left = face_cx - crop_size // 2
    crop_top = face_cy - crop_size // 2

    crop_left = max(0, min(crop_left, img.shape[1] - crop_size))
    crop_top = max(0, min(crop_top, img.shape[0] - crop_size))
    crop_right = crop_left + crop_size
    crop_bottom = crop_top + crop_size

    cropped = img[crop_top:crop_bottom, crop_left:crop_right]
    if cropped.size == 0:
        logger.warning(f"Empty crop produced for avatar image: {image_path}")
        return False

    _imwrite_safe(output_path, cropped)
    return True


def _save_generated_avatar_with_crop(generated_path: str, target_path: str) -> bool:
    """Crop the generated avatar immediately and save it using the final person-named path."""
    cropped_path = f"{target_path}.cropped.png"
    if os.path.exists(cropped_path):
        try:
            os.remove(cropped_path)
        except OSError:
            pass

    cropped_ok = _crop_avatar_to_face(generated_path, cropped_path)
    if cropped_ok and os.path.exists(cropped_path):
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        os.replace(cropped_path, target_path)
        return True

    if os.path.exists(cropped_path):
        try:
            os.remove(cropped_path)
        except OSError:
            pass
    return False


def maybe_auto_orient_avatar(target_path: str, uuid: int, member_name: str) -> bool:
    """Try to auto-orient an avatar in place and log the outcome."""
    if not _normalize_avatar_file(target_path):
        logger.warning(f"[uuid={uuid}] Avatar normalization failed for '{member_name}'")

    try:
        from fix_face_orientation import auto_orient_face
    except ImportError as exc:
        logger.warning(f"[uuid={uuid}] Avatar orientation helper unavailable for '{member_name}': {exc}")
        return False

    try:
        rot, ok = auto_orient_face(target_path)
        if rot > 0 and ok:
            logger.info(f"[uuid={uuid}] Avatar auto-oriented {rot}° for '{member_name}'")
            return True
        if not ok:
            logger.warning(f"[uuid={uuid}] Avatar orientation check failed for '{member_name}'")
        return False
    except Exception as exc:
        logger.warning(f"[uuid={uuid}] Avatar orientation error for '{member_name}': {exc}")
        return False


# ====================================================================== #
# FaceEngine — thin facade over the two groups for generators to adopt.  #
# ====================================================================== #

class FaceEngine:
    """Unified face capability: recognition + avatar processing.

    A single object generators can depend on (``from backends.faces import
    FaceEngine``) instead of importing the loose helpers. Every method delegates
    to the module-level function it replaces, so behavior is identical.
    """

    SIMILARITY_THRESHOLD = FACE_SIMILARITY_THRESHOLD
    SIMILARITY_THRESHOLD_INTL = FACE_SIMILARITY_THRESHOLD_INTL

    # -- recognition / consistency verification --
    @staticmethod
    def threshold_for(nationality: str) -> float:
        return get_face_threshold(nationality)

    @staticmethod
    def app():
        return get_face_app()

    @staticmethod
    def cosine_similarity(a, b) -> float:
        return cosine_similarity(a, b)

    @staticmethod
    def reference_embeddings(uuid: int, person_image_paths: List[str]) -> List:
        return get_reference_embeddings_for_uuid(uuid, person_image_paths)

    @staticmethod
    def verify(image_path: str, reference_embeddings: List, threshold: float):
        return verify_face_match(image_path, reference_embeddings, threshold)

    # -- avatar image processing --
    @staticmethod
    def imread(path: str):
        return _imread_safe(path)

    @staticmethod
    def imwrite(path: str, img) -> bool:
        return _imwrite_safe(path, img)

    @staticmethod
    def crop_avatar_to_face(image_path: str, output_path: str, padding_ratio: float = 0.35) -> bool:
        return _crop_avatar_to_face(image_path, output_path, padding_ratio)

    @staticmethod
    def save_avatar_with_crop(generated_path: str, target_path: str) -> bool:
        return _save_generated_avatar_with_crop(generated_path, target_path)

    @staticmethod
    def maybe_auto_orient_avatar(target_path: str, uuid: int, member_name: str) -> bool:
        return maybe_auto_orient_avatar(target_path, uuid, member_name)
