-- 标准下载记录表
-- 唯一键：std_no + source_name（同一来源的同一标准号只保留一条记录）

CREATE TABLE IF NOT EXISTS standard_download_record (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    std_no      VARCHAR(100) NOT NULL        COMMENT '标准号',
    std_name    VARCHAR(500)                 COMMENT '标准名称',
    source_name VARCHAR(200)                 COMMENT '来源名称',
    source_type VARCHAR(20)                  COMMENT '来源类型 guobiao/hangbiao',
    status      VARCHAR(20)  NOT NULL        COMMENT 'SUCCESS/NO_FULL_TEXT/ABOLISHED/ADOPTED/FAILED',
    oss_url     VARCHAR(500)                 COMMENT 'OSS 完整 URL',
    oss_path    VARCHAR(500)                 COMMENT 'OSS 相对路径',
    created_at  DATETIME                     COMMENT '首次写入时间',
    updated_at  DATETIME                     COMMENT '最后更新时间',
    UNIQUE KEY  uk_std_no_source (std_no, source_name(100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标准下载记录';
