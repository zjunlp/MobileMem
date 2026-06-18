"""Appearance feature library (nationality-aware, unified pipeline).

Single source of truth: every feature value is a canonical English semantic key
with a ``{zh, en}`` localization in :data:`LOCALIZE`. Sampling pools
(:data:`POOLS`) are per-nationality-group subsets of those keys, so cultural
specificity is preserved while the data layer stays unified. Rendering is done
once, at the outermost layer, via :func:`get_appearance`, which localizes to the
persona's language (Chinese personas -> Chinese words, others -> English words).

No per-uuid hardcoding: sampling is deterministic per ``uuid`` (seeded), so the
same persona keeps a stable look across runs without baking in a fixed table.
"""

import random

# en values are self-contained prompt words (already include "eyes"/"nose"/...).
FACE = {
    "round":      {"zh": "圆脸",   "en": "round face"},
    "square":     {"zh": "方脸",   "en": "square face"},
    "oval":       {"zh": "鹅蛋脸", "en": "oval face"},
    "melon_seed": {"zh": "瓜子脸", "en": "heart-shaped face"},
    "long":       {"zh": "长脸",   "en": "oblong face"},
    "square_jaw": {"zh": "国字脸", "en": "square-jawed face"},
    "heart":      {"zh": "心形脸", "en": "heart-shaped face"},
    "diamond":    {"zh": "菱形脸", "en": "diamond face"},
}

EYES = {
    "single_eyelid": {"zh": "单眼皮",       "en": "single-eyelid eyes"},
    "double_eyelid": {"zh": "双眼皮",       "en": "double-eyelid eyes"},
    "inner_double":  {"zh": "内双",         "en": "subtle double-eyelid eyes"},
    "phoenix":       {"zh": "丹凤眼",       "en": "upturned phoenix eyes"},
    "almond":        {"zh": "杏眼",         "en": "almond eyes"},
    "big_double":    {"zh": "大眼睛双眼皮", "en": "large double-eyelid eyes"},
    "deep_set":      {"zh": "深邃眼",       "en": "deep-set eyes"},
    "round_eyes":    {"zh": "圆眼",         "en": "round eyes"},
    "hooded":        {"zh": "内勾眼",       "en": "hooded eyes"},
    "wide_set":      {"zh": "宽眼距",       "en": "wide-set eyes"},
    "upturned":      {"zh": "上挑眼",       "en": "upturned eyes"},
}

NOSE = {
    "high_bridge":   {"zh": "高鼻梁",   "en": "high nose bridge"},
    "flat":          {"zh": "塌鼻梁",   "en": "flat nose bridge"},
    "small":         {"zh": "小巧鼻子", "en": "small nose"},
    "straight_tall": {"zh": "挺拔鼻梁", "en": "tall straight nose"},
    "delicate":      {"zh": "秀气鼻子", "en": "delicate nose"},
    "proper":        {"zh": "端正鼻梁", "en": "well-proportioned nose"},
    "broad":         {"zh": "宽鼻梁",   "en": "broad nose"},
    "tall":          {"zh": "高挺鼻梁", "en": "prominent nose bridge"},
    "straight":      {"zh": "直鼻",     "en": "straight nose"},
    "button":        {"zh": "小翘鼻",   "en": "button nose"},
    "aquiline":      {"zh": "鹰钩鼻",   "en": "aquiline nose"},
    "narrow":        {"zh": "窄鼻",     "en": "narrow nose"},
    "roman":         {"zh": "罗马鼻",   "en": "Roman nose"},
}

BODY = {
    "slim":     {"zh": "偏瘦",     "en": "slim build"},
    "balanced": {"zh": "匀称",     "en": "well-proportioned build"},
    "chubby":   {"zh": "微胖",     "en": "slightly plump build"},
    "sturdy":   {"zh": "健壮",     "en": "sturdy build"},
    "slender":  {"zh": "纤细",     "en": "slender build"},
    "slim_fit": {"zh": "苗条",     "en": "slim figure"},
    "athletic": {"zh": "健美",     "en": "athletic build"},
    "average":  {"zh": "中等身材", "en": "average build"},
    "muscular": {"zh": "肌肉型",   "en": "muscular build"},
    "lean":     {"zh": "精瘦",     "en": "lean build"},
}

SKIN = {
    "fair":      {"zh": "白皙",       "en": "fair skin"},
    "wheat":     {"zh": "小麦色",     "en": "wheat-colored skin"},
    "healthy":   {"zh": "健康肤色",   "en": "healthy skin tone"},
    "dark":      {"zh": "偏黑肤色",   "en": "deeper skin tone"},
    "light":     {"zh": "浅肤色",     "en": "light skin"},
    "olive":     {"zh": "橄榄色肤色", "en": "olive skin"},
    "brown":     {"zh": "棕色肤色",   "en": "brown skin"},
    "deep_dark": {"zh": "深色肤色",   "en": "dark skin"},
    "tan":       {"zh": "古铜色肤色", "en": "tan skin"},
}

LOCALIZE = {"face": FACE, "eyes": EYES, "nose": NOSE, "body": BODY, "skin": SKIN}

POOLS = {
    "Chinese": {
        "face": ["round", "square", "melon_seed", "oval", "long", "square_jaw"],
        "eyes": ["single_eyelid", "double_eyelid", "inner_double", "phoenix", "almond", "big_double"],
        "nose": ["high_bridge", "flat", "small", "straight_tall", "delicate", "proper", "broad", "tall"],
        "body": ["slim", "balanced", "chubby", "sturdy", "slender", "slim_fit"],
        "skin": ["fair", "wheat", "healthy", "dark"],
    },
    "western": {
        "face": ["oval", "round", "square", "heart", "long", "diamond"],
        "eyes": ["deep_set", "almond", "round_eyes", "hooded", "wide_set", "upturned"],
        "nose": ["straight", "button", "aquiline", "broad", "narrow", "roman"],
        "body": ["slim", "athletic", "average", "muscular", "lean", "sturdy"],
        "skin": ["fair", "light", "olive", "brown", "deep_dark", "tan"],
    },
}

# Ethnicity hint -> preferred skin semantic keys (used for non-Chinese personas).
ETHNICITY_SKIN_MAP = {
    "african american": ["brown", "deep_dark"],
    "black": ["brown", "deep_dark"],
    "white": ["fair", "light"],
    "caucasian": ["fair", "light"],
    "european": ["fair", "light", "olive"],
    "hispanic": ["olive", "tan", "light", "brown"],
    "latino": ["olive", "tan", "light", "brown"],
    "latina": ["olive", "tan", "light", "brown"],
    "east asian": ["fair", "light"],
    "southeast asian": ["tan", "olive", "light"],
    "south asian": ["brown", "olive", "tan"],
    "middle eastern": ["olive", "tan", "light"],
    "arab": ["olive", "tan", "light"],
    "mixed race": ["light", "olive", "tan", "brown"],
    "biracial": ["light", "olive", "tan", "brown"],
}


def _group(nationality: str) -> str:
    """Map a nationality to a sampling-pool group."""
    return "Chinese" if nationality == "Chinese" else "western"


def localize(feature: str, key: str, lang: str) -> str:
    """Render a canonical feature key into a display word for ``lang`` (zh/en).

    Unknown keys pass through unchanged, so externally supplied (stage0) English
    values are never mangled.
    """
    entry = LOCALIZE.get(feature, {}).get(key)
    if not entry:
        return key
    return entry["zh"] if lang == "zh" else entry["en"]


def get_appearance(uuid, nationality="Chinese", ethnicity_hint="", profile_record=None):
    """Return appearance features as display words in the persona's language.

    Deterministic per ``uuid`` (seeded). Chinese personas get Chinese words,
    others get English words. Non-Chinese personas that carry a richer stage0
    ``appearance`` (hair/ethnicity) have it passed through in English.

    Args:
        uuid: the persona's uuid (seeds the deterministic sampling)
        nationality: "Chinese" -> Chinese words + East-Asian pool; otherwise English
        ethnicity_hint: e.g. "African American", biases skin tone for non-Chinese
        profile_record: stage1 record; may carry a stage0 'appearance' sub-object

    Returns:
        dict with face/eyes/nose/body/skin (non-Chinese stage0 personas also get
        hair_color/hair_style/facial_hair/ethnicity/eye_color, in English).
    """
    lang = "zh" if nationality == "Chinese" else "en"

    # Non-Chinese persona with a structured stage0 appearance: pass through (English).
    if nationality != "Chinese" and profile_record and "appearance" in profile_record:
        app = profile_record["appearance"]
        return {
            "face": app.get("face_shape", "oval face"),
            "eyes": app.get("eye_color", "brown") + " eyes",
            "nose": "straight nose",
            "body": app.get("build", "average build"),
            "skin": app.get("skin_color", "light skin"),
            "hair_color": app.get("hair_color", ""),
            "hair_style": app.get("hair_style", ""),
            "facial_hair": app.get("facial_hair", ""),
            "ethnicity": app.get("ethnicity", ""),
            "eye_color": app.get("eye_color", ""),
        }

    # Otherwise sample deterministically from the per-group pool, then localize.
    rng = random.Random(uuid)
    pool = POOLS[_group(nationality)]

    skin_keys = pool["skin"]
    if lang == "en" and ethnicity_hint:
        hint = ethnicity_hint.lower()
        for key, tones in ETHNICITY_SKIN_MAP.items():
            if key in hint:
                skin_keys = tones
                break

    return {
        "face": localize("face", rng.choice(pool["face"]), lang),
        "eyes": localize("eyes", rng.choice(pool["eyes"]), lang),
        "nose": localize("nose", rng.choice(pool["nose"]), lang),
        "body": localize("body", rng.choice(pool["body"]), lang),
        "skin": localize("skin", rng.choice(skin_keys), lang),
    }


def format_appearance_description(appearance, nationality="Chinese"):
    """Format an appearance dict into a natural-language description."""
    if nationality == "Chinese":
        return f"{appearance['face']}，{appearance['eyes']}，{appearance['nose']}，{appearance['body']}身材，{appearance['skin']}"
    return f"{appearance['face']}, {appearance['eyes']}, {appearance['nose']}, {appearance['body']}, {appearance['skin']}"
