# App Time Guard（Windows）

本机 **应用可用时段 / 时长限额 / 用量统计 / 定时启动** 工具。超出时段或限额时 **强制结束进程**。仅监听 `127.0.0.1`。

位于 `agency_agents/app-time-guard/`，实现时参考同目录上级的 Cursor 工程规则（Backend / Frontend / SRE）。

## 功能

- **自动发现**：扫描运行中进程 + 开始菜单 `.lnk`，一键导入
- Web 配置：登记应用、**按单应用**配置可用时段与定时启停；支持分类（游戏娱乐 / 学习 / 办公 / 其他）
- **分类默认规则**：
  - 游戏娱乐：仅周六日 **06:00–22:20**，日限 **2 小时**
  - 学习 / 办公 / 其他：每天 **05:00–22:20**，不限时长
  - 新建/导入默认写入；可用「套用默认」重写
- **默认策略**：未配置任何时段 = **全天开放**；配置时段后仅窗口内允许
- 守护线程：周期性检测进程；违规则 terminate/kill
- **定时启停**：支持每天/指定星期；动作可选「启动」或「关闭」
- 统计：每日用量、会话时间轴（年月日 / 24h 缩放）、击杀次数、启动次数、审计日志
- 计时：默认仅统计**当前前台窗口**对应的已登记应用（后台托盘不计）；可用环境变量 `USAGE_FOREGROUND_ONLY=false` 改为进程在跑就计

## 定时启停说明

- 规则按 **应用 ID** 隔离，改 A 不会动到 B
- 重复：`每天`（weekday=-1）或周一～周日
- 动作：`launch` 到点启动；`close` 到点结束进程
- 轮询间隔约 15 秒，到点后 **5 分钟内**均可触发
- 启动若因限额/窗外暂时不能启：记 `launch_deferred` 并重试
- UI 提供「1 分钟后启动/关闭（测）」与「重置触发」方便验收


## 安装

```powershell
cd g:\AI_SYS\agency_agents\app-time-guard
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 运行

```powershell
python run.py
```

打开：http://127.0.0.1:8765/

API 文档：http://127.0.0.1:8765/docs

## 自测

```powershell
cd g:\AI_SYS\agency_agents\app-time-guard
python scripts/selftest.py
```

应看到全部 `[PASS]`，退出码 0。覆盖：默认开放策略、自动发现、应用 CRUD、时段批量、定时启动、启动/杀进程、统计。


1. 登记 `C:\Windows\System32\notepad.exe`，进程名 `notepad.exe`
2. 添加「当前星期、接下来 10 分钟」之外的时段，或先不配时段（全禁）
3. 手动打开记事本 → 数秒内应被结束；「统计」页击杀数增加
4. 配置覆盖当前时间的时段，日限额设为 1 分钟 → 超时后再开仍被杀
5. 配置约 1 分钟后的定时启动 → 到点自动拉起（且须在允许策略内）

## 开机自启（任务计划程序）

以当前用户登录时启动（建议勾选「最高权限」以便结束更多进程）：

```powershell
$py = (Resolve-Path .\ .venv\Scripts\python.exe).Path
# 若未用 venv，改为 (Get-Command python).Source
$work = (Resolve-Path .).Path
$action = New-ScheduledTaskAction -Execute $py -Argument "run.py" -WorkingDirectory $work
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "AppTimeGuard" -Action $action -Trigger $trigger -Description "Windows App Time Guard"
```

取消：

```powershell
Unregister-ScheduledTask -TaskName "AppTimeGuard" -Confirm:$false
```

## 打包安装程序（Windows）

一键构建单文件 `app_time_guard.exe` 与可安装包：

```powershell
cd g:\AI_SYS\agency_agents\app-time-guard
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

产物：

| 路径 | 说明 |
|------|------|
| `dist\app_time_guard.exe` | 单文件主程序，可直接双击运行 |
| `dist\AppTimeGuard_Package\` | 含 `install.ps1` / `uninstall.ps1` |
| `dist\AppTimeGuard_Portable.zip` | 上述目录的 zip，便于分发 |
| `dist\installer\AppTimeGuard_Setup_*.exe` | 若已安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php) 则额外生成 |

安装版数据目录：`%LOCALAPPDATA%\AppTimeGuard\`

命令行参数：`--no-browser`、`--port 8765`、`--host 127.0.0.1`

## 权限说明

- 普通权限可能无法结束部分高权限进程；审计日志会记录 `access_denied`
- 本工具可被手动停止服务绕过，定位为 **自律辅助**，非防破解方案

## 目录

```
app-time-guard/
  run.py / app_time_guard_entry.py
  requirements.txt
  packaging/     # PyInstaller spec + Inno Setup
  scripts/       # selftest / build_exe
  app/           # FastAPI、模型、守护与调度
  static/        # Web UI
  data/          # SQLite（开发模式）
  dist/          # 打包产物
```

## 冒烟清单（开发）

| 项 | 期望 |
|----|------|
| `GET /api/system/health` | `{"status":"ok"}` |
| `GET /api/system/status` | guard/launcher running |
| CRUD `/api/apps/` | 可写可读 |
| 窗外进程 | 被杀并写 audit `kill` |
| 定时启动 | audit `launch` 或 `launch_skipped` |
