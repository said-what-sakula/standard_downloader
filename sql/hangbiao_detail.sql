-- 行标详情信息表
-- 唯一键：std_no（同一标准号只保留一条）

CREATE TABLE IF NOT EXISTS hangbiao_detail (
    id                BIGINT        AUTO_INCREMENT PRIMARY KEY,
    std_no            VARCHAR(100)  NOT NULL        COMMENT '标准号，如 AQ 2076—2025',
    std_name          VARCHAR(500)                  COMMENT '标准名称',
    industry_code     VARCHAR(20)                   COMMENT '行业代码，如 AQ、NB、JT',
    industry_name     VARCHAR(100)                  COMMENT '行业名称，如 安全生产、能源',
    mandatory_type    VARCHAR(20)                   COMMENT '强制/推荐性：强制性 / 推荐性 / 指导性',
    status            VARCHAR(20)                   COMMENT '当前状态：现行 / 废止 / 即将实施',
    publish_date      DATE                          COMMENT '发布日期',
    implement_date    DATE                          COMMENT '实施日期',
    abolish_date      DATE          NULL            COMMENT '废止日期（仅废止标准有值）',
    ccs               VARCHAR(50)                   COMMENT '中国标准分类号',
    ics               VARCHAR(50)                   COMMENT '国际标准分类号',
    org_unit          VARCHAR(200)                  COMMENT '归口单位',
    department        VARCHAR(200)                  COMMENT '主管部门',
    industry_category VARCHAR(200)                  COMMENT '行业分类',
    scope             TEXT                          COMMENT '适用范围',
    drafting_orgs     VARCHAR(1000)                 COMMENT '主要起草单位（逗号分隔）',
    drafting_persons  VARCHAR(1000)                 COMMENT '主要起草人（逗号分隔）',
    record_no         VARCHAR(100)                  COMMENT '备案号',
    record_notice     VARCHAR(100)                  COMMENT '备案公告',
    detail_url        VARCHAR(500)                  COMMENT '详情页 URL',
    source_name       VARCHAR(200)                  COMMENT '来源名称',
    created_at        DATETIME                      COMMENT '首次写入时间',
    updated_at        DATETIME                      COMMENT '最后更新时间',
    UNIQUE KEY uk_std_no (std_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业标准详情信息';


-- 被代替标准关联表
-- 唯一键：std_no + replaced_std_no

CREATE TABLE IF NOT EXISTS hangbiao_replace_std (
    id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
    std_no           VARCHAR(100)  NOT NULL COMMENT '主标准号',
    replaced_std_no  VARCHAR(100)  NOT NULL COMMENT '被代替的标准号',
    created_at       DATETIME               COMMENT '写入时间',
    UNIQUE KEY uk_std_replace (std_no, replaced_std_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行标被代替标准关联';
