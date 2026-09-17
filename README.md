# Codex Sounds

轻量 macOS Codex 音效插件：只做三个核心提醒，没有 MCP 服务、后台守护进程或外部 Python 依赖。

| 事件 | 音效 | 接入方式 |
| --- | --- | --- |
| 本轮停止输出 | Glass | `Stop` |
| 发起结构化提问 | Ping | `PreToolUse` 匹配 `request_user_input` / `request_user_input_async` / `AskUserQuestion` |
| 即将请求批准 | Pop | `PermissionRequest` |

## 生效和验证

安装后新建一个 Codex 任务，并审查、信任本插件的 Hooks（CLI 中运行 `/hooks`；桌面端以当前版本的审查提示为准）。安装插件本身并不自动信任 Hooks。

1. 让 Codex 给出一句简短答复，检查 Glass。
2. 请 Codex 使用结构化提问工具提出一个问题，检查 Ping。
3. 在本来就需要批准的正常工作流中检查 Pop。不为音效测试降低权限限制或自动批准操作。

代码单元测试和模拟事件验证不等于桌面端端到端验证；不同 Codex 版本的特殊提问工具路径可能不经过通用 Hooks。聊天正文中的普通问句不触发提问音。

## 设计边界

- `Stop` 代表本轮停止，不代表整个业务目标成功；其他 Stop Hook 继续任务时也可能已经响过。
- 插件不修改审批结果，不继续或阻止任务。播放失败时输出空 JSON，让工作继续。
- 同一回合、同一工具调用去重；没有工具调用 ID 的批准事件仅短时去重，避免后续批准静音。
- 异步提问后三秒内的 Stop 音被抑制，优先保留提问音。
- 所有三个系统音效使用 50% 播放增益，系统音量仍然生效。
- 第一版不判断前后台，不读取系统勿扰状态，不转发远程音频。Hooks 在执行主机播放，远程任务不属于本版支持范围。
- 去重数据库优先写入 Codex 提供的 `PLUGIN_DATA`；兼容回退为用户缓存目录。只保存哈希、事件分类和时间，不保存对话正文。
- 用户可在 Codex 插件界面禁用或卸载；`CODEX_SOUNDS_MUTE=1` 可供受控启动环境静音。

## 开发

Python 3 标准库；macOS 自带 `/usr/bin/afplay` 和系统音效。

在仓库目录运行：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/notify.py --preview complete
python3 scripts/notify.py --preview input
python3 scripts/notify.py --preview approval
```

模拟事件（不播放、不写数据库）：

```sh
printf '%s' '{"hook_event_name":"Stop","session_id":"test","turn_id":"1"}' | python3 scripts/notify.py --dry-run
```

修改后重新安装插件，并新建任务；已安装缓存不会自动跟随源码更新。Hooks 内容发生变化时重新审查、信任。

## 文件结构

- `.codex-plugin/plugin.json`：插件元数据。
- `hooks/hooks.json`：三个 Hook。
- `scripts/notify.py`：分类、去重和系统音效播放。
- `tests/test_notify.py`：分类、并发去重、输出契约等测试。

## 参考

- [OpenAI 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks)

## 本机安装记录

源码与本地 Git 仓库位于 `/Users/wayne/Documents/work/code/llm/codex-sounds`（本 README 所在目录）；个人插件源通过用户 plugins 目录中的符号链接指向同一份源码，不维护第二份代码。请保留源码目录。

插件标识：`codex-sounds@personal`。已安装到 Codex 缓存，Hooks 的首次信任由用户完成。尚未创建远程仓库，也未推送代码。

更新时先使用 plugin-creator 的 `update_plugin_cachebuster.py` 更新版本缓存标记，再执行 `codex plugin add codex-sounds@personal`。
