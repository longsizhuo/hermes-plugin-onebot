# OneBot 适配器开发日志

> QQ 机器人（Hermes × NapCat / OneBot 11）适配器开发全记录
> 起始：2026-08-12 ｜ 最近更新：2026-09-16

## 0. 开发规范（用户要求，2026-08-13 起）

1. **能外置的模块就外置**：纯逻辑/可复用函数拆到 `onebot_utils.py` 或独立模块，不放 adapter.py
2. **adapter.py 尽量不动**：仅当功能在外部模块无法实现时才改（需实例状态/连接/协议交互）
3. **所有改动必须写本日志**：时间线、根因、修复、验证

---

## 1. 项目概述

Hermes 的 QQ 渠道通过 **OneBot 11 协议**接入 NapCat（Docker 部署），本插件实现完整平台适配器：

```
NapCat (QQ)  ←— 反向 WS —→  OneBotAdapter (adapter.py)  ←— Hermes Gateway
                                    │
                                    ├─ onebot_utils.py  (纯函数：CQ 解析/分段/Markdown/表情/字体/chat_id)
                                    └─ t2i_render.py    (AstrBot 风格文字图渲染器)
```

- **形态**：用户级插件 `~/.hermes/plugins/onebot/`（独立于 Hermes 源码，升级无覆盖风险）
- **协议**：OneBot 11（兼容 NapCat / Lagrange / LLOneBot / go-cqhttp）
- **连接**：反向 WebSocket `ws://0.0.0.0:8643/ws`（NapCat ws-reverse）
- **授权**：`ONEBOT_ALLOWED_USERS` 白名单（仅 123456789）；群聊需 @ 或回复触发
- **代码规模**：adapter.py 1414 行 / onebot_utils.py 249 行 / t2i_render.py 1129 行

---

## 2. 架构与模块

### 2.1 adapter.py — 平台适配器（OneBotAdapter : BasePlatformAdapter）

| 区域 | 方法 | 说明 |
|---|---|---|
| 连接生命周期 | `connect/disconnect`、`_start_reverse_server`、`_connect_forward_once`、`_forward_read_loop`、`_forward_reconnect` | 反向 WS 服务 + 可选正向 WS 连接 + 自动重连 |
| 入站 | `_handle_frame`、`_process_message`、`_parse_content`、`_parse_message_array` | 段数组优先解析（回退 CQ 字符串），CQ 反转义，图片/语音/视频/引用处理 |
| 媒体入站 | `_resolve_image`、`_download_image`、`_download_media`、`_download_audio`、`_shrink_image` | url/base64/file/hash 四路取图；图片压缩 ≤2048px；语音下载转 WAV |
| 出站 | `send`、`_send_media`、`send_image(_file)`、`send_multiple_images`、`send_voice`、`send_video`、`send_document` | 分段、t2i 转图、批量图 ≤9 张、媒体 base64 |
| 扩展 API | `send_typing/stop_typing`（NapCat set_input_status）、`_handle_group_history`（HTTP /api/group_history）、`send_forward_msg`（[[qq_forward]]） | |
| 回复周期合并 | `_settle_loop_buffer` | loop 中间消息 → 合并转发 + 撤回（见 §5.7） |
| 引用取图 | `_process_message` 内 get_msg 分支 | 引用消息自动取原文文本 + 图片（见 §5.6） |
| 工具 | `_call_action`（echo/future 请求-响应）、`_file_to_base64`、`_parse_forward_blocks` | |

### 2.2 onebot_utils.py — 可热加载纯函数模块（2026-08-13 从 adapter 拆出）

| 函数 | 职责 |
|---|---|
| `_cq_unescape` | CQ 反转义（&amp; → &、&#91; → [、&#93; → ]、&#44; → ,） |
| `_split_reply` / `DEFAULT_SPLIT_LENGTH` / `_SENTENCE_BOUNDS` | 长消息按标点分段（≤100 单条、100–150 分段、>150 转图） |
| `strip_markdown` / `_inline_markdown` | QQ 不渲染 Markdown，发前剥离（保留 `[[qq_forward]]` 等内部标记） |
| `_FACE_EMOJI` | QQ 表情 id → emoji 映射表 |
| `_ttc_sc_index` / `_build_font_chain` | Noto CJK ttc 简体索引 + 字体回退链 |
| `_build_chat_id` / `_split_chat_id` | chat_id 编解码（private:123456789 / group:123456789） |
| CQ 正则表 | `_CQ_IMAGE_RE`、`_CQ_RECORD_RE`、`_CQ_AT_RE`、`_CQ_REPLY_RE`、`_CQ_FACE_RE`、`_CQ_ANY_RE`、`_FORWARD_RE` |

### 2.3 t2i_render.py — AstrBot 风格文字图渲染器

- 架构：**MarkdownParser → 元素列表 → calculate_height/render 两遍流程**（AstrBot local_strategy.py 元素化架构）
- 规格：白底 800px、正文 26px、顶栏 #002FA7 蓝条白字 52px（anchor=lm）、页脚 "Powered by Hermes"
- 能力：标题/粗体/斜体/删除线/行内代码/引用/无序列表/有序列表/**表格**（AstrBot 没有）/emoji
- 排版：中文标点禁则、行内样式整体换行、字形级字体回退链、逐字符测量
- 表格：表头灰底、网格线、交替行底色、自适应列宽拉伸、单元格居中、超宽换行

---

## 3. 开发时间线

### 2026-08-12（主体开发日，9 次提交 → PR #84202）

| 时间 | 工作 |
|---|---|
| 09:52–11:00 | 适配器主体：反向 WS、私聊/群聊、白名单、CQ 解析、Markdown 剥离 |
| 上午 | 语音转写（ffmpeg→faster-whisper small）、正在输入提示、图片压缩 |
| 12:00 前后 | NapCat Docker 部署、扫码登录、全链路打通（ws://192.168.5.74:8643/ws） |
| 13:00–13:05 | 出站媒体测试：语音条、URL 图片直发、批量图片、合并转发 [[qq_forward]] |
| 13:44 | **CQ 反转义根因修复**：图片 URL 中 `&` 被转义为 `&amp;` 导致 CDN 拒绝下载 |
| 14:00–15:00 | 文字图渲染器 t2i_render.py（AstrBot 风格，>150 字转图）+ 顶栏 "To 昵称" |
| 14:43 | 斜体截断修复（AFFINE 变换预留 4px→8px） |
| 14:54 | 表格列宽拉伸占满 + 标题高度按渲染字号测量 |
| 15:00+ | ttc 字体变体 bug 修复（`_ttc_sc_index` 索引错位 → 简体字形正确） |
| 晚间 | **9 次提交**（+2983 行 / 9 文件）：结构化解析、图片根因修复、渲染器迭代 ~10 轮；文档 qq-onebot.md |
| 22:48 | 提交完成，PR #84202 OPEN、MERGEABLE（P3 排队等待 review） |

### 2026-08-13（打磨日）

| 时间 | 工作 |
|---|---|
| 04:00 前 | emoji 彩色化全链路：fontTools 从 NotoColorEmoji CBDT 表抠位图（136×128 RGBA），替代 PIL 直载（仅 109px 且渲染空白）；ZWJ 分裂/区域指示符为已知限制 |
| 05:xx | inline code 中文过大修复：`_code_font_size` 26→22px、垂直居中、mono 下移 2px、emoji 缩放 |
| 07:5x | **热加载机制**：adapter 层 mtime 检测 + importlib.reload（t2i_render.py 保存即生效，实测页脚颜色切换验证） |
| 08:1x | **onebot_utils.py 拆分**：纯函数从 adapter 拆出 + `_load_onebot_utils()` 同款热加载；8 组函数验证通过、SyntaxError 自动回退旧模块 |
| 08:3x | 右侧溢出第一轮修复：测量宽与绘制起点统一（引用 -35/无序 -45/有序 -55/表格 -30），表格网格线右缘 794→790 |
| 09:00 | 胶囊高度加大（padding 3→5px，内部 32→36px）+ 行高加大（正文 +12=38px、引用/列表 +10=36px、表格 +14=40px） |
| 09:1x | **引用内长代码溢出修复**：split_to_fit 对 InlineCode 用代码字体测量（width_fn 参数化） |
| 09:2x | **标点禁则超宽修复**：标点放不下时带宿主字下移（不落行首也不出界） |
| 09:3x | **空格回退 bug 修复**：last_space=0 时切出空 head，回退前检查 head 非空且 new_w ≤ max_width |
| 09:4x | **跨元素行首禁则修复**：纯文本段剥离开头标点前缀吸附、正文换新行（`expect_edits` 行 792px 溢出根因） |
| 09:4x | **引用消息取图+取文本**：reply 段 → get_msg API → 原消息文本+图片带回（图片/语音/视频三种媒体均支持） |
| 09:5x | **loop 消息合并转发+撤回**：interim 缓冲 → final 到达时 send_forward_msg + delete_msg；网关 `_send_commentary` 补 interim 标记 |
| 11:1x | **PR #84202 同步**：引用取文/loop 合并/热加载/utils 拆分全部推入 PR（commit c98e1fb99，+949/-321，6 文件）；测试 32→36（新增引用取文、群/私聊/单条合并 4 用例）；文档 qq-onebot.md 增 3 章节；stream_consumer 127 测试无破坏 |
| 11:3x | **鲁棒性检查 + 6 项修复**（commit 4e185a624）：① /tmp/hermes_onebot 临时媒体 6h 过期清理（`_cleanup_tmp_files`，原只写不删会无限堆积）② WS 断线时 pending action futures 立即 set_exception（原干等 wait_for 10-30s + 泄漏）③ 断线关闭旧 aiohttp session（连接泄漏）④ 重连任务去重（并发断线会双 WS 连接，NapCat 只响应第一条→消息丢失）⑤ `_send_media` 的 int(target) ValueError 兜底（原在 try 外会炸到 gateway）⑥ loop 缓冲 5 分钟无 final 自动丢弃（`_loop_buffer_ts` 原只写不读） |
| 12:2x | **群聊权限分级**（commit 0433e321b，PR 第 12 提交，测试 36→43）：`enforces_own_access_policy=True`（gateway 信任 adapter 名单）＋`group_policy: allowlist`+`group_allow_from` 按群号放行（群成员无需逐个加白名单）＋`admin_users` 角色判定（回退 ONEBOT_ALLOWED_USERS）＋member 群消息注入 `[受限用户:仅问答]` 前缀（软限制，platform_hint 声明禁文件/终端/配置/HA/跨平台/cron）＋member 斜杠命令事件构造前拦截（@提及前缀先剥离再判；`/tmp/x` 路径不误伤）＋member 私聊拒绝（`dm_policy: allowlist` 关闭 pairing 入口）＋出站敏感意图审计（`scan_sensitive` + WARNING 日志，软限制兜底观测） |
| 12:4x | **用户档案（独立模块，仅本地，不进 PR）**：群聊消息按 QQ 号自动记录到 `profiles/<qq>.jsonl`（JSONL 追加：ts/昵称/群号/文本，@提及剥离，磁盘持久化重启不丢；只记群聊，注入受限前缀前记录原始文本）＋`read_profile` 尾读最近 N 条＋HTTP 端点 `/api/user_profile?user_id=..&limit=..`（agent 按需拉取总结）。**用户要求独立出来不 push** → 拆成独立模块 `profiles.py`（`_load_profiles()` 同款 mtime 热加载），PR 已回退（force push 0433e321b，档案 commit eb017c04f 从分支移除）。测试坑：热加载 `_load_onebot_utils` 首次调用因 `_UTILS_MTIME=0` 触发 reload 覆盖 monkeypatch——fixture 需同步 mtime 阻止；测试残留会进 git，profiles/ 目录须 gitignore/不入库 |
| 12:5x | **斜杠命令日志（profiles.py 扩展，仅本地）**：根因=斜杠命令被 gateway 核心拦截、不进 session、gateway.log 无命令本身（只有重启动作），重启后 agent 无法得知用户发过什么命令。修复：adapter 拦截点对**所有斜杠命令**（admin+member）写 `profiles/commands.jsonl`（ts/用户/昵称/chat/命令原文/blocked 标记），HTTP 端点 `/api/commands` 查询；重启后 agent 可查"谁何时发了什么命令"（含被拦的 member 命令），/restart 后能接续重启前的指令 |
| 13:0x | **NapCat API 白名单代理**（/api/napcat，14 个 action）：`get_group_member_list`/`get_group_member_info`/`get_stranger_info`/`get_forward_msg`/`get_record`/`get_file`/`upload_group_file`/`upload_private_file`/`get_group_root_files`/`get_group_files_by_folder`/`get_group_file_url`/`ocr_image`/`get_ai_characters`/`send_group_ai_record`。`NAPCAT_API_WHITELIST` 常量 + `_handle_napcat_api`：白名单外 403、params 需 JSON 对象否则 400、白名单内透传 `_call_action`（WS echo）。验证：白名单内 200 透传/外 403/坏参数 400 全过 |
| 13:1x | **新面孔自动建档**（profiles.py + adapter，仅本地）：群消息遇到无资料文件的 QQ 号时异步调 `get_group_member_info` 拉名片/性别/年龄/入群时间等存 `profiles/<qq>_info.json`（`save_member_info`/`load_member_info`），不阻塞主流程（create_task）、失败仅 debug 日志；档案从此带静态成员资料打底 |
| 08-14 13:0x | **interim 标记丢失排查 + 恢复**（详见 §4.10）：用户问\"自动撤回还生效吗\"→ 查日志发现最后一次 `interim=True` 停在 08-13 13:23，之后全是 `final=True buf=0`；代码层 adapter 合并/撤回逻辑完好，但 gateway 核心 `stream_consumer._send_commentary` 的 interim 注入不见了（`git status` 干净、文件与官方 HEAD 一致——8-13 下午的补丁被后续 git 操作覆盖，且 reflog 无 8-13 记录）。**教训：live 核心源码补丁不固化就会在下次 pull/恢复时静默丢失，且日志观测（final/interim/buf）是唯一能发现功能静默失效的手段**。修复：重新打补丁（`_meta = dict(self.metadata or {}); _meta[\"interim\"] = True`，注意必须拷贝不污染原 metadata）+ 补丁固化到 `/root/wip/onebot-interim.patch` + 本 DEVLOG §4.10 |

### 2026-09-11（Hermes v0.21.1 升级确认）

| 时间 | 工作 |
|---|---|
| 11:4x | **interim 核心补丁退役**：`hermes update`（160 commits，v0.21.1 @ 45a6101f）提示 8-25 的 update autostash 遗留 7 天未恢复（内容即本补丁的暂存副本）。核对上游代码：`_send_commentary` 已重构至 `stream_consumer_fallback.py` 并**原生注入 `_interim_send=True`**，adapter 对 `interim`/`_interim_send`/`expect_edits` 三 key 均兼容（§loop 合并判定），无需任何改动。结论：**上游已原生实现，本地补丁与 autostash 正式退役**——`git stash drop b4b29246`，`/root/wip/onebot-interim.patch` 留档不删。升级后 gateway（含 yui）重启正常，9119/8644 监听正常 |

---

## 4. 关键决策与坑（按价值排序）

### 4.1 CQ 反转义（_cq_unescape）
- **症状**：用户发图，CDN 拒绝下载（URL 403）
- **根因**：CQ 码中 url 参数的 `&` 被转义为 `&amp;`，NapCat 原样下发
- **修复**：`&amp;`→`&`、`&#91;`→`[`、`&#93;`→`]`、`&#44;`→`,`，应用于 url/属性值/文本

### 4.2 ttc 字体变体索引（_ttc_sc_index）
- **症状**：「路径」的「径」显示异常、「修复」宽度减半
- **根因**：NotoSansCJK-Regular.ttc 含 10 个字体，name 表枚举索引被误当 ttc 集合索引 → 加载了 JP/Mono/HK 变体
- **修复**：正确遍历 `reader.numFonts`，选择名称含 'CJK SC' 且非 Mono 的索引（=2）

### 4.3 彩色 emoji（CBDT 位图）
- **症状**：PIL 直载 NotoColorEmoji 仅 109px 可加载且渲染空白
- **方案**：fontTools 解析 CBDT 表（`cbdt_bitmap_format_17`），提取 136×128 RGBA 位图（PNG offset 9），按字号缩放粘贴
- **细节**：cmap 含 0-9 需码点过滤；粗体双画 `skip_emoji=True` 防 1px 重影；NotoColorEmoji 不进回退链
- **限制**：ZWJ 组合（👨👩👧）分裂、区域指示符（🇨🇳）渲染为字母

### 4.4 测量与绘制一致性（右侧溢出系列）
- **第一轮**：绘制起点 x=10 而测量按 x=0 → 右侧多 10px。统一「测量宽 = 起点 + 可用宽度」：引用 -35、无序 -45、有序 -55、表格 -30；表格网格线右缘 `table_x + table_w`
- **第二轮**：split_to_fit 用普通字体测 InlineCode（724px）而绘制用等宽字体（892px）→ 测量<绘制不拆行。修复：width_fn 参数化，InlineCode 传 `_code_char_width`
- **第三轮**：标点禁则硬塞满行 → 超宽 25px+。修复：标点带宿主字下移（行首变「字。」不违规）
- **第四轮**：文本以空格开头时 last_space=0，回退切出空 head → 整行 780px 溢出。修复：head 非空且 new_w ≤ max_width 才回退，否则硬切
- **第五轮**：跨元素行首禁则把整段（如 `）发送后...`）吸附 → 792px 超宽。修复：纯文本段剥离开头标点前缀吸附，正文换新行

**验证方法论**：像素级扫描（右界 790 判定：非白像素 x>791）+ vision_analyze 视觉复核 + 逻辑断言（每行右缘 ≤ 790）。

### 4.5 热加载体系
- **动机**：改渲染样式/分段规则必须 /restart，迭代慢
- **实现**：adapter 内 `_load_t2i_render()` / `_load_onebot_utils()`：每次调用前 stat mtime，变化则 `importlib.reload` + 锁；reload 失败（SyntaxError）沿用旧模块不崩
- **范围**：t2i_render.py / onebot_utils.py 保存即生效；adapter.py 自身改动需一次 /restart（类方法绑定实例，reload 不更新）
- **热加载源**：`_load_onebot_utils()` 的返回值被 `u.xxx` 动态获取（DEFAULT_SPLIT_LENGTH、_CQ_IMAGE_RE、_FACE_EMOJI、_FORWARD_RE、strip_markdown 等全部经 `u.` 前缀）

### 4.6 引用消息取原文
- **需求**：用户引用消息是为了给 agent 看——要文本，不只是图
- **实现**：reply 段记录 message_id → 调 `get_msg` → 解析原消息段数组/CQ → 文本拼 `[引用]xxx`、图片/语音/视频下载附加
- **限制**：video 段 NapCat 可能只给 hash 无 url（待补 get_video_file API 分支）

### 4.7 loop 消息合并转发+撤回（空间优化）
- **需求**：一次回复中 gateway 每条 loop 发一条消息（3 条文本 + 1 张 t2i 卡），刷屏占空间
- **根因排查链**：
  1. adapter 用 metadata `expect_edits` 判断 interim → 全失败（`_send_commentary` 传的是原始 thread metadata，无标记）
  2. 日志加 `[onebot] send: ... final/interim/meta_keys/buf` 观测 → 确认 meta_keys=[]
  3. 改 gateway 核心 `stream_consumer._send_commentary`：metadata 补 `interim: True`
  4. adapter 判断改为 `is_final = notify or not interim`
- **结算**：interim 纯文本缓冲（(message_id, text)），final 到达时：
  - 缓冲 ≥2 条才合并（单条不值得）
  - 群聊 `send_forward_msg(group_id)` / 私聊 `send_private_forward_msg(user_id)`（NapCat 均支持）
  - 转发成功后才撤回原消息；失败保留原消息不丢内容
- **防护**：新用户消息到达时清空残留缓冲（防跨轮误合并）

### 4.8 其他
- **Markdown 剥离**：QQ 不渲染 Markdown，发前 strip（标题→文本、代码块→引号包裹等），保留内部 `[[qq_forward]]` 标记
- **图片压缩**：入站大图等比压缩 ≤2048px（LANCZOS），透明保 PNG，GIF 取首帧——防 vision 超时
- **语音链路**：QQ 语音 → ffmpeg 转 16kHz WAV → faster-whisper small 转录，失败降级 `[语音]`
- **正在输入**：NapCat 扩展 API `set_input_status`（OneBot 11 标准无此接口），仅私聊，失败静默

### 4.9 interim 标记丢失（核心补丁被覆盖，2026-08-14 排查恢复）
- **症状**：loop 合并转发+撤回不再触发——日志里最后一次 `interim=True` 是 08-13 13:23，此后所有 send 都是 `final=True buf=0`
- **排查链**：① adapter 侧代码完好（`_settle_loop_buffer`/`delete_msg`/`send_forward_msg` 都在）→ ② 问题在 gateway 核心 `stream_consumer._send_commentary` 的 `metadata["interim"]=True` 注入消失 → ③ `git status` 干净、`git diff HEAD` 无差异 → 补丁被后续 git 操作（pull/checkout 恢复）覆盖；reflog 无 08-13 记录，文件回到官方 HEAD
- **修复**：重新打补丁（`_meta = dict(self.metadata or {}); _meta["interim"] = True`）——**必须拷贝 `self.metadata`，不能原地改**（共享引用，会污染后续 final 的 metadata）
- **固化**：补丁文件 `/root/wip/onebot-interim.patch`；本 DEVLOG §3 时间线 + §4.9 记录。**任何 live 核心源码改动必须同步固化 patch + DEVLOG，否则 git pull 后静默失效，唯一发现手段是 `[onebot] send: ... final/interim/buf` 日志观测**
- **退役（2026-09-11）**：上游把 `_send_commentary` 重构至 `stream_consumer_fallback.py` 并原生注入 `_interim_send=True`（v0.21.1 @ 45a6101f 确认），adapter 兼容新旧 key——本地补丁不再需要，patch 文件留档，autostash 已 drop（§3 09-11 条目）

---

## 5. 功能清单（当前状态）

### 入站
- [x] 私聊/群聊（群需 @/回复触发，白名单授权）
- [x] 段数组解析（回退 CQ 字符串），CQ 反转义
- [x] 图片：url/base64/file/hash 四路获取，压缩 ≤2048px
- [x] 语音：下载 → ffmpeg → STT 转写
- [x] 视频：`_download_media` 下载（有 url 时）；hash-only 经 get_video_file 换取，失败降级 `[视频]` 占位（M2 T1）
- [x] 引用消息：自动取原文文本 + 图片/语音/视频
- [x] 表情 id → emoji、@、回复、卡片、戳一戳段类型
- [x] /api/group_history：主动拉群历史（count ≤50/页，message_seq 翻页）

### 出站
- [x] 长消息策略：≤100 单条 / 100–150 按标点分段 / >150 渲染 t2i 文字图（失败回退分段）
### 平台事件与命令（M2 批次新增，2026-09-16）
- [x] notice 事件分发骨架（`_process_notice` + `_NOTICE_HANDLERS` 表驱动）；戳一戳响应（戳 bot 才响应，`poke_reply` 默认 false，per-chat 60s 冷却，send 成功才占冷却）
- [x] request 事件 + 好友申请/群邀请审批：`onebot_requests.json` 台账（0600）、admin 私聊通知、`/approve` / `/reject` 命令（幂等 + processed 重放静默 + 群内审批不泄露台账 + 台账 200 条上限）
- [x] `/model` 文字序号选择器 + `/model <纯数字>` 快照序号解析（网关 ModelPickerSnapshotStore：TTL 300s + 256 LRU）
- [x] ffmpeg 启动检查（连接期探测一次，缺失 WARNING + 安装指引）

### 出站
- [x] 本地图片 base64、URL 图片直发、批量 ≤9 张/条（URL+本地混合）
- [x] 语音（base64→silk）、视频、文件（base64+文件名）
- [x] 合并转发 `[[qq_forward]]`（群 send_forward_msg / 私聊 send_private_forward_msg）
- [x] loop 中间消息合并转发 + 撤回（gateway interim 标记：上游原生 `_interim_send`，本地补丁已退役）
- [x] 正在输入提示（NapCat set_input_status）

### t2i 渲染
- [x] AstrBot 元素化架构，两遍流程
- [x] 彩色 emoji（CBDT 位图）、行内 code 胶囊（#EEF1F8/#2F4882/radius 6/等宽/CJK 22px）
- [x] 表格（表头灰底/网格线/自适应列宽/居中）
- [x] 中文标点禁则、行内样式整体换行、字形级字体回退
- [x] 顶栏 "To 昵称"、页脚 "Powered by Hermes"
- [x] 右侧溢出 5 轮系统性修复（测量=绘制、禁则、空格回退、跨元素标点）

### 运维
- [x] 热加载：t2i_render.py / onebot_utils.py 保存即生效
- [x] NapCat 断线自动重连；session 重置（daily 4:00）等核心机制天然支持
- [x] PR #84202 已推送官方仓库（OPEN、MERGEABLE，P3 排队）

---

## 6. 已知限制 / 待办

1. **ZWJ 组合 emoji 分裂**（👨👩👧→三个）、**区域指示符**（🇨🇳→C+N 字母）——NotoColorEmoji 字体限制
2. ~~**视频引用**：NapCat 可能只给 file hash 无 url，需补 get_video_file API 分支~~ **已修复（2026-09-16，M2 T1，commit 931a7b17d9）**：`_resolve_video` 经 get_video_file 换取视频文件（file/file_id 双参数防御式），失败降级 `[视频]` 占位（见 §13）
3. ~~**cron 投递媒体被核心丢弃**：send_message_tool 媒体白名单不含 onebot（需改核心，已记）~~ **已修复（2026-09-16 复核）**：commit b1465df01d 已把 onebot 纳入核心 `_PLUGIN_STANDALONE_MEDIA` 与 `_MEDIA_PLATFORMS_NOTE`，cron 离进程投递的图片+文本经 `_send_plugin_standalone` → 插件 `_standalone_send` 真实投递；回归测试见 hermes-agent `tests/tools/test_onebot_send_message_media.py`（含端到端 HTTP mock 用例与注册链路用例）
4. **loop 合并** interim 标记：~~依赖本地补丁~~ 已退役（2026-09-11）——上游原生注入 `_interim_send`（见 §4.9 退役条），Hermes 升级不再有覆盖风险
5. **interim 评论合并**：单条评论不合并（缓冲 <2 条跳过），转发本身也占空间
6. 系统级 python3 环境混乱 → 统一用 `/root/.hermes/hermes-agent/venv/bin/python`

---

## 7. 群聊增强（2026-08-13，参考 AstrBot 群聊插件设计，仅本地不进 PR）

调研参考：`astrbot_plugin_group_context`（增量上下文/主动回复/转发展开/图片携带轮数）、
`astrbot_plugin_group_chat_plus`（两层过滤/概率调节器/消息元数据注入/等待窗口）、
Sphere Rapids Group Chat Plus（组合条件回复/请求级工具隔离）。

### 已实施

| 功能 | 实现 | 生效 |
|---|---|---|
| **群消息元数据注入** | `onebot_utils.build_group_message_text`：群消息进 session 前加 `[HH:MM 昵称(QQ)][@我] 内容` 前缀，agent 知道说话人/时间/触发方式；私聊不注入 | adapter.py，/restart |
| **合并转发展开** | `_CQ_FORWARD_RE` + `adapter._expand_forward`：段数组/CQ 检测 forward id → `get_forward_msg` 展开为 `昵称: 内容` 多行文本注入；失败降级 `[合并转发]` 占位 | adapter.py + onebot_utils.py，/restart |

### 调研结论（暂缓）

- **增量上下文**（group_context 思路：session 只带"上一轮后新增"群消息）：Hermes 的 session 由核心管理（全量历史 + 压缩），adapter 层无法干净地增量注入——需要改核心或伪造 event，暂不做
- **双格式**（content 多模态 + prompt 纯文本双通道）：Hermes MessageEvent 无 prompt 通道，适配器只消费 text+media_urls；群聊图片已走 vision 链路，等价能力已具备，无需双格式
- **上下文加提示词**（主动/被动回复注入 system 提示词）：Hermes system prompt 由核心组装，adapter 无法注入；可用 profiles 摘要/技能替代，暂缓

---

## 8. 快速备忘（运维）

```bash
# 插件目录
~/.hermes/plugins/onebot/          # adapter.py / onebot_utils.py / t2i_render.py

# 改渲染/分段规则 → 保存即生效（热加载）
# 改 adapter.py / gateway 核心 → 发 /restart

# 验证编译
/root/.hermes/hermes-agent/venv/bin/python -m py_compile adapter.py onebot_utils.py t2i_render.py

# NapCat（Docker）
# 数据目录 /vol2/1000/docker/napcat；WebUI http://192.168.5.74:6099/webui
# docker restart 会丢登录态（强制退出不落盘）——需要重新扫码/QCE 登录

# 日志
/root/.hermes/logs/gateway.log     # 含 [onebot] send: ... final/interim/meta_keys/buf 观测
```

---

*本日志由开发过程会话记录整理，随迭代持续更新。*

## 9. dsh-onebot 增量回移（2026-08-25，PORTING.md §7.3）

> 双写：dsh 侧见 /root/wip/dsh-onebot/DEVLOG.md。源: PORTING.md（/vol1/1000/杂项/），
> 源码 github.com/mario841859784/dsh-onebot。

### 已完成（提交 a9f10e1b24，69 测试全绿）
- **#5 文件双通道接收**：get_private_file_url 直链 → get_file base64/url 回退；
  file 段注入 [文件:本地路径]；段数组/CQ 双路径；`max_inbound_file_bytes`（默认 20MB）
- **#1 模型工具**：tools.py 7 工具（qq_send_image/voice/video/file/forward +
  napcat_api 15 白名单 + group_history）；provides_tools + register_tools 双注册；
  adapter 新增 /api/napcat、/api/send_media 端点；chat 从参数或 HERMES_SESSION_CHAT_ID 推断
- **#2 interim 90s 自动撤回**：每条 interim 独立计时（`interim_recall_seconds` 默认 90，
  0 关闭），final 未结算即单独撤回；缓冲被 final 结算后任务自愈
- **#3 回合末小结卡**：final 将整轮 interim 渲染为「本轮进展」t2i 卡片 + 撤回原文；
  渲染/发送失败回退合并转发
- **#4 撤回限速 60ms**：delete_msg 批量间隔防 NapCat 超时
- **#6 本地斜杠命令**（admin）：/ocr（最近入站图 → ocr_image）、/mode interim|instant
  （per-chat loop 合并开关）、/id、/ver；其余斜杠交网关
- **#7 t2i 墨水自检**：connect 时字体链检查，缺 CJK 打 WARNING

### 已知限制
- /ocr 依赖 NapCat ocr_image 且图片在 /tmp/hermes_onebot 存活（6h TTL 清理）
- /mode 覆盖仅内存态，重启恢复默认 interim

### 文档同步（2026-08-26）
- 英文用户文档 qq-onebot.md 补全 7 项增量（提交 1b2dcb73a3，+52/-2）：
  Inbound files 双通道、Agent model tools 表（qq_napcat_api 15 白名单 /
  qq_group_history）、per-interim 90s 自动撤回、回合末 t2i 小结卡、
  撤回限速 60ms、admin 本地斜杠命令（/ocr /mode /id /ver）、
  hot_reload 章节补 opt-in 说明（默认关）、extra keys 表补
  max_inbound_file_bytes / interim_recall_seconds。
  已推送 PR #84202。中文 DEVLOG 本节即记录，无需英文化。

### 文档改版（2026-08-26，提交 39f2412918）
- 英文文档从 website/docs/user-guide/messaging/qq-onebot.md 移入插件目录
  改名 plugins/platforms/onebot/README.md（git mv，历史保留 99%）
- 新增中文版 plugins/platforms/onebot/README.zh-CN.md（全量翻译含 7 项增量）
- website/sidebars.ts 移除 qq-onebot 条目；environment-variables.md 链接
  改为指向插件 README（+ 中文版提示）
- 脱敏扫描干净；已推送 PR #84202

## 10. Windows 测试兼容修复（2026-09-15，回应 Chalars1011 的 PR 实测反馈）

Chalars1011 在 Windows 11 + 真实 NapCat 实测：适配器本体连接/收发全通过，62 测试过 / 2 失败（均为测试自身的跨平台问题，非适配器 bug）：

1. `test_inbound_file_falls_back_to_get_file_base64` 硬编码断言 `/tmp/hermes_onebot/`——Windows 落盘是 `%LOCALAPPDATA%\Temp\hermes_onebot`。改为 `tempfile.gettempdir()` 构造路径断言（adapter.py 本身已用 gettempdir，只有测试写死）。
2. `test_ink_check_reports_font_chain` 断言 `cjk is True`——无 Noto CJK 的机器（其 Windows）ink 自检 ok=False 属优雅降级（长回复退纯文本+警告日志），非失败。改为按 `cjk` 分支断言。

修复提交 31bad149bd（tests/plugins/platforms/test_onebot_platform.py，66 passed），已 push 到 fork，PR #84202 自动更新。
注：其余 4 处 `/tmp/hermes_onebot/` 字符串是 mock 返回值（Windows 上仅作字符串比对不落盘），无需改。

## 11. 交接给 dsh（2026-09-16）

用户决定让 dsh 接手 OneBot 适配器后续开发。交接包已生成：
/root/wip/onebot-handoff-dsh/（HANDOFF.md + PR 状态 + 待办清单）。

### 当前状态快照（交接基准）
- PR #84202 OPEN，head=5ff96605f19（fork mario841859784/hermes-agent，分支 feat/onebot-platform）
- worktree：/root/hermes-pr（共享 venv ~/.hermes/hermes-agent/venv）
- 本地生产副本：~/.hermes/plugins/onebot/（与 PR tip 代码一致）
- 测试：66 passed（tests/plugins/platforms/test_onebot_platform.py）

### 待办（Chalars1011 第二轮 review，2026-09-15 issuecomment-5683264142）
1. 【合并前必修】/api/* 三端点无鉴权（/ws 有 Bearer，group_history/napcat/send_media 裸奔；
   send_media 可读本地文件外发；README 示例教 host:0.0.0.0 → LAN 裸奔）
2. forward 模式不起本地 API server，7 个 qq_* 工具无服务可连（tools.py 硬编码 127.0.0.1:8643）
3. 设计取舍：群里回复任何人都算 @（_is_mentioned 对 reply 段无条件 True）→ 建议限定回复 bot 消息
4. minor：README host 默认值漂移（0.0.0.0 vs 代码 127.0.0.1）、/mode 无 override 提示语自相矛盾、
   image_urls 死变量、图片 URL INFO 日志、t2i 无输出尺寸上限

### 交接注意（从本项目历史教训提炼）
- worktree 提交后 push 到 fork remote（不是 origin/upstream，403）
- 修完 #1 建议回复 PR @Chalars1011 请其复测（对方在其 Windows 生产环境真实 NapCat 实测）
- 测试断言临时目录用 tempfile.gettempdir()（勿硬编码 /tmp）

## 12. 第二轮 review 收口：4.1–4.4 处置 + T6 配套（2026-09-16，dsh 接手后首批）

Chalars1011 第二轮 review（issuecomment-5683264142）四项 + 配套项全部处置完毕，落在 hermes-agent 仓 `feat/onebot-platform` 分支（PR #84202）。工作目录 /vol2/1000/ssd/workspace/project2/hermes-agent/，devlog 规范不变：能外置才外置、所有改动写本日志。

### 时间线

| 步骤 | 工作 | 提交 |
|---|---|---|
| T1（review 4.1） | `/api/*` 三端点（group_history/napcat/send_media）补齐鉴权：统一走 `_check_api_auth`——有 token 严格 Bearer 校验、无 token 仅 loopback 放行+逐请求 WARNING、非 loopback 一律 fail-closed 401 | d8a09a4e93 |
| T2（review 4.2） | forward 模式补挂 `/api/*`-only 本地 server（不注册 `/ws`，复用同一鉴权闸门），7 个 qq_* 工具在 forward 模式恢复可用；reverse/forward 互斥，单实例只起一个 server | ddf1529f13 |
| T3（review 4.3） | reply 触发语义收紧（dsh 口径/用户裁决 D2）：仅当被回复者为 bot 自身时才算提及；get_msg 失败/超时/原消息撤回删除等不可判定场景回落旧行为（算提及），防止撤回消息被回复后永不触发 | 82ffc85645 |
| T6（4.1 配套） | qq_* 工具 `/api/*` 请求自动携带 `Authorization: Bearer <token>`（凭证与 adapter 同源：gateway 配置或 `ONEBOT_ACCESS_TOKEN` 环境变量），另做 ok/status 归一化 | 48a1cf6e48 |
| T4（review 4.4） | minor 批次 + 主动加固（见下） | b32044b26f |
| T5（整备收口） | 双语 README 交叉核对、DEVLOG 补记（本节）、测试红线自查、run_tests.sh CI-parity 回归、`_reply_target_id` 外置顺手项、PR 回复草稿（未发送） | 不提交，留编排者验收 |

### T4 minor + 主动加固（对照对比报告 A1改/A3/A4）

- WS 帧上限显式声明：reverse/forward 均设 `max_msg_size=4MiB`，与 aiohttp 3.14.3 默认一致（零行为变化，防依赖库默认值漂移）——对比报告 A1 原判修正后口径（A1改）
- `_handle_reverse_ws` token 比较改 `hmac.compare_digest`（与 `_check_api_auth` 同语义）——A3
- reverse 绑非 loopback 且未配 token 时启动即 WARNING——A4
- 双语 README host 默认值对齐代码 `127.0.0.1`；`0.0.0.0` 仅作必配 token 示例
- `/mode` 无 override 时提示语自相矛盾修复；`image_urls` 死变量清理；图片 URL 下载日志 INFO→debug
- t2i 渲染总高上限 `MAX_RENDER_HEIGHT=8000px`（用户裁决 D3）：超限抛 ValueError，走 adapter.send 既有失败回退——降级分段纯文本。铁律核对位置：检查位于第一遍测量（calculate_height 累加）之后、`Image.new`/任何 draw* 之前，不触碰绘制路径，测量=绘制一致性与右缘 790 判定均不受影响
- 新增 6 测试：/mode 两态、t2i 边界与回退、启动告警

### 测试

- `tests/plugins/platforms/test_onebot_platform.py`：66 → 90 passed（T1–T4 各批新增，Windows 兼容红线保持：临时目录断言用 `tempfile.gettempdir()`、无写死 `~/.hermes`、无 change-detector、mock async 均 `async def`）
- 终局回归 `export HOME=/root && bash scripts/run_tests.sh tests/plugins/platforms/test_onebot_platform.py`：90 passed / 0 failed（CI-parity 口径，8 workers，7.9s）

### 文档

- 双语 README 逐节交叉核对（Token 与网络安全、forward 工具可用性、群 @ 触发、host 默认值、WS 帧上限均一致）；双侧同补 t2i 总高上限 8000px 说明（此前双侧均未提及）
- 顺手项（T3 遗留）：`_reply_target_id` staticmethod 外置到 `onebot_utils.py`（§2.2 热加载纯函数模块，经 `_load_onebot_utils()` 调用，adapter 删除原 staticmethod），调用点与语义逐字不变，测试零修改保持全绿

### 提交链与遗留

- 提交链：d8a09a4e93 → ddf1529f13 → 82ffc85645 → 48a1cf6e48 → b32044b26f（提交者 mario841859784）
- 遗留风险：
  1. 本地生产副本 `/root/.hermes/plugins/onebot/` 未同步本轮改动（含 8 月以来各提交），上线前需人工核对同步
  2. A2 reverse 拨入抖动防护留合并后独立小 PR（行为新增，不混入本批）
  3. t2i 超限降级在极端长文（>8000px）下从卡片变多条文本，用户可感知但符合 D3 裁决；`text_image_threshold: 0` 可整体关闭
  4. T5 各改动未提交，待编排者验收与 M4 门禁评审后统一处置

## 13. M2 批次：T1–T6（2026-09-16，dsh 接手后第二批）

分支 feat/onebot-platform，基于 f1d5d4abcd，批次提交全部未 push。devlog 规范不变：能外置才外置、所有改动写本日志。

### 任务与提交

| 任务 | 工作 | 提交 |
|---|---|---|
| T1 | 视频段 hash-only 时经 get_video_file 换取视频文件：新增 `_resolve_video`（file/file_id 双参数防御式），失败降级 `[视频]` 占位——§6 已知限制#2 就此关闭 | 931a7b17d9 |
| T2 | ffmpeg 启动检查：连接期探测一次，缺失打 WARNING + 安装指引；双语 README 同步（可选依赖/故障排查） | 932d5d9f96 |
| T3 | 媒体白名单验证——§6 已知限制#3 已于 2026-09-16 复核标注"已修复"（原条目已含回归测试位置 hermes-agent `tests/tools/test_onebot_send_message_media.py`，未重复补记） | 02c7487673 |
| T4 | notice 事件分发骨架：`_process_notice` + `_NOTICE_HANDLERS` 表驱动；戳一戳响应——仅戳 bot 才响应、`poke_reply` 默认 false、per-chat 60s 冷却、send 成功才占冷却 | dd7180cefd |
| T5 | request 事件 + 好友申请/群邀请审批：台账落盘 `onebot_requests.json`（0600）、admin 私聊通知、`/approve` / `/reject` 命令、幂等 + processed 重放静默 + 群内审批不泄露台账 + 台账 200 条上限 | 21093d57e0 + 300d6f4c4b |
| T6 | `/model` 文字序号选择器：adapter `send_model_picker`（"← 当前"标记）+ 网关 `ModelPickerSnapshotStore`（TTL 300s + 256 LRU + housekeeping prune）+ `/model <纯数字>` 快照序号解析（精确模型名 > 序号 > 过期/越界报错；flags 不解释；五端 picker 均落账快照） | b48b0a9838 + a2c9403ad2 + cae7278d47 |

### 测试与评审

- 测试 90 → 144（插件 121 + 网关 picker 23）
- 两轮独立评审：同意/部分同意，7 项 🟡 建议全部收口
- 全部 mock 验证；真实 NapCat 端到端待生产验证，重点：get_video_file 参数契约、poke/request 事件格式

### 功能清单/已知限制同步

§5 新增"平台事件与命令（M2 批次新增，2026-09-16）"小节（新增配置键 `poke_reply`，命令 `/approve` / `/reject` / `/model <序号>`），入站视频条目更新；§6 #2 标注已修复。T3 对应 §6 #3 原条目已含回归测试位置，未改动。

## 14. T7：/model 序号选择下沉插件层 + 生产网关 T6 补丁回滚（2026-10-18）

T6 的网关侧快照/序号解析以未提交补丁形态部署在核心层（/root/.hermes/hermes-agent 的 gateway/run.py + gateway/slash_commands_model.py），两度被 `hermes update` 冲掉（2026-09-17 首次、10-16 再丢）。v0.22.2 网关原生已支持 `/model <名> --provider <slug>` 切换链路（prod gateway/run.py L137/L589），本批把序号快照与改写整体下沉插件层，网关回滚原生版——生产从此不依赖任何核心层未提交补丁，免疫 update 冲补丁。

### 任务与提交

| 任务 | 工作 | 提交 |
|---|---|---|
| T7 | adapter：`_MODEL_PICKER_NUMBER_RE` 锚定纯序号命令（flags/非数字/相邻命令名不拦）；`send_model_picker` record-on-success 落账快照（TTL 300s + 256 chat 容量，落账时惰性清理过期项 + 超容量淘汰最旧）；`_maybe_rewrite_model_picker_number`（剥 @提及前缀 → 无快照原样放行 → 过期答复并清快照 → 精确模型名优先放行 → 越界答复有效范围 → 命中改写 `/model <名> --provider <slug>`，判定异常回退原样放行），仅挂 role=="admin" 门下（member 斜杠已在入站门全部拦截）；onebot_utils：新增 `expand_model_picker_entries` 与渲染器逐行同序（providers × models、跳过无模型行）；新增 12 测试（record-on-success、编号与渲染器逐行一致、命中改写、@提及剥除、精确名放行、越界/过期答复不转发、无快照放行、flags 不拦、容量淘汰、惰性清理、member 不可达） | e0827153c7 |

### 测试

- `export HOME=/root && bash scripts/run_tests.sh tests/plugins/platforms/test_onebot_platform.py -j 2`：136 passed / 0 failed（CI-parity 口径，2 workers，14.3s；弱 NAS 限核跑法，未跑全量）

### 部署

- 生产插件 /root/.hermes/plugins/onebot/{adapter.py,onebot_utils.py} 同步 T7 版本（原版备份同名 .bak-t7-20261018）；生产网关 gateway/{run.py,slash_commands_model.py} 由 .bak-t6-20261018 回滚原生版（md5 核对）后删除 T6 备份，git status 回 clean。证据与回滚一行命令见产出目录 .t7-plugin-picker-20261018/REPORT.md。

### 遗留

- 快照为插件进程内存态（不落盘）：网关重启后快照清空，需重发 /model 再回复序号——与 T6 网关版语义一致
- 生产待验证：真实 NapCat 下完整走一遍 /model 列表 → 序号回复 → 会话模型切换成功；错误提示文案的两条路径（过期/越界）人工过一遍

## 15. T9：插件独立为单插件仓 hermes-plugin-onebot（2026-10-18）

onebot 插件自 hermes-agent fork 插件线（feat/onebot-platform-v0.22.2，基线 a8c76ea43d）独立为单插件仓 https://github.com/mario841859784/hermes-plugin-onebot ，生产同批从手工拷贝切换为 `hermes plugins install` 正式安装（切换结果与证据见项目侧 `.t9-standalone-20261018/REPORT.md`）。plugin.yaml（name: onebot-platform / version: 1.1.0）原样保留，config/状态连续；fork 两分支（feat/onebot-platform=e0827153c7、feat/onebot-platform-v0.22.2=a8c76ea43d）原样留存。

### 仓库布局

- 仓根=插件文件（plugin.yaml、__init__.py、adapter.py、onebot_utils.py、t2i_render.py、tools.py、README.md、README.zh-CN.md、本 DEVLOG），与上游单插件仓（hermes-plugin-rocketchat 等）同构；多一目录 tests/（136 用例 + conftest.py），8 个插件文件 md5 与基线一致。
- README 新增「Install (standalone repo) / 安装（独立仓）」节（`hermes plugins install <repo-url>`、代理前缀、署名 mario841859784）与依赖说明：`fonttools>=4,<5` 仅 t2i 文字转图档位需要（Pillow 为宿主自带），主仓 pyproject 的 pin 不随仓携带。不加 LICENSE（作者后续自定）。

### 测试适配（136 用例全数保留）

- in-tree 导入（plugins.platforms.onebot.*）适配为包形态 onebot_platform.*：tests/conftest.py 以生产 loader 同款机制（`spec_from_file_location` + `submodule_search_locations`，对应 hermes_cli/plugins_loader.py::_load_directory_module）从仓根 __init__.py 装配包，相对导入生效；HERMES_HOME/HOME 每用例重定向 tmp_path，不触真实 ~/.hermes/。
- 关键发现：仓根裸导入形态（sys.path 加仓根后 `import tools`）不可用——gateway/platforms/base.py:424 在模块导入期把 hermes-agent 根重新插到 sys.path[0]，其链上模块绑定 core `tools` 包，与插件根级 tools.py 在 sys.modules['tools'] 键上冲突（8 个 test_tools_* 失败）。包形态与生产 hermes_plugins.onebot_platform 命名空间同构，天然隔离。
- 运行方式：`cd tests && HERMES_AGENT_HOME=<hermes-agent 检出> python -m pytest test_onebot_platform.py`（钉版 venv：pytest 9.1.1 / pytest-asyncio 1.3.0；从仓根跑会触发 pytest 9 对根 Package 节点 __init__.py 的导入而失败——连字符目录名使包名解析退化为顶层 `__init__`，相对导入报错，仅影响本地开发跑法，不影响 loader 安装态）。136 passed。

## 16. T11：Teknium review 8 项安全加固（2026-10-19，v1.2.0）

上游 reviewer（Teknium）对 PR（hermes-agent#140979 catalog 收录）给出 CHANGES_REQUESTED 8 项，本节逐项落地；版本 1.1.0→1.2.0（PLUGIN_VERSION 同步，/ver 输出随之更新）。提交拆四个逻辑 commit（e6745b4 → 5fa6a34 → 2f30b46 → 本条），全程生产零触碰。

### Review 逐项处置

| # | review 意见 | 落点 | 处置 |
|---|---|---|---|
| 1 | 本地文件读取一律过 media-delivery validator | adapter.py `_file_to_base64(gate=True)`；send_image_file / send_multiple_images / send_voice / send_video / send_document 五个出站读取点全部 gate；/api/send_media 图片分支对每个本地 source 预校验（拒绝整单 403，不静默丢弃）；adapter.send() 附件循环同 gate | 入站（vision/OCR）读取不过闸（review 只指出站）；拒绝记 WARNING `[onebot] outbound media read blocked by media-delivery validator`；错误串 `* rejected (media-delivery validator denylist), too large, or unreadable` |
| 2 | tools.py chat_id 越权 | tools.py `_session_chat()` 随 /api/send_media 载荷透传会话上下文（工具层无会话角色，判定下沉 adapter）；adapter `_authorize_cross_chat_send()`：无会话（CLI/cron）放行、目标=当前会话放行、目标=ONEBOT_HOME_CHANNEL 放行、private 会话且 QQ ∈ admin_users 放行，其余 403 拒绝 | 群会话无法归因用户 → fail-closed 拒绝；拒绝记 WARNING `[onebot] cross-chat send denied: session=%s target=%s`；qq_napcat_api / qq_group_history 不在 scope（只读/白名单内） |
| 3 | napcat 白名单 upload_group_file/upload_private_file | 保留白名单（功能优先），`_handle_napcat_api` 对这两个 action 的 params.file 做 validator 校验：拒绝 403 `file rejected: local path is not permitted…`，通过则替换为 resolved path | 与 #1 同一 denylist 语义 |
| 4 | 反向/正向 WS 非 loopback 裸奔 | adapter `_validate_bind_security()`：非 loopback host 且 access_token 为空 → raise（`refusing to bind non-loopback host … without access_token`），_start_reverse_server 与 _start_api_server 入口各调一次；connect() 捕获记 ERROR 返回 False（fail-start） | 原 WARNING 降级测试删除，改为 raise 断言；README/README.zh-CN 安全段改为「非 loopback 必须 token，拒绝启动」 |
| 5 | 凭证走 secret_scope | adapter 新模块函数 `_standalone_access_token(extra)`：agent.secret_scope.get_secret("ONEBOT_ACCESS_TOKEN") 优先，异常/为空回落 extra.access_token；tools.py `_access_token()` 同源改造；plugin.yaml optional_env 声明 ONEBOT_ACCESS_TOKEN（password: true） | 无 scope 且未开 multiplex 时 get_secret 读 os.environ → 纯 env 部署行为不变；UnscopedSecretError 场景回落 config |
| 6 | 工具英文优先 | tools.py 全部 handler 结果/错误串、_schemas() 属性描述、_DESCRIPTIONS 改英文（关键结果附一行中文）；相应更新断言中文串的既有测试 | 例：`Sent (message_id=…) / 已发送`、`Send failed: …`、`action … is not whitelisted. Allowed: …` |
| 7 | python_dependencies | plugin.yaml `python_dependencies: ["fonttools>=4,<5"]`；README/README.zh-CN 安装节改为「loader 自动安装，无需手工 pip」 | |
| 8 | /tmp 状态与媒体迁 plugin-data | 新模块函数 `_plugin_data_dir()`=$HERMES_HOME/plugin-data/onebot-platform/、`_media_dir()`（media/ 子目录）、`_ensure_media_dir()`；7 处 /tmp/hermes_onebot 写点全部改 `_ensure_media_dir()`；onebot_nicknames.json / onebot_requests.json 迁入同目录；`_cleanup_tmp_files` 同时清扫新 media 目录与旧 /tmp/hermes_onebot（旧目录只读兼容） | 一次性迁移 `_migrate_legacy_state_file()`：旧位置存在且新位置缺失时 copy2（copy 不 move，旧文件保留作回滚备份），失败降级为新文件起步不 raise；媒体不迁移（瞬态，6h 清扫） |
| — | 非阻塞：私有导入 _AUDIO_EXTS | 移除 `from gateway.platforms.base import _AUDIO_EXTS`，插件自带 `_AUDIO_MIME_TYPES`/`_AUDIO_EXTS`（与 base.py 手工同步） | 顺带消除 validator caution |

### 兼容性说明

- 状态迁移只在「新位置缺失」时发生，升级后首次触碰（构造 /approve 或昵称写盘）自动迁移；回滚 1.1.x 后旧文件仍在，无状态丢失窗口。
- /api/send_media 载荷新增 session_chat 字段：旧工具（1.1.x tools.py）不带该字段 → adapter 视为无会话上下文放行，向后兼容。
- get_secret 缺失（旧 hermes-agent 无 secret_scope 模块）→ ImportError 走回落链，行为同 1.1.x。

### 测试

新增 28 用例（媒体过闸 10、chat_id 越权 7、绑定安全+secret 7、plugin-data 迁移与清扫 5，含 conftest 平台注册修复），断言中文串的既有用例同步更新；`cd tests && HERMES_AGENT_HOME=<hermes-agent> python -m pytest test_onebot_platform.py`：**165 passed**（基线 136）。conftest 补丁说明：T9 后仓内捆绑 stub 目录已清空，Platform("onebot") 无法经捆绑目录扫描解析，改为按生产 loader 语义在 conftest 注册 PlatformEntry（production-mirror，非测试专用 hack）。
