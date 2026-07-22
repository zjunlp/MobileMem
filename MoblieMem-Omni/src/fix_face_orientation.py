"""Backward-compatible shim — the implementation lives in ``backends.faces``.

Historically this root-level module carried its own copy of the face
orientation logic while ``backends/faces.py`` had a second, slightly
different one. The tolerance-based algorithm is now the single
implementation in ``backends.faces``; import from there in new code:

    from backends.faces import auto_orient_face
"""

from backends.faces import (  # noqa: F401
    ORIENTATION_SNAP_TOLERANCE_DEGREES,
    _face_angle_from_kps,
    _eye_line_horizontal_delta_from_kps,
    _upright_face_score_from_kps,
    _orient_face_from_kps,
    _imread_safe,
    _imwrite_safe,
    auto_orient_face,
)
