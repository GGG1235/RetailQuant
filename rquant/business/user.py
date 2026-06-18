"""
rquant.business.user — 用户管理
- 默认用户（local）：使用现有 data/ 目录下的文件（向后兼容）
- 模拟用户：data/users/{user_id}/ 子目录，完全隔离
- 用户列表持久化到 data/users.json
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .data import _load_json, _save_json

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"

DEFAULT_USER_ID = "local"
DEFAULT_USER_NAME = "本地用户"


@dataclass
class User:
    id: str
    name: str
    type: str  # "local" | "sim"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


def _load_users() -> list[dict]:
    return _load_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    _save_json(USERS_FILE, users)


def _ensure_default_user() -> User:
    """确保默认用户存在，不存在则创建"""
    users = _load_users()
    for u in users:
        if u["id"] == DEFAULT_USER_ID:
            return User(**u)
    default = User(id=DEFAULT_USER_ID, name=DEFAULT_USER_NAME, type="local")
    users.append(
        {
            "id": default.id,
            "name": default.name,
            "type": default.type,
            "created_at": default.created_at,
        }
    )
    _save_users(users)
    return default


def get_default_user() -> User:
    """返回默认本地用户（始终存在）"""
    return _ensure_default_user()


def create_user(name: str = "", type_: str = "sim") -> User:
    """创建新用户（模拟炒股用）"""
    user = User(
        id=str(uuid.uuid4())[:8],
        name=name or f"用户_{str(uuid.uuid4())[:4]}",
        type=type_,
    )
    users = _load_users()
    users.append(
        {
            "id": user.id,
            "name": user.name,
            "type": user.type,
            "created_at": user.created_at,
        }
    )
    _save_users(users)
    get_user_data_dir(user.id).mkdir(parents=True, exist_ok=True)
    return user


def get_user(user_id: str) -> Optional[User]:
    """按 ID 查用户"""
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            return User(**u)
    return None


def list_users() -> list[User]:
    """列出所有用户"""
    return [User(**u) for u in _load_users()]


def delete_user(user_id: str) -> bool:
    """删除用户（默认用户不可删）"""
    if user_id == DEFAULT_USER_ID:
        return False
    users = _load_users()
    users = [u for u in users if u["id"] != user_id]
    _save_users(users)
    return True


def get_user_data_dir(user_id: str) -> Path:
    """返回用户数据目录"""
    if user_id == DEFAULT_USER_ID:
        return DATA_DIR
    return DATA_DIR / "users" / user_id
