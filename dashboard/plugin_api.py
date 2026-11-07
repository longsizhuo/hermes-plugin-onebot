"""QQ (OneBot) dashboard plugin — backend API routes, mounted at
``/api/plugins/onebot-platform/``.

设置页三件事（kanban 先例口径：宿主正典写路径，不发明第二条）：
- GET  /config  读 ``config.yaml`` 的 ``platforms.onebot.extra`` 白名单键
  （凭证类脱敏为布尔；只读不回显）
- PUT  /config  白名单键+类型校验后 ``save_config``（hermes_cli.config
  正典写路径，进程内 mutation lock 同款纪律）
- GET  /status  同进程直取活 adapter（adapter._live_adapter()）：WS 连接
  态 + 主动写闸用量，零网络
- GET  /audit   media/qq-actions.log 尾部（主动写审计）

extra 键都在 adapter.__init__ 读取——写入后需要重启网关生效，端点显式
返回 ``restart_required``，前端横幅提示。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:  # 热加载口径：onebot_utils 改动免重启（与 adapter 同款）
    from onebot_platform import adapter as _adapter_mod
except ImportError:  # pragma: no cover - 独立加载路径兜底
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location(
        "onebot_platform.adapter",
        str(Path(__file__).resolve().parent.parent / "adapter.py"),
    )
    _adapter_mod = _ilu.module_from_spec(_spec)  # type: ignore[assignment]
    _spec.loader.exec_module(_adapter_mod)  # type: ignore[union-attr]

log = logging.getLogger(__name__)

router = APIRouter()

# 设置页可读/可写的 extra 白名单（键 -> 类型）。凭证键单独处理：
# access_token 只暴露 has_token 布尔，不接受回显。
_STR_KEYS = (
    "mode", "host", "url", "bot_qq", "dm_policy", "group_policy",
)
_INT_KEYS = (
    "port", "text_image_threshold", "image_max_size", "max_inbound_file_bytes",
    "interim_recall_seconds", "rate_limit_per_minute",
    "action_rate_per_minute", "action_rate_per_day",
    "outbound_image_max_bytes", "segments_interval_ms",
)
_BOOL_KEYS = (
    "require_mention", "allow_private_hosts", "segments_enabled", "poke_reply",
    "hot_reload",
)
_LIST_KEYS = (
    "allow_from", "group_allow_from", "admin_users", "allow_cidrs",
)
_SECRET_KEYS = ("access_token",)
_WHITELIST = set(_STR_KEYS) | set(_INT_KEYS) | set(_BOOL_KEYS) | set(_LIST_KEYS) | set(_SECRET_KEYS)

# 策略枚举的合法取值（写入口径，越界 400）
_ENUM_KEYS = {
    "mode": {"reverse", "forward"},
    "dm_policy": {"open", "allowlist", "disabled"},
    "group_policy": {"open", "allowlist", "disabled"},
}


def _load_onebot_extra() -> Dict[str, Any]:
    from hermes_cli.config import load_config_readonly

    cfg = load_config_readonly() or {}
    platforms = cfg.get("platforms") or {}
    entry = platforms.get("onebot") or {}
    extra = entry.get("extra") or {}
    return extra if isinstance(extra, dict) else {}


def _save_onebot_extra(extra: Dict[str, Any]) -> None:
    """写回 platforms.onebot.extra（hermes_cli.config 正典写路径）。"""
    from hermes_cli.config import load_config_readonly, save_config

    cfg = load_config_readonly() or {}
    platforms = cfg.setdefault("platforms", {})
    entry = platforms.setdefault("onebot", {})
    entry["enabled"] = bool(entry.get("enabled", True))
    entry["extra"] = extra
    save_config(cfg)


def _redact(extra: Dict[str, Any]) -> Dict[str, Any]:
    """白名单投影 + 凭证脱敏（access_token -> has_token 布尔）。"""
    out: Dict[str, Any] = {}
    for key in _STR_KEYS + _INT_KEYS + _BOOL_KEYS + _LIST_KEYS:
        if key in extra:
            out[key] = extra[key]
    for key in _SECRET_KEYS:
        out[f"has_{key}"] = bool(str(extra.get(key) or "").strip())
    return out


@router.get("/config")
def get_config() -> Dict[str, Any]:
    return {"status": "ok", "config": _redact(_load_onebot_extra())}


class ConfigPatch(BaseModel):
    values: Dict[str, Any]


@router.put("/config")
def put_config(patch: ConfigPatch) -> Dict[str, Any]:
    values = patch.values or {}
    unknown = [k for k in values if k not in _WHITELIST]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知/不可写键：{', '.join(sorted(unknown))}")

    extra = dict(_load_onebot_extra())
    for key, value in values.items():
        if key in _ENUM_KEYS and str(value) not in _ENUM_KEYS[key]:
            raise HTTPException(
                status_code=400,
                detail=f"{key} 取值需为 {' / '.join(sorted(_ENUM_KEYS[key]))}",
            )
        if key in _INT_KEYS:
            try:
                extra[key] = int(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} 需为整数")
        elif key in _BOOL_KEYS:
            extra[key] = bool(value)
        elif key in _LIST_KEYS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise HTTPException(status_code=400, detail=f"{key} 需为字符串数组")
            extra[key] = value
        elif key in _STR_KEYS:
            extra[key] = str(value)
        elif key in _SECRET_KEYS:
            text = str(value or "").strip()
            if text:
                extra[key] = text  # 空串 = 不修改（脱敏面不回显旧值）

    _save_onebot_extra(extra)
    # extra 全部在 adapter.__init__ 读取：写入后需要重启网关生效
    return {"status": "ok", "config": _redact(extra), "restart_required": True}


@router.get("/status")
def get_status() -> Dict[str, Any]:
    adapter = _adapter_mod._live_adapter()
    if adapter is None:
        return {"status": "ok", "running": False}
    connected = False
    try:
        connected = bool(adapter._ws is not None)
    except Exception:
        connected = False
    stats: Dict[str, Any] = {}
    try:
        stats = adapter._write_gate_stats()
    except Exception as exc:  # pragma: no cover - 闸关闭/旧实例
        log.debug("[onebot-dashboard] write gate stats unavailable: %s", exc)
    return {
        "status": "ok",
        "running": True,
        "connected": connected,
        "write_gate": stats,
        "plugin_version": getattr(_adapter_mod, "PLUGIN_VERSION", ""),
    }


@router.get("/audit")
def get_audit(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    entries: List[Dict[str, Any]] = []
    try:
        media_dir = _adapter_mod._ensure_media_dir()
        audit_file = media_dir / "qq-actions.log"
        if audit_file.exists():
            lines = audit_file.read_text(encoding="utf-8").splitlines()
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception as exc:
        log.debug("[onebot-dashboard] audit read failed: %s", exc)
    return {"status": "ok", "entries": list(reversed(entries)), "generated_at": time.time()}
