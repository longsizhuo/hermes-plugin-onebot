/**
 * QQ (OneBot) — Dashboard Plugin
 *
 * 设置页：连接 / 策略 / 发送与频控 / segments / 高级 分组表单 + 状态面板
 * （连接态、写闸用量）+ 主动写审计查看。Plain IIFE，无构建步骤；全部请求
 * 走 SDK.fetchJSON（宿主唯一合法鉴权面）。
 *
 * 后端：../plugin_api.py（/api/plugins/onebot-platform/*）。extra 键都在
 * adapter.__init__ 读取——保存后需重启网关生效（横幅提示）。
 */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK) return;

  const { React, hooks, fetchJSON, utils } = SDK;
  const { useState, useEffect, useCallback } = hooks;
  const { Card, CardContent, Badge, Button, Input, Label, Select, SelectOption, Checkbox } = SDK.components;
  const h = React.createElement;

  const PLUGIN = "onebot-platform";
  const BASE = "/api/plugins/" + PLUGIN;

  // 字段定义（组 -> 字段）。type: str/int/bool/list/enum/token
  const GROUPS = [
    {
      title: "连接",
      fields: [
        { key: "mode", label: "模式", type: "enum", options: ["reverse", "forward"],
          help: "reverse = NapCat 拨入；forward = 适配器拨出" },
        { key: "host", label: "监听地址", type: "str", help: "非 loopback 地址必须配 access_token" },
        { key: "port", label: "端口", type: "int" },
        { key: "url", label: "正向 WS 目标", type: "str", help: "forward 模式用，如 ws://127.0.0.1:3001" },
        { key: "bot_qq", label: "机器人 QQ", type: "str", help: "留空则从事件自动学习" },
        { key: "has_access_token", label: "Access Token", type: "secret-badge",
          help: "在 Desktop/TUI 设置→插件 编辑（存 .env）；非 loopback 绑定时必填" },
      ],
    },
    {
      title: "策略",
      fields: [
        { key: "require_mention", label: "群聊仅 @ 时响应", type: "bool" },
        { key: "dm_policy", label: "私聊策略", type: "enum", options: ["open", "allowlist", "disabled"],
          help: "open = 仅管理员" },
        { key: "allow_from", label: "私聊白名单", type: "list", help: "逗号分隔 QQ 号" },
        { key: "group_policy", label: "群聊策略", type: "enum", options: ["open", "allowlist", "disabled"] },
        { key: "group_allow_from", label: "群白名单", type: "list", help: "逗号分隔群号" },
        { key: "admin_users", label: "管理员", type: "list", help: "逗号分隔 QQ 号；回退 ONEBOT_ALLOWED_USERS" },
        { key: "allow_cidrs", label: "SSRF 白名单网段", type: "list", help: "如 192.168.5.0/24；受信任内网协议端用" },
        { key: "allow_private_hosts", label: "整体放行私网下载", type: "bool" },
        { key: "poke_reply", label: "被戳轻提示回复", type: "bool" },
      ],
    },
    {
      title: "发送与频控",
      fields: [
        { key: "text_image_threshold", label: "t2i 卡片阈值（字）", type: "int", help: "超过渲染文字图；0 关闭卡片路径" },
        { key: "outbound_image_max_bytes", label: "卡片 PNG 上限（字节）", type: "int" },
        { key: "rate_limit_per_minute", label: "入站频控（条/分钟/chat）", type: "int", help: "0 关闭" },
        { key: "action_rate_per_minute", label: "主动写频控（条/分钟）", type: "int", help: "0 关闭" },
        { key: "action_rate_per_day", label: "主动写日配额（条）", type: "int", help: "0 关闭" },
      ],
    },
    {
      title: "分段发送工具",
      fields: [
        { key: "segments_enabled", label: "启用 qq_send_segments", type: "bool" },
        { key: "segments_interval_ms", label: "相邻段间隔（ms，0-3000）", type: "int" },
      ],
    },
    {
      title: "高级",
      fields: [
        { key: "image_max_size", label: "入站图片长边上限（px）", type: "int", help: "0 保持原样" },
        { key: "max_inbound_file_bytes", label: "入站文件上限（字节）", type: "int" },
        { key: "interim_recall_seconds", label: "interim 自动撤回（秒）", type: "int", help: "0 关闭" },
        { key: "hot_reload", label: "热加载（仅开发）", type: "bool" },
      ],
    },
  ];

  const listToText = (v) => Array.isArray(v) ? v.join(", ") : (v == null ? "" : String(v));
  const textToList = (t) => t.split(",").map((s) => s.trim()).filter((s) => s !== "");

  function OnebotPage() {
    const [config, setConfig] = useState(null);
    const [values, setValues] = useState({});
    const [status, setStatus] = useState(null);
    const [audit, setAudit] = useState([]);
    const [error, setError] = useState("");
    const [saved, setSaved] = useState(false);
    const [saving, setSaving] = useState(false);

    const refresh = useCallback(async () => {
      try {
        const cfg = await fetchJSON(BASE + "/config");
        setConfig(cfg.config || {});
        setValues(cfg.config || {});
        setError("");
      } catch (e) {
        setError("配置加载失败：" + (e && e.message ? e.message : e));
      }
      try {
        setStatus(await fetchJSON(BASE + "/status"));
      } catch (e) { /* 状态面板非关键 */ }
      try {
        const audit = await fetchJSON(BASE + "/audit?limit=20");
        setAudit(audit.entries || []);
      } catch (e) { /* 审计非关键 */ }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    const setValue = (key, value) => {
      setValues((prev) => ({ ...prev, [key]: value }));
      setSaved(false);
    };

    const save = async () => {
      const payload = {};
      for (const group of GROUPS) {
        for (const f of group.fields) {
          if (!(f.key in values) || f.type === "secret-badge") continue;
          if (f.type === "list") payload[f.key] = textToList(String(values[f.key] || ""));
          else if (f.type === "int") {
            const n = parseInt(String(values[f.key]), 10);
            payload[f.key] = Number.isNaN(n) ? values[f.key] : n;
          } else payload[f.key] = values[f.key];
        }
      }
      setSaving(true);
      try {
        const res = await fetchJSON(BASE + "/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ values: payload }),
        });
        setConfig(res.config || {});
        setValues(res.config || {});
        setSaved(res.restart_required !== false);
        setError("");
        setStatus(await fetchJSON(BASE + "/status").catch(() => status));
      } catch (e) {
        setError("保存失败：" + (e && e.message ? e.message : e));
      } finally {
        setSaving(false);
      }
    };

    const renderField = (f) => {
      const value = values[f.key];
      const common = { id: "ob-" + f.key };
      let control;
      if (f.type === "bool") {
        control = h(Checkbox, {
          ...common,
          checked: Boolean(value),
          onCheckedChange: (checked) => setValue(f.key, Boolean(checked)),
        });
      } else if (f.type === "enum") {
        control = h(Select, {
          ...common,
          value: String(value ?? ""),
          onValueChange: (v) => setValue(f.key, v),
        },
          f.options.map((opt) => h(SelectOption, { key: opt, value: opt }, opt)));
      } else if (f.type === "secret-badge") {
        control = h("div", { className: "pt-2" },
          h(Badge, { variant: value ? "success" : "secondary" }, value ? "已配置（.env）" : "未配置"));
      } else {
        control = h(Input, {
          ...common,
          type: f.type === "int" ? "number" : "text",
          value: f.type === "list" ? listToText(value) : (value == null ? "" : String(value)),
          onChange: (e) => setValue(f.key, e.target.value),
        });
      }
      return h("div", { key: f.key, className: "flex flex-col gap-1" },
        h(Label, { htmlFor: "ob-" + f.key, className: "text-sm" }, f.label),
        control,
        f.help ? h("span", { className: "text-xs text-text-tertiary" }, f.help) : null);
    };

    const gate = status && status.write_gate ? status.write_gate : null;

    return h("div", { className: "mx-auto flex max-w-3xl flex-col gap-4 p-4" },
      // 标题 + 状态面板
      h(Card, null,
        h(CardContent, { className: "flex flex-col gap-2 p-4" },
          h("div", { className: "flex items-center gap-3" },
            h("span", { className: "text-base font-semibold" }, "QQ (OneBot) 状态"),
            status && status.running
              ? h(Badge, { variant: status.connected ? "success" : "warning" },
                  status.connected ? "WS 已连接" : "WS 未连接")
              : h(Badge, { variant: "secondary" }, "适配器未运行")),
          status && status.plugin_version
            ? h("div", { className: "text-xs text-text-tertiary" }, "插件版本 v" + status.plugin_version)
            : null,
          gate
            ? h("div", { className: "flex flex-wrap gap-x-6 gap-y-1 text-xs text-text-secondary" },
                h("span", null, "主动写 分钟 " + gate.minute_used + "/" + gate.minute_limit),
                h("span", null, "今日 " + gate.day_used + "/" + gate.day_limit))
            : null)),
      // 保存横幅 / 错误
      saved ? h("div", { className: "rounded border border-border bg-background px-3 py-2 text-sm" },
        "已保存。配置在适配器启动时读取——重启网关后生效（hermes gateway restart）。") : null,
      error ? h("div", { className: "rounded border border-destructive px-3 py-2 text-sm text-destructive" }, error) : null,
      // 分组表单
      GROUPS.map((group) =>
        h(Card, { key: group.title },
          h(CardContent, { className: "flex flex-col gap-3 p-4" },
            h("div", { className: "text-sm font-semibold" }, group.title),
            h("div", { className: "grid grid-cols-1 gap-3 md:grid-cols-2" },
              group.fields.map(renderField))))),
      // 保存按钮
      h("div", { className: "flex items-center gap-3" },
        h(Button, { onClick: save, disabled: saving }, saving ? "保存中…" : "保存设置"),
        h("span", { className: "text-xs text-text-tertiary" }, "写入 config.yaml platforms.onebot.extra")),
      // 审计
      h(Card, null,
        h(CardContent, { className: "flex flex-col gap-2 p-4" },
          h("div", { className: "text-sm font-semibold" }, "主动写审计（最近 20 条）"),
          audit.length === 0
            ? h("div", { className: "text-xs text-text-tertiary" }, "暂无记录")
            : h("pre", { className: "max-h-64 overflow-auto font-mono text-xs text-text-secondary" },
                audit.map((e, i) => h("div", { key: i },
                  new Date((e.ts || 0) * 1000).toLocaleString() + "  " +
                  (e.allowed ? "✓" : "✗") + "  " + (e.chat_id || "") + "  " + (e.action || "") +
                  (e.reason ? "  " + e.reason : "")))))));
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("onebot-platform", OnebotPage);
  }
})();
