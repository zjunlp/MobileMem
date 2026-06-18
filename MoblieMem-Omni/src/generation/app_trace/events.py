"""App-trace event-to-apptype assignment / selection (pure, keyword-scored)."""


def assign_all_events_to_types(events, app_types):
    """Assign every event to one app type by keyword score for --all-events mode."""
    keywords = {
        "book":     ["读", "书", "阅读", "read", "book", "study", "学习", "图书", "文学", "小说", "知识"],
        "music":    ["音乐", "歌", "听歌", "music", "listen", "concert", "演唱", "歌手", "专辑", "演奏"],
        "video":    ["视频", "看", "watch", "video", "电影", "film", "剧", "vlog", "综艺", "直播", "动漫"],
        "shopping": ["买", "购", "shop", "buy", "order", "包裹", "快递", "商品", "淘宝", "消费", "外卖"],
    }
    assignment = {t: [] for t in app_types}
    rr_index = 0
    for ev in events:
        text = (ev.get('event_name', '') + ' ' + ev.get('description', '')).lower()
        scores = {t: sum(1 for kw in keywords[t] if kw in text) for t in app_types}
        best_score = max(scores.values())
        if best_score > 0:
            # Tie on the highest score goes to the first app_type for determinism.
            best_type = next(t for t in app_types if scores[t] == best_score)
        else:
            # No keyword match: distribute evenly by round-robin.
            best_type = app_types[rr_index % 4]
            rr_index += 1
        assignment[best_type].append(ev)
    return assignment


def select_events_for_type(events, app_type, n=2, existing_assigned=None):
    """Select suitable events for this type while avoiding duplicate assignment."""
    if existing_assigned is None:
        existing_assigned = set()

    # Prefer events that already have info for this type.
    already_have = [
        e for e in events
        if f"{app_type}_info" in e and e['event_id'] not in existing_assigned
    ]
    if len(already_have) >= n:
        return already_have[:n]

    # Choose events that have not already been assigned elsewhere.
    candidates = []
    for e in events:
        if e['event_id'] in existing_assigned:
            continue
        if f"{app_type}_info" in e:
            continue
        candidates.append(e)

    # Sort by relevance to the type using simple keyword matching.
    keywords = {
        "book": ["读", "书", "阅读", "read", "book", "study", "学习", "图书", "文学"],
        "music": ["音乐", "歌", "听", "music", "listen", "concert", "演唱", "乐"],
        "video": ["视频", "看", "watch", "video", "电影", "film", "剧", "vlog"],
        "shopping": ["买", "购", "shop", "buy", "order", "包裹", "快递", "商品", "淘宝"],
    }

    def relevance(ev):
        desc = (ev.get('event_name', '') + ' ' + ev.get('description', '')).lower()
        return sum(1 for kw in keywords.get(app_type, []) if kw in desc)

    candidates.sort(key=relevance, reverse=True)

    need = n - len(already_have)
    selected = already_have + candidates[:need]
    return selected[:n]
