"""MemWeb 后端服务

加载 stage5_all_users.json 与 stage6_questions_*.jsonl，
对外暴露 REST API 供前端可视化使用。
"""
from __future__ import annotations

import json
import os
import re
import threading
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


DATA_DIR = Path(os.environ.get("MEMWEB_DATA_DIR", r"D:\code\memweb"))
STAGE5_FILE = DATA_DIR / "stage5_all_users.json"
STAGE6_GLOB = "stage6_questions_uuid*.jsonl"
IMAGE_DIR = DATA_DIR / "image"
ALLOWED_IMAGE_UIDS = {"uid0", "uid10"}

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"


class Store:
    """全局数据缓存：进程启动时一次性载入磁盘文件，之后只读。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.loaded = False
        self.summary: Dict[str, Any] = {}
        self.users: Dict[int, Dict[str, Any]] = {}
        self.questions: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.errors: List[str] = []

    def load(self) -> None:
        with self._lock:
            if self.loaded:
                return
            self._load_stage5()
            self._load_stage6()
            self.loaded = True

    def _load_stage5(self) -> None:
        if not STAGE5_FILE.exists():
            self.errors.append(f"stage5 文件不存在: {STAGE5_FILE}")
            return
        with open(STAGE5_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.summary = data.get("summary", {}) or {}
        for u in data.get("users", []) or []:
            uid = u.get("user_id")
            if uid is None:
                continue
            records = u.get("records") or []
            record = records[0] if records else {}
            profile = record.get("Basic_Profile") or {}
            init_state = record.get("Init_State") or {}
            important_dates = record.get("Important_Dates") or {}
            sessions = record.get("sessions") or []
            session_stats = record.get("session_stats_summary") or {}
            self.users[int(uid)] = {
                "user_id": int(uid),
                "language": record.get("language"),
                "source_file": u.get("source_file"),
                "source_size_bytes": u.get("source_size_bytes"),
                "session_count": u.get("session_count", len(sessions)),
                "profile": profile,
                "init_state": init_state,
                "important_dates": important_dates,
                "sessions": sessions,
                "session_stats_summary": session_stats,
            }

    def _load_stage6(self) -> None:
        pattern = re.compile(r"stage6_questions_uuid(\d+)\.jsonl$")
        for path in DATA_DIR.glob(STAGE6_GLOB):
            m = pattern.search(path.name)
            if not m:
                continue
            uid = int(m.group(1))
            qs: List[Dict[str, Any]] = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(rec, dict) and "questions" in rec:
                            for q in rec.get("questions") or []:
                                qs.append(q)
                        else:
                            qs.append(rec)
            except OSError as e:
                self.errors.append(f"读取 {path} 失败: {e}")
                continue
            self.questions[uid].extend(qs)


store = Store()

@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    store.load()
    yield


app = FastAPI(
    title="MobileMem · 轨迹样本浏览器",
    version="1.0",
    lifespan=lifespan,
)


# ----------------------------------------------------------------------
# 通用
# ----------------------------------------------------------------------

@app.get("/api/health")
def health() -> Any:
    return {
        "status": "ok",
        "loaded": store.loaded,
        "user_count": len(store.users),
        "errors": store.errors,
    }


@app.get("/api/summary")
def get_summary() -> Any:
    user_ids = sorted(store.users.keys())
    total_questions = sum(len(qs) for qs in store.questions.values())
    return {
        "summary": store.summary,
        "user_ids": user_ids,
        "user_count": len(user_ids),
        "total_sessions": sum(u["session_count"] for u in store.users.values()),
        "total_questions": total_questions,
        "stage5_file": str(STAGE5_FILE),
        "data_dir": str(DATA_DIR),
    }


# ----------------------------------------------------------------------
# 用户
# ----------------------------------------------------------------------

@app.get("/api/users")
def list_users() -> Any:
    rows = []
    for uid, u in sorted(store.users.items()):
        profile = u.get("profile") or {}
        rows.append({
            "user_id": uid,
            "name": profile.get("name"),
            "gender": profile.get("gender"),
            "birth_date": profile.get("birth_date"),
            "language": u.get("language"),
            "session_count": u.get("session_count"),
            "question_count": len(store.questions.get(uid, [])),
        })
    return rows


def _require_user(uid: int) -> Dict[str, Any]:
    if uid not in store.users:
        raise HTTPException(404, f"user {uid} not found")
    return store.users[uid]


@app.get("/api/users/{uid}")
def get_user(uid: int) -> Any:
    u = _require_user(uid)
    profile = u.get("profile") or {}
    sessions = u.get("sessions") or []

    memory_type_counter: Counter = Counter()
    importance_counter: Counter = Counter()
    for s in sessions:
        memory_points = s.get("memory_points")
        if memory_points is None:
            memory_points = (
                (s.get("own_memory_points") or [])
                + (s.get("shared_parent_memory_points") or [])
            )
        for mp in memory_points:
            if mp.get("memory_type"):
                memory_type_counter[mp["memory_type"]] += 1
            if mp.get("importance") is not None:
                importance_counter[str(mp["importance"])] += 1

    return {
        "user_id": uid,
        "profile": profile,
        "init_state": u.get("init_state"),
        "important_dates": u.get("important_dates"),
        "language": u.get("language"),
        "session_count": u.get("session_count"),
        "session_stats_summary": u.get("session_stats_summary"),
        "memory_type_distribution": dict(memory_type_counter),
        "importance_distribution": dict(importance_counter),
        "question_count": len(store.questions.get(uid, [])),
    }


# ----------------------------------------------------------------------
# Sessions
# ----------------------------------------------------------------------

def _session_brief(s: Dict[str, Any]) -> Dict[str, Any]:
    image_refs = s.get("image_refs") or {}
    return {
        "session_id": s.get("session_id"),
        "event_id": s.get("event_id"),
        "parent_event_id": s.get("parent_event_id"),
        "event_name": s.get("event_name"),
        "event_start_time": s.get("event_start_time"),
        "event_end_time": s.get("event_end_time"),
        "dialogue_goal": s.get("dialogue_goal"),
        "dialogue_summary": s.get("dialogue_summary"),
        "dialogue_turn_count": len(s.get("dialogue") or []),
        "memory_point_count": len(
            s.get("memory_points")
            or (
                (s.get("own_memory_points") or [])
                + (s.get("shared_parent_memory_points") or [])
            )
        ),
        "image_candidate_count": len(s.get("image_candidates") or []),
        "event_scene": image_refs.get("event_scene"),
        "event_scene_description": image_refs.get("event_scene_description"),
        "person_avatar": image_refs.get("person_avatar"),
    }


@app.get("/api/users/{uid}/sessions")
def list_sessions(
    uid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=200),
    keyword: str = Query(
        "",
        description="关键字（匹配 event_name / dialogue_summary / dialogue_goal）",
    ),
) -> Any:
    u = _require_user(uid)
    sessions: List[Dict[str, Any]] = u.get("sessions") or []
    kw = (keyword or "").strip().lower()
    if kw:
        def hit(s: Dict[str, Any]) -> bool:
            for k in ("event_name", "dialogue_summary", "dialogue_goal"):
                v = s.get(k) or ""
                if isinstance(v, str) and kw in v.lower():
                    return True
            return False
        sessions = [s for s in sessions if hit(s)]

    total = len(sessions)
    start = (page - 1) * page_size
    end = start + page_size
    items = [_session_brief(s) for s in sessions[start:end]]
    return {
        "user_id": uid,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if page_size else 1,
        "items": items,
    }


@app.get("/api/users/{uid}/timeline")
def get_timeline(uid: int) -> Any:
    u = _require_user(uid)
    items = []
    for s in u.get("sessions") or []:
        items.append({
            "session_id": s.get("session_id"),
            "event_id": s.get("event_id"),
            "event_name": s.get("event_name"),
            "event_start_time": s.get("event_start_time"),
            "event_end_time": s.get("event_end_time"),
            "dialogue_summary": s.get("dialogue_summary"),
        })
    items.sort(key=lambda x: x.get("event_start_time") or "")
    return {"user_id": uid, "count": len(items), "items": items}


@app.get("/api/users/{uid}/sessions/{session_id}")
def get_session(uid: int, session_id: str) -> Any:
    u = _require_user(uid)
    sessions = u.get("sessions") or []
    idx = next(
        (i for i, s in enumerate(sessions) if s.get("session_id") == session_id),
        None,
    )
    if idx is None:
        raise HTTPException(404, f"session {session_id} not found for user {uid}")
    return sessions[idx]


# ----------------------------------------------------------------------
# Questions
# ----------------------------------------------------------------------

@app.get("/api/users/{uid}/questions")
def list_questions(
    uid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    qtype: Optional[str] = None,
    difficulty: Optional[str] = None,
    keyword: str = Query(""),
) -> Any:
    _require_user(uid)
    qs = list(store.questions.get(uid, []))

    if qtype:
        qs = [q for q in qs if q.get("question_type") == qtype]
    if difficulty:
        qs = [q for q in qs if q.get("difficulty") == difficulty]
    kw = (keyword or "").strip().lower()
    if kw:
        def hit(q: Dict[str, Any]) -> bool:
            for k in ("question", "answer"):
                v = q.get(k) or ""
                if isinstance(v, str) and kw in v.lower():
                    return True
            return False
        qs = [q for q in qs if hit(q)]

    total = len(qs)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "user_id": uid,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if page_size else 1,
        "items": qs[start:end],
    }


@app.get("/api/users/{uid}/questions/stats")
def question_stats(uid: int) -> Any:
    _require_user(uid)
    questions = store.questions.get(uid, [])
    qtype: Counter = Counter()
    difficulty: Counter = Counter()
    fmt: Counter = Counter()
    for q in questions:
        if q.get("question_type"):
            qtype[q["question_type"]] += 1
        if q.get("difficulty"):
            difficulty[q["difficulty"]] += 1
        if q.get("question_format"):
            fmt[q["question_format"]] += 1
    return {
        "user_id": uid,
        "total": len(questions),
        "question_type": dict(qtype),
        "difficulty": dict(difficulty),
        "question_format": dict(fmt),
    }


# ----------------------------------------------------------------------
# Relationships
# ----------------------------------------------------------------------

@app.get("/api/users/{uid}/relationships")
def relationships(uid: int) -> Any:
    u = _require_user(uid)
    init_state = u.get("init_state") or {}
    rels = init_state.get("social_relationships") or {}
    me_name = (u.get("profile") or {}).get("name") or f"user_{uid}"

    nodes: List[Dict[str, Any]] = [{"id": me_name, "group": "self", "label": me_name}]
    edges: List[Dict[str, Any]] = []
    seen = {me_name}

    def add_node(name: str, group: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if not name or name in seen:
            return
        seen.add(name)
        node = {"id": name, "group": group, "label": name}
        if extra:
            node.update(extra)
        nodes.append(node)

    if isinstance(rels, dict):
        for group, val in rels.items():
            if isinstance(val, dict) and (
                "relationship_type" in val or "description" in val
            ):
                person_name = group
                relation_type = val.get("relationship_type") or "other"
                add_node(person_name, relation_type, {"meta": val})
                edges.append({
                    "source": me_name,
                    "target": person_name,
                    "relation": relation_type,
                })
                continue
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        name = (
                            item.get("name")
                            or item.get("person")
                            or item.get("relation")
                        )
                        if name:
                            add_node(name, group, {"meta": item})
                            edges.append({"source": me_name, "target": name, "relation": group})
                    elif isinstance(item, str):
                        add_node(item, group)
                        edges.append({"source": me_name, "target": item, "relation": group})
            elif isinstance(val, dict):
                for sub_key, sub_val in val.items():
                    name = sub_key
                    add_node(name, group, {"meta": sub_val})
                    edges.append({"source": me_name, "target": name, "relation": group})
            elif isinstance(val, str):
                add_node(val, group)
                edges.append({"source": me_name, "target": val, "relation": group})

    return {
        "user_id": uid,
        "me_name": me_name,
        "raw_social_relationships": rels,
        "nodes": nodes,
        "edges": edges,
    }


# ----------------------------------------------------------------------
# 图片资源（只允许白名单 uid 下的图片）
# ----------------------------------------------------------------------

@app.get("/image/{uid_dir}/{sub}/{name}")
def get_image(uid_dir: str, sub: str, name: str) -> Any:
    if uid_dir not in ALLOWED_IMAGE_UIDS:
        raise HTTPException(403, f"uid {uid_dir} not exposed")
    base = (IMAGE_DIR / uid_dir).resolve()
    target = (IMAGE_DIR / uid_dir / sub / name).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "image not found")
    return FileResponse(str(target))


@app.get("/api/users/{uid}/images")
def list_user_images(uid: int) -> Any:
    """列出该 uid 已开放的所有图片（按子目录分类）。"""
    uid_dir = f"uid{uid}"
    if uid_dir not in ALLOWED_IMAGE_UIDS:
        return {"user_id": uid, "available": False, "groups": {}}
    base = IMAGE_DIR / uid_dir
    if not base.exists():
        return {"user_id": uid, "available": False, "groups": {}}
    groups: Dict[str, List[str]] = {}
    for sub in sorted(p.name for p in base.iterdir() if p.is_dir()):
        files = sorted(f.name for f in (base / sub).iterdir() if f.is_file())
        groups[sub] = files
    return {
        "user_id": uid,
        "available": True,
        "url_prefix": f"/image/{uid_dir}",
        "groups": groups,
        "total": sum(len(v) for v in groups.values()),
    }


# ----------------------------------------------------------------------
# 静态资源 / 首页
# ----------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> Any:
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(
        {
            "message": "MemWeb backend up.",
            "hint": "前端文件 static/index.html 不存在；接口可用：/api/summary, /api/users, /api/users/{uid}/sessions ...",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=int(os.environ.get("MEMWEB_PORT", "8765")),
        reload=False,
    )
