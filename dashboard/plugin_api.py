"""QQ (OneBot) dashboard plugin — backend API routes, mounted at
``/api/plugins/onebot-platform/``.

设置读写走**宿主正典路径**：plugin.yaml ``config_schema``（Desktop/TUI
设置→插件 hub 同一 schema）+ ``hermes_cli.plugins_settings.save_plugin_settings``
（THE writer，写 ``plugins.entries.onebot-platform.settings``，带锁原子合并）。
GET /config 返回 schema 驱动的生效视图：hub settings > platforms.onebot.extra
> config_schema default；secret（access_token）脱敏为 has_* 布尔且不接受
本端点写入（Desktop hub 的凭证路由或 config.yaml 管理）。

- GET  /status  同进程直取活 adapter（adapter._live_adapter()）：WS 连接
  态 + 主动写闸用量，零网络
- GET  /audit   media/qq-actions.log 尾部（主动写审计）

extra/settings 键都在 adapter.__init__ 读取——写入后需要重启网关生效，
端点显式返回 ``restart_required``。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:  # 热加载口径：onebot_utils/adapter 改动免重启（与 adapter 同款）
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

_PLUGIN_ID = "onebot-platform"


def _plugin_dir() -> Path:
    """插件根目录（dashboard/ 的上一级）；plugin.yaml/config_schema 在此。"""
    return Path(__file__).resolve().parent.parent


def _schema() -> Dict[str, Dict[str, Any]]:
    from hermes_cli.plugins_settings import _manifest_config_schema

    return _manifest_config_schema(_plugin_dir())


def _effective_config() -> Dict[str, Any]:
    """schema 驱动的生效视图：hub settings > platforms.onebot.extra > default。

    secret 字段脱敏为 ``has_<key>`` 布尔（值只存 .env，永不回显）。
    """
    from hermes_cli.config import get_env_value, load_config_readonly
    from hermes_cli.plugins_settings import _field_type, secret_env_name
    from hermes_cli.plugins_state import _plugin_settings_entry

    schema = _schema()
    cfg = load_config_readonly() or {}
    entry = _plugin_settings_entry(cfg, _PLUGIN_ID) or {}
    hub = entry.get("settings")
    hub = hub if isinstance(hub, dict) else {}
    extra = ((cfg.get("platforms") or {}).get("onebot") or {}).get("extra") or {}
    extra = extra if isinstance(extra, dict) else {}
    out: Dict[str, Any] = {}
    for key, spec in schema.items():
        kind = _field_type(spec)
        if kind == "secret":
            env = secret_env_name(_PLUGIN_ID, key, spec)
            out[f"has_{key}"] = get_env_value(env) is not None
            continue
        value = hub.get(key)
        if value is None:
            value = extra.get(key)
        if value is None:
            value = spec.get("default")
        out[key] = value
    return out


@router.get("/config")
def get_config() -> Dict[str, Any]:
    return {"status": "ok", "config": _effective_config()}


class ConfigPatch(BaseModel):
    values: Dict[str, Any]


@router.put("/config")
def put_config(patch: ConfigPatch) -> Dict[str, Any]:
    values = dict(patch.values or {})
    if "access_token" in values:
        raise HTTPException(
            status_code=400,
            detail="access_token 是 secret：请在 Desktop/TUI 的 设置→插件 编辑（存 .env），"
            "或直接改 config.yaml 的 platforms.onebot.extra.access_token",
        )
    schema = _schema()
    unknown = [k for k in values if k not in schema]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知/不可写键：{', '.join(sorted(unknown))}")
    # 整数键收敛：前端 number 输入给字符串，这里按 schema 转型后再交给
    # save_plugin_settings 的严格类型校验。
    for key, spec in schema.items():
        if key in values and str(spec.get("type") or "").lower() in ("int", "integer"):
            try:
                values[key] = int(values[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} 需为整数")

    from hermes_cli.plugins_settings import save_plugin_settings

    try:
        written = save_plugin_settings(_PLUGIN_ID, _plugin_dir(), values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    log.info("[onebot-dashboard] settings written: %s", written)
    # extra/settings 键都在 adapter.__init__ 读取：写入后需要重启网关生效
    return {"status": "ok", "config": _effective_config(), "restart_required": True,
            "written": written}


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
