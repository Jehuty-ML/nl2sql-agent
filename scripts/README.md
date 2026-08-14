# 合成数据与本地 ClickHouse

本仓**不依赖**外部采集仓库即可跑通问数：`infra/` 提供 ClickHouse，本脚本灌合成数据。

## 一键准备分析库

在仓库根目录：

```powershell
docker compose -f infra/docker-compose.yml up -d
python .\scripts\generate_demo_data.py --seed 42 --to-clickhouse --truncate
```

默认连接：

| 用途 | 用户 | 密码 |
|------|------|------|
| **造数脚本（管理）** | `lumen` | `lumen_demo` |
| **问数 Agent（只读）** | `lumen_ro` | `lumen_ro_demo` |

库表：`lumenlearn.events` / `lumenlearn.users`。  
Agent `.env` 必须用只读账号；脚本默认用管理账号灌数，并执行 `infra/init_readonly.sql` 创建 `lumen_ro`。

脚本会自动执行 `infra/clickhouse_ddl.sql` 建库建表。

## 仅生成 CSV（不起容器）

```powershell
python .\scripts\generate_demo_data.py --seed 42 --users 800 --days 90
```

输出到 `data/`：`users.csv`、`events.csv`、`GENERATION_META.txt`。同一 `--seed` 可复现。

## 数据声明

100% Synthetic Demo Data · No PII · 仅用于技术演示。

事件契约见 `app/bi/events_dictionary.json`。
