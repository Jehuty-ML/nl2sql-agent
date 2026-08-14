-- Agent 专用只读账号（由管理账号执行；造数脚本 --to-clickhouse 时自动尝试）
-- 与工具层 / 会话 settings.readonly=1 叠加，形成三道防线。

CREATE USER IF NOT EXISTS lumen_ro IDENTIFIED WITH plaintext_password BY 'lumen_ro_demo' SETTINGS readonly = 1;
GRANT SELECT ON lumenlearn.* TO lumen_ro;
