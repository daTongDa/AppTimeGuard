# 本地冒烟验收清单

日期：____

## 环境

- [ ] `pip install -r requirements.txt`
- [ ] `python run.py` 启动成功
- [ ] 浏览器打开 http://127.0.0.1:8765/

## API

- [ ] `GET /api/system/health` → ok
- [ ] `GET /api/system/status` → guard_running / launcher_running 为 true

## UI / 行为

- [ ] 登记记事本（或其它测试 exe）
- [ ] 未配时段或窗外打开 → 进程被结束
- [ ] 统计页出现用量 / kill_count
- [ ] 统计页会话时间轴：可选年月日，+/- 缩放小时/分钟刻度，并行应用多轨分色
- [ ] 配置当前可用时段 + 日限额 1 分钟 → 超时后仍杀
- [ ] 配置即将到来的定时启动 → 到点 launch 或因策略 launch_skipped
- [ ] 审计日志可见 kill / launch 记录

## 安全

- [ ] 服务仅绑定 127.0.0.1
- [ ] explorer.exe 等系统进程未被误杀
