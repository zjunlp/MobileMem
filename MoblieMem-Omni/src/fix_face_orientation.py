"""
Automatically detect and correct portrait image orientation (upside down or sideways).

Uses insightface's 5 keypoints (eyes, nose tip, and mouth corners) to infer
face orientation. If the face is not upright, the image is rotated and saved
in place.

Dependencies: insightface, opencv-python, numpy, onnxruntime
"""

import os
import math
import logging

# Avoid OpenMP duplicate-runtime conflicts when insightface and numpy/torch link libiomp5md.dll.
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')

logger = logging.getLogger(__name__)

_FACE_APP = None
ORIENTATION_SNAP_TOLERANCE_DEGREES = 20.0


def _get_face_app():
    global _FACE_APP
    if _FACE_APP is not None:
        return _FACE_APP if _FACE_APP else None
    try:
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(allowed_modules=['detection'], providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=0, det_size=(640, 640))
        _FACE_APP = app
        return _FACE_APP
    except Exception as exc:
        logger.warning(f"FaceAnalysis unavailable: {exc}")
        _FACE_APP = False
        return None


def _face_angle_from_kps(kps):
    """Return the eye-center to mouth-center angle in degrees."""
    eye_center = (kps[0] + kps[1]) / 2.0
    mouth_center = (kps[3] + kps[4]) / 2.0
    dx = eye_center[0] - mouth_center[0]
    dy = eye_center[1] - mouth_center[1]
    return math.degrees(math.atan2(-dy, dx))


def _eye_line_horizontal_delta_from_kps(kps):
    """Return how far the eye line is from horizontal in degrees."""
    dx = kps[1][0] - kps[0][0]
    dy = kps[1][1] - kps[0][1]
    angle = math.degrees(math.atan2(dy, dx))
    return min(abs(angle), abs(angle - 180.0), abs(angle + 180.0))


def _upright_face_score_from_kps(kps):
    """Lower score means the face looks more upright."""
    face_angle = _face_angle_from_kps(kps)
    upright_delta = abs(face_angle - 90.0)
    eye_horizontal_delta = _eye_line_horizontal_delta_from_kps(kps)
    return upright_delta + eye_horizontal_delta, face_angle, eye_horizontal_delta


def _orient_face_from_kps(kps):
    """Return the clockwise rotation needed to make a face upright: 0/90/180/270."""
    angle = _face_angle_from_kps(kps)
    right_delta = abs(angle - 0.0)
    upside_down_delta = abs(angle + 90.0)
    left_delta = min(abs(angle - 180.0), abs(angle + 180.0))
    upright_delta = abs(angle - 90.0)

    if upright_delta <= ORIENTATION_SNAP_TOLERANCE_DEGREES:
        return 0      # Close to upright; keep a slight head tilt.
    if right_delta <= ORIENTATION_SNAP_TOLERANCE_DEGREES:
        return 270    # Close to lying sideways to the right.
    if upside_down_delta <= ORIENTATION_SNAP_TOLERANCE_DEGREES:
        return 180    # Close to upside down.
    if left_delta <= ORIENTATION_SNAP_TOLERANCE_DEGREES:
        return 90     # Close to lying sideways to the left.
    return 0


def _imread_safe(path: str):
    import cv2
    import numpy as np
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass
    img = cv2.imread(path)
    if img is not None:
        return img
    return img


def _imwrite_safe(path: str, img) -> bool:
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


def auto_orient_face(image_path: str) -> tuple:
    """
    Detect face orientation in an image and rotate it in place if needed.
    
    Returns:
        (rotation_degrees, success): 
            rotation_degrees: Actual rotation applied (0/90/180/270).
            success: Whether processing succeeded.
    """
    import cv2

    app = _get_face_app()
    if app is None:
        return 0, False

    img = _imread_safe(image_path)
    if img is None:
        logger.warning(f"Cannot read image: {image_path}")
        return 0, False

    rotations = {
        0: None,
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }

    best = None
    for try_rot, cv_code in rotations.items():
        candidate = img if cv_code is None else cv2.rotate(img, cv_code)
        faces = app.get(candidate)
        if not faces:
            continue

        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        face_area = (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])
        upright_score, face_angle, eye_horizontal_delta = _upright_face_score_from_kps(face.kps)
        det_score = float(getattr(face, 'det_score', 0.0))
        candidate_score = (upright_score, -det_score, -face_area, try_rot, face_angle, eye_horizontal_delta)
        if best is None or candidate_score < best:
            best = candidate_score

    if best is None:
        logger.warning(f"No face detected in any orientation: {os.path.basename(image_path)}")
        return 0, False

    best_upright_score, _neg_det_score, _neg_face_area, best_rot, best_face_angle, best_eye_delta = best
    if best_rot == 0:
        return 0, True

    if best_upright_score > ORIENTATION_SNAP_TOLERANCE_DEGREES * 2:
        logger.warning(
            f"Face orientation ambiguous for {os.path.basename(image_path)}: "
            f"score={best_upright_score:.1f}, angle={best_face_angle:.1f}, eye_delta={best_eye_delta:.1f}"
        )
        return 0, True

    rotated = cv2.rotate(img, rotations[best_rot])
    if _imwrite_safe(image_path, rotated):
        logger.info(f"Auto-oriented {best_rot}° CW: {os.path.basename(image_path)}")
        return best_rot, True
    return best_rot, False
