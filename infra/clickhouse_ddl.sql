-- LumenLearn Demo · ClickHouse DDL（问数分析库）
-- Synthetic Demo Only

CREATE DATABASE IF NOT EXISTS lumenlearn;

-- 行为事件事实表
CREATE TABLE IF NOT EXISTS lumenlearn.events
(
    distinct_id String,
    anonymous_id String,
    identity_login_id String,
    event String,
    event_time DateTime64(3),
    dt Date,
    app_id String,
    lib String,
    screen_name String,
    title String,
    network_type String,
    register_channel String,
    path_id String,
    path_name String,
    path_category String,
    lesson_id String,
    lesson_name String,
    lesson_index Int32,
    duration Int32,
    exercise_id String,
    is_passed Int8,
    challenge_id String,
    challenge_name String,
    challenge_days Int32,
    share_type String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(dt)
ORDER BY (dt, event, distinct_id);

-- 用户属性表
CREATE TABLE IF NOT EXISTS lumenlearn.users
(
    distinct_id String,
    login_id String,
    register_dt Date,
    register_channel String,
    app_id String,
    last_active_dt Date
)
ENGINE = ReplacingMergeTree
ORDER BY distinct_id;
