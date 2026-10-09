# Codex Sounds

适用于 **macOS、Ubuntu/Linux、Windows** 的轻量 Codex 音效插件。只做三个核心提醒，没有 MCP 服务、后台守护进程或第三方 Python 包依赖。

| 事件 | 自带音效 | 接入方式 |
| --- | --- | --- |
| 本轮停止输出 | 柔和上扬音 `complete.wav` | `Stop` |
| 发起结构化提问 | 轻盈双音 `input.wav` | `PreToolUse` 匹配结构化提问工具 |
| 即将请求批准 | 分层三音 `approval.wav` | `PermissionRequest` |

音效由仓库脚本原创合成，不包含 macOS 系统音效；三平台使用同一组短 WAV 文件。当前采用 C「极简电子」风格：圆润 FM 拨弦、轻微音高收束与短空间反射；每个提示音约 1.18 秒，16-bit / 44.1kHz 双声道。

## 新电脑快速安装（不需要 npm）

先准备支持插件命令的 Codex CLI、Git 和 Python 3.9+。macOS/Linux 需要可用的 `python3`；Windows 需要 PATH 中的 `python` 指向 Python 3，并准备可用音频设备。

在终端执行，macOS、Linux 和 Windows 使用相同的两条安装命令：

```sh
codex plugin marketplace add wangyendt/codex-sounds --ref main
codex plugin add codex-sounds@codex-sounds
```

然后启动 `codex`，在交互输入框中输入 `/hooks`，审查来源为 `codex-sounds` 的三个 Hook 并信任。重启桌面 App 或新建 CLI 会话后测试提示音。没有需要批准的操作时不会播放批准音；普通文字问句不播放结构化提问音。

Ubuntu 缺少播放器时，安装 `pulseaudio-utils`（见下面的平台依赖）。本仓库自带插件市场清单 `.agents/plugins/marketplace.json`，Codex 负责从 GitHub 拉取、安装和更新；这条安装路径不使用 npm，也不需要手动克隆仓库或编辑用户配置。

以后更新：

```sh
codex plugin marketplace upgrade codex-sounds
codex plugin add codex-sounds@codex-sounds
```

更新后新建会话；若提示 Hooks 需要审查，重新确认。卸载插件使用 `codex plugin remove codex-sounds@codex-sounds`。

已有 `codex-sounds@personal` 本地开发版的电脑不必重复安装同一插件。迁移到 GitHub 市场版时，先禁用或卸载旧来源，避免两份 Hook 同时播放。

## 平台与依赖

所有平台需要 Python 3.9+（新安装建议使用仍受维护的 Python 3 版本），以及支持本插件 Hooks 的 Codex。

| 系统 | 播放后端 | 环境要求 |
| --- | --- | --- |
| macOS | 系统自带 `afplay` | 可用的 Python；启动器优先检查 Homebrew Python，避开 Xcode 管理的 Python 占位程序 |
| Ubuntu / Linux | `pw-play` → `paplay` → `aplay` | 至少安装其中一个播放器，并有可用的音频会话/设备 |
| Windows 原生 | Python 标准库 `winsound` | `python` 命令在 PATH 中指向 Python 3.9+；启用音频设备 |
| WSL / 容器 / SSH / 无桌面服务器 | 按执行主机系统选择后端 | 音频输出依赖宿主机配置；本插件不转发远程声音 |

Ubuntu 缺少播放器时，可自行安装 PulseAudio 工具：

```sh
sudo apt install pulseaudio-utils
```

Windows 的 Hook 使用 `commandWindows`，Python 在进程内读取插件根目录环境变量，避免依赖 PowerShell 和 CMD 不同的环境变量展开语法。包含中文或空格的安装路径纳入启动测试。

每台机器需要分别安装 Python、配置音频后端，并将插件安装、启用到该机的 Codex；复制源码不会自动注册到另一台机器。

## 生效和验证

安装后新建一个 Codex 任务，并审查、信任本插件的 Hooks：CLI 中运行 `/hooks`，检查来源为 `codex-sounds` 的三个 Hook 后信任。安装插件本身不自动信任 Hooks；更新 Hook 定义后需要重新审查。

1. 让 Codex 给出一句简短答复，检查本轮结束音。
2. 请 Codex 使用结构化提问工具提出一个问题，检查提问音。
3. 在本来就需要批准的正常工作流中检查批准音。不为音效测试改变审批规则或自动批准操作。

结构化提问匹配 `request_user_input`、`request_user_input_async`、`AskUserQuestion` 及命名空间前缀。聊天正文中的普通问句不触发提问音；特殊工具路径是否进入通用 Hooks，以当前 Codex 版本为准。

### 本地试听

macOS/Linux，在仓库目录运行（可用启动器自动选择 Python）：

```sh
sh scripts/run.sh --preview complete
sh scripts/run.sh --preview input
sh scripts/run.sh --preview approval
```

Windows，在仓库目录运行：

```powershell
python scripts/notify.py --preview complete
python scripts/notify.py --preview input
python scripts/notify.py --preview approval
```

试听失败返回非零退出码并在标准错误输出简要诊断。Hook 模式下播放失败仍输出 `{}` 并成功退出，不影响 Codex 工作。

## 设计边界

- `Stop` 代表本轮停止，不代表整个业务目标成功；其他 Stop Hook 继续任务时也可能已经响过。
- 插件不修改审批结果，不继续或阻止任务。
- 同一回合、同一工具调用去重；没有工具调用 ID 的批准事件仅短时去重，避免后续批准静音。
- 异步提问后三秒内的 Stop 音被抑制，优先保留提问音。
- WAV 峰值不超过满幅的 27%，系统和应用音量仍然生效。
- 播放子进程总等待预算为五秒；Linux 首选后端失败或超时后，在剩余预算内尝试备用后端。
- Windows 同步播放放在有超时限制的子进程内，避免父进程提前退出导致音效截断，也避免音频驱动长时间挂起 Hook。
- 不判断前后台、不读取系统勿扰状态、不转发远程音频。声音在执行 Hook 的主机播放。
- 去重数据库优先写入 `PLUGIN_DATA`，其次使用兼容环境变量 `CLAUDE_PLUGIN_DATA`；无覆盖时使用各系统的用户缓存目录。数据库只保存哈希、事件分类和时间，不保存正文。
- 设置 `CODEX_SOUNDS_MUTE=1` 可以静音自动 Hook；手动 `--preview` 仍试听。也可以在 Codex 中禁用插件。

## 开发与测试

在仓库目录运行，Windows 将 `python3` 换成 `python`：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/generate_sounds.py
```

生成音效只需要 Python 标准库；生成的三份 WAV 已随仓库提交，用户无需再次生成。

模拟事件（不播放、不写数据库）：

```sh
printf '%s' '{"hook_event_name":"Stop","session_id":"test","turn_id":"1"}' | sh scripts/run.sh --dry-run
```

已添加 GitHub Actions 的 macOS / Ubuntu / Windows × Python 3.9 / 3.13 测试矩阵。该工作流在推送和 Pull Request 时运行，也支持手动触发。单元测试模拟音频后端，不要求 CI 配备扬声器。

当前验证：Mac 上运行单元测试、启动器集成测试和实际音频播放测试；Windows/Linux 分支使用模拟后端覆盖选择、回退和超时。尚未完成 Windows/Linux 真实设备播放和 Codex 端到端验证。

## 文件结构

- `.codex-plugin/plugin.json`：插件元数据。
- `hooks/hooks.json`：三个 Hook，包含 Windows 启动命令。
- `scripts/run.sh`：macOS/Linux Python 启动器。
- `scripts/notify.py`：分类、去重、平台适配和播放。
- `scripts/generate_sounds.py`：可重建音效的合成脚本。
- `assets/*.wav`：三个平台共用的 PCM 音效。
- `tests/`：分类、并发去重、平台回退、缓存路径、启动器、输出契约测试。
- `.github/workflows/test.yml`：三平台自动测试配置。

## 源码与维护

```sh
git clone https://github.com/wangyendt/codex-sounds.git
cd codex-sounds
```

克隆后可按上面的命令运行测试和试听。自动 Hook 提醒还需要通过 Codex 的插件安装流程注册、启用，并审查信任 Hooks；克隆本身不会修改 Codex 配置。

在本地插件市场中开发时，让插件源指向同一份 Git 工作目录。修改后更新插件版本缓存标记，再从相应市场重新安装；已安装缓存不会自动跟随源码变化。新建任务以加载新版本，Hook 定义变化时重新审查、信任。

## 参考

- [OpenAI 官方 Hooks 文档](https://learn.chatgpt.com/docs/hooks)
- [Python winsound 文档](https://docs.python.org/3/library/winsound.html)
