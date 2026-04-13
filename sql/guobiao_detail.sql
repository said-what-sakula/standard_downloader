-- 国标详情信息表
-- 唯一键：std_no（同一标准号只保留一条）
-- 强制/推荐性从标准号推断：GB=强制性，GB/T=推荐性，GB/Z=指导性
-- 国标无废止日期字段，废止状态只通过 status 字段标识

CREATE TABLE IF NOT EXISTS guobiao_detail (
    id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
    std_no           VARCHAR(100)  NOT NULL        COMMENT '标准号，如 GB/T 43500-2023',
    std_name_zh      VARCHAR(500)                  COMMENT '中文标准名称',
    std_name_en      VARCHAR(500)                  COMMENT '英文标准名称',
    mandatory_type   VARCHAR(20)                   COMMENT '强制/推荐性：强制性 / 推荐性 / 指导性（从标准号推断）',
    status           VARCHAR(20)                   COMMENT '当前状态：现行 / 废止 / 即将实施',
    ccs              VARCHAR(50)                   COMMENT '中国标准分类号（CCS）',
    ics              VARCHAR(50)                   COMMENT '国际标准分类号（ICS）',
    publish_date     DATE                          COMMENT '发布日期',
    implement_date   DATE          NULL            COMMENT '实施日期（废止标准可能为空）',
    department       VARCHAR(200)                  COMMENT '主管部门',
    org_department   VARCHAR(200)                  COMMENT '归口部门',
    publisher        VARCHAR(500)                  COMMENT '发布单位',
    note             VARCHAR(500)                  COMMENT '备注',
    detail_url       VARCHAR(500)                  COMMENT '详情页 URL（含 hcno）',
    source_name      VARCHAR(200)                  COMMENT '来源名称',
    created_at       DATETIME                      COMMENT '首次写入时间',
    updated_at       DATETIME                      COMMENT '最后更新时间',
    UNIQUE KEY uk_std_no (std_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国家标准详情信息';
