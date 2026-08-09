"""MemWeb backend for prepared samples and the raw Hugging Face dataset."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import zipfile
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("MEMWEB_DATA_DIR", str(APP_DIR.parent))).expanduser().resolve()
STATIC_DIR = APP_DIR / "static"
PREPARED_DATA_FILE = DATA_DIR / "stage5_all_users.json"
PREPARED_QUESTION_GLOB = "stage6_questions_uuid*.jsonl"
RAW_DATA_FILES = (DATA_DIR / "omni" / "data.jsonl", DATA_DIR / "data.jsonl")
RAW_QUESTION_FILES = (
    DATA_DIR / "omni" / "questions.jsonl",
    DATA_DIR / "questions.jsonl",
)
IMAGE_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}
IMAGE_GROUP_ALIASES = {
    "book": "book_screenshots",
    "chat records": "chat_records",
    "event": "camera_photos",
    "friend": "posts",
    "group_chat": "chat_records",
    "group_chat_members": "kg_reference_photos",
    "money": "transaction_records",
    "music": "music_screenshots",
    "person": "pensona_reference_photos",
    "scenery": "others",
    "shopping": "shopping_records",
    "shopping records": "shopping_records",
    "ticket": "ticket_records",
    "transaction records": "transaction_records",
    "video": "video_screenshots",
}


def first_existing(paths: tuple[Path, ...]) -> Optional[Path]:
    return next((path for path in paths if path.is_file()), None)


def decoded_zip_name(info: zipfile.ZipInfo) -> str:
    """Recover UTF-8 or GB18030 names from ZIPs without a Unicode flag."""
    name = info.filename
    if not info.flag_bits & 0x800 and not name.isascii():
        raw_name = name.encode("cp437")
        for encoding in ("utf-8", "gb18030"):
            try:
                name = raw_name.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    return name.replace("\\", "/")


class Store:
    """全局数据缓存：进程启动时一次性载入磁盘文件，之后只读。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.loaded = False
        self.summary: Dict[str, Any] = {}
        self.users: Dict[int, Dict[str, Any]] = {}
        self.questions: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.errors: List[str] = []
        self.data_mode = "unknown"
        self.data_file: Optional[Path] = None
        self.question_files: List[Path] = []

    def load(self) -> None:
        with self._lock:
            if self.loaded:
                return
            if PREPARED_DATA_FILE.is_file():
                self.data_mode = "prepared"
                self._load_prepared_data(PREPARED_DATA_FILE)
            else:
                raw_data_file = first_existing(RAW_DATA_FILES)
                if raw_data_file:
                    self.data_mode = "huggingface"
                    self._load_raw_data(raw_data_file)
                else:
                    expected = ", ".join(str(path) for path in (PREPARED_DATA_FILE, *RAW_DATA_FILES))
                    self.errors.append(f"未找到数据文件，检查以下路径: {expected}")

            self._load_questions()
            if not self.summary:
                self.summary = {
                    "sample_only": self.data_mode != "huggingface",
                    "user_count": len(self.users),
                    "session_count": sum(user["session_count"] for user in self.users.values()),
                    "description": (
                        "Raw MobileMem-Omni dataset loaded from Hugging Face."
                        if self.data_mode == "huggingface"
                        else "Prepared MobileMem dataset."
                    ),
                }
            self.loaded = True

    def _register_user(
        self,
        uid: int,
        record: Dict[str, Any],
        source_file: Path,
        source_size_bytes: Optional[int] = None,
        session_count: Optional[int] = None,
    ) -> None:
        sessions = record.get("sessions") or []
        self.users[int(uid)] = {
            "user_id": int(uid),
            "language": record.get("language"),
            "source_file": str(source_file),
            "source_size_bytes": source_size_bytes,
            "session_count": len(sessions) if session_count is None else session_count,
            "profile": record.get("Basic_Profile") or {},
            "init_state": record.get("Init_State") or {},
            "important_dates": record.get("Important_Dates") or {},
            "sessions": sessions,
            "session_stats_summary": record.get("session_stats_summary") or {},
        }

    def _load_prepared_data(self, path: Path) -> None:
        self.data_file = path
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.summary = data.get("summary", {}) or {}
        for u in data.get("users", []) or []:
            uid = u.get("user_id")
            if uid is None:
                continue
            records = u.get("records") or []
            if not records:
                continue
            record = dict(records[0])
            if len(records) > 1:
                record["sessions"] = [
                    session
                    for source_record in records
                    for session in (source_record.get("sessions") or [])
                ]
            self._register_user(
                int(uid),
                record,
                path,
                source_size_bytes=u.get("source_size_bytes"),
                session_count=u.get("session_count"),
            )

    def _load_raw_data(self, path: Path) -> None:
        self.data_file = path
        source_size = path.stat().st_size
        with open(path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    self.errors.append(f"{path}:{line_number} JSON 解析失败: {error}")
                    continue
                uid = record.get("uuid")
                if uid is None:
                    self.errors.append(f"{path}:{line_number} 缺少 uuid")
                    continue
                self._register_user(int(uid), record, path, source_size_bytes=source_size)

    def _load_question_file(self, path: Path, fallback_uid: Optional[int] = None) -> None:
        self.question_files.append(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as error:
                        self.errors.append(f"{path}:{line_number} JSON 解析失败: {error}")
                        continue
                    uid = record.get("uuid", record.get("user_id", fallback_uid))
                    if uid is None:
                        self.errors.append(f"{path}:{line_number} 缺少 uuid")
                        continue
                    questions = record.get("questions") if isinstance(record, dict) else None
                    if isinstance(questions, list):
                        self.questions[int(uid)].extend(questions)
                    elif isinstance(record, dict):
                        self.questions[int(uid)].append(record)
        except OSError as error:
            self.errors.append(f"读取 {path} 失败: {error}")

    def _load_questions(self) -> None:
        pattern = re.compile(r"stage6_questions_uuid(\d+)\.jsonl$")
        prepared_paths = sorted(DATA_DIR.glob(PREPARED_QUESTION_GLOB))
        if prepared_paths:
            for path in prepared_paths:
                match = pattern.search(path.name)
                if match:
                    self._load_question_file(path, fallback_uid=int(match.group(1)))
            return

        raw_question_file = first_existing(RAW_QUESTION_FILES)
        if raw_question_file:
            self._load_question_file(raw_question_file)
        else:
            self.errors.append("未找到问题文件")


class ImageStore:
    """Read images from an extracted directory or directly from image.zip."""

    def __init__(self) -> None:
        self.directory: Optional[Path] = None
        self.archive_path: Optional[Path] = None
        self.archive: Optional[zipfile.ZipFile] = None
        self.archive_members: Dict[str, zipfile.ZipInfo] = {}
        self.archive_groups: Dict[int, Dict[str, List[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._archive_lock = threading.Lock()
        self.errors: List[str] = []

    @property
    def source(self) -> Optional[str]:
        if self.directory:
            return str(self.directory)
        if self.archive_path:
            return str(self.archive_path)
        return None

    def load(self) -> None:
        directory_candidates = (DATA_DIR / "image", DATA_DIR / "omni" / "image")
        self.directory = next((path for path in directory_candidates if path.is_dir()), None)
        if self.directory:
            return

        archive_candidates = (DATA_DIR / "omni" / "image.zip", DATA_DIR / "image.zip")
        self.archive_path = first_existing(archive_candidates)
        if not self.archive_path:
            return

        try:
            self.archive = zipfile.ZipFile(self.archive_path)
            for info in self.archive.infolist():
                if info.is_dir():
                    continue
                normalized = decoded_zip_name(info).lstrip("./")
                match = re.search(r"(?:^|/)image/(uid\d+)/([^/]+)/([^/]+)$", normalized)
                if not match:
                    match = re.search(r"(?:^|/)(uid\d+)/([^/]+)/([^/]+)$", normalized)
                if not match:
                    continue
                uid_dir, group, name = match.groups()
                relative = f"{uid_dir}/{group}/{name}"
                self.archive_members[relative] = info
                self.archive_groups[int(uid_dir[3:])][group].append(name)
            for groups in self.archive_groups.values():
                for names in groups.values():
                    names.sort()
        except (OSError, zipfile.BadZipFile) as error:
            self.errors.append(f"无法读取图片压缩包 {self.archive_path}: {error}")
            self.close()

    def close(self) -> None:
        if self.archive:
            self.archive.close()
            self.archive = None

    def groups_for_user(self, uid: int) -> Dict[str, List[str]]:
        if self.directory:
            base = self.directory / f"uid{uid}"
            if not base.is_dir():
                return {}
            return {
                directory.name: sorted(path.name for path in directory.iterdir() if path.is_file())
                for directory in sorted(path for path in base.iterdir() if path.is_dir())
            }
        return {
            group: list(names)
            for group, names in sorted(self.archive_groups.get(uid, {}).items())
        }

    def response(self, uid: int, group: str, name: str) -> Any:
        uid_dir = f"uid{uid}"
        group = IMAGE_GROUP_ALIASES.get(group, group)
        if self.directory:
            base = (self.directory / uid_dir).resolve()
            target = (base / group / name).resolve()
            try:
                target.relative_to(base)
            except ValueError as error:
                raise HTTPException(400, "invalid image path") from error
            if not target.is_file():
                raise HTTPException(404, "image not found")
            return FileResponse(str(target), headers=IMAGE_CACHE_HEADERS)

        if self.archive:
            relative = f"{uid_dir}/{group}/{name}"
            info = self.archive_members.get(relative)
            if not info:
                raise HTTPException(404, "image not found")
            try:
                with self._archive_lock:
                    content = self.archive.read(info)
            except (KeyError, OSError, zipfile.BadZipFile) as error:
                raise HTTPException(404, "image not found") from error
            media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            return Response(
                content=content,
                media_type=media_type,
                headers=IMAGE_CACHE_HEADERS,
            )

        raise HTTPException(404, "image source not available")


store = Store()
image_store = ImageStore()

@asynccontextmanager
async def lifespan(_: FastAPI) -> Any:
    store.load()
    image_store.load()
    try:
        yield
    finally:
        image_store.close()


app = FastAPI(
    title="MobileMem · Dataset Explorer",
    version="2.0",
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
        "data_mode": store.data_mode,
        "image_source": image_store.source,
        "errors": [*store.errors, *image_store.errors],
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
        "data_mode": store.data_mode,
        "data_file": str(store.data_file) if store.data_file else None,
        "question_files": [str(path) for path in store.question_files],
        "image_source": image_store.source,
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
# 图片资源
# ----------------------------------------------------------------------

@app.get("/image/{uid_dir}/{sub}/{name}")
def get_image(uid_dir: str, sub: str, name: str) -> Any:
    match = re.fullmatch(r"uid(\d+)", uid_dir)
    if not match:
        raise HTTPException(400, "invalid uid")
    uid = int(match.group(1))
    _require_user(uid)
    return image_store.response(uid, sub, name)


@app.get("/api/users/{uid}/images")
def list_user_images(
    uid: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(80, ge=1, le=200),
    group: Optional[str] = None,
) -> Any:
    """List a user's images with pagination to keep the full dataset responsive."""
    _require_user(uid)
    all_groups = image_store.groups_for_user(uid)
    group_counts = {key: len(names) for key, names in all_groups.items()}
    selected_groups = (
        {group: all_groups.get(group, [])}
        if group
        else all_groups
    )
    flattened = [
        (group_name, name)
        for group_name, names in selected_groups.items()
        for name in names
    ]
    total = len(flattened)
    start = (page - 1) * page_size
    page_items = flattened[start : start + page_size]
    groups: Dict[str, List[str]] = defaultdict(list)
    for group_name, name in page_items:
        groups[group_name].append(name)
    return {
        "user_id": uid,
        "available": bool(all_groups),
        "url_prefix": f"/image/uid{uid}",
        "group": group or "",
        "group_counts": group_counts,
        "groups": dict(groups),
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total else 1,
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
        port=int(os.environ.get("MEMWEB_PORT", "8766")),
        reload=False,
    )
