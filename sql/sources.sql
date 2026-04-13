-- 下载来源配置表
-- 替代 config/sources.yaml，以 name 为唯一键
-- source_type: guobiao / hangbiao

CREATE TABLE IF NOT EXISTS download_source (
    id          BIGINT        AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(200)  NOT NULL        COMMENT '来源名称，如 AQ-安全生产',
    source_type VARCHAR(20)   NOT NULL        COMMENT 'guobiao / hangbiao',
    url         VARCHAR(1000) NOT NULL        COMMENT '列表页 URL',
    sort_order  INT           DEFAULT 0       COMMENT '排序序号（前端拖拽顺序）',
    created_at  DATETIME                      COMMENT '首次写入时间',
    updated_at  DATETIME                      COMMENT '最后更新时间',
    UNIQUE KEY uk_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下载来源配置';

-- 初始数据（原 sources.yaml 迁移）
INSERT IGNORE INTO download_source (name, source_type, url, sort_order, created_at, updated_at) VALUES
('石油及相关技术',   'guobiao',  'https://openstd.samr.gov.cn/bzgk/gb/std_list?r=0.3486968221641664&p.p1=0&p.p5=PUBLISHED&p.p6=75',    0, NOW(), NOW()),
('机械系统和通用件', 'guobiao',  'https://openstd.samr.gov.cn/bzgk/gb/std_list?r=0.022731407008866555&p.p1=0&p.p5=PUBLISHED&p.p6=21', 1, NOW(), NOW()),
('橡胶和塑料工业',   'guobiao',  'https://openstd.samr.gov.cn/bzgk/gb/std_list?r=0.8454233586786969&p.p1=0&p.p5=PUBLISHED&p.p6=83',  2, NOW(), NOW()),
('AQ-安全生产',      'hangbiao', 'https://std.samr.gov.cn/hb/hbQuery?initnode=AQ%20%E5%AE%89%E5%85%A8%E7%94%9F%E4%BA%A7',           3, NOW(), NOW());
