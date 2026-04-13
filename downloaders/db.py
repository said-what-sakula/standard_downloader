"""
downloaders/db.py
MySQL 下载记录 CRUD，基于 SQLAlchemy 同步引擎。
程序启动时调用 init_db() 自动建表。
"""

import sys
from datetime import datetime, timezone, timedelta

_CST = timezone(timedelta(hours=8))


def _now() -> datetime:
    """返回当前北京时间（UTC+8，naive datetime，适合直接写入 MySQL）。"""
    return datetime.now(_CST).replace(tzinfo=None)

from sqlalchemy import create_engine, text as sql_text

from .config import get_db_config

_engine = None

_INIT_SQLS = [
    """
    CREATE TABLE IF NOT EXISTS standard_download_record (
        id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
        std_no      VARCHAR(100) NOT NULL        COMMENT '标准号',
        std_name    VARCHAR(500)                 COMMENT '标准名称',
        source_name VARCHAR(200)                 COMMENT '来源名称',
        source_type VARCHAR(20)                  COMMENT '来源类型 guobiao/hangbiao',
        status      VARCHAR(20)  NOT NULL        COMMENT 'SUCCESS/NO_FULL_TEXT/ABOLISHED/ADOPTED/FAILED',
        oss_url     VARCHAR(500)                 COMMENT 'OSS 完整 URL',
        oss_path    VARCHAR(500)                 COMMENT 'OSS 相对路径',
        local_path  VARCHAR(1000)                COMMENT '本地文件绝对路径',
        created_at  DATETIME                     COMMENT '首次写入时间',
        updated_at  DATETIME                     COMMENT '最后更新时间',
        UNIQUE KEY  uk_std_no_source (std_no, source_name(100))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标准下载记录'
    """,
    """
    CREATE TABLE IF NOT EXISTS download_source (
        id          BIGINT        AUTO_INCREMENT PRIMARY KEY,
        name        VARCHAR(200)  NOT NULL        COMMENT '来源名称',
        source_type VARCHAR(20)   NOT NULL        COMMENT 'guobiao / hangbiao',
        url         VARCHAR(1000) NOT NULL        COMMENT '列表页 URL',
        sort_order  INT           DEFAULT 0       COMMENT '排序序号',
        created_at  DATETIME                      COMMENT '首次写入时间',
        updated_at  DATETIME                      COMMENT '最后更新时间',
        UNIQUE KEY uk_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='下载来源配置'
    """,
    """
    CREATE TABLE IF NOT EXISTS hangbiao_detail (
        id                BIGINT        AUTO_INCREMENT PRIMARY KEY,
        std_no            VARCHAR(100)  NOT NULL        COMMENT '标准号',
        std_name          VARCHAR(500)                  COMMENT '标准名称',
        industry_code     VARCHAR(20)                   COMMENT '行业代码',
        industry_name     VARCHAR(100)                  COMMENT '行业名称',
        mandatory_type    VARCHAR(20)                   COMMENT '强制/推荐性',
        status            VARCHAR(20)                   COMMENT '当前状态',
        publish_date      DATE                          COMMENT '发布日期',
        implement_date    DATE                          COMMENT '实施日期',
        abolish_date      DATE          NULL            COMMENT '废止日期',
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行业标准详情信息'
    """,
    """
    CREATE TABLE IF NOT EXISTS hangbiao_replace_std (
        id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
        std_no           VARCHAR(100)  NOT NULL COMMENT '主标准号',
        replaced_std_no  VARCHAR(100)  NOT NULL COMMENT '被代替的标准号',
        created_at       DATETIME               COMMENT '写入时间',
        UNIQUE KEY uk_std_replace (std_no, replaced_std_no)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='行标被代替标准关联'
    """,
    """
    CREATE TABLE IF NOT EXISTS guobiao_detail (
        id               BIGINT        AUTO_INCREMENT PRIMARY KEY,
        std_no           VARCHAR(100)  NOT NULL        COMMENT '标准号',
        std_name_zh      VARCHAR(500)                  COMMENT '中文标准名称',
        std_name_en      VARCHAR(500)                  COMMENT '英文标准名称',
        mandatory_type   VARCHAR(20)                   COMMENT '强制/推荐性',
        status           VARCHAR(20)                   COMMENT '当前状态',
        ccs              VARCHAR(50)                   COMMENT '中国标准分类号',
        ics              VARCHAR(50)                   COMMENT '国际标准分类号',
        publish_date     DATE                          COMMENT '发布日期',
        implement_date   DATE          NULL            COMMENT '实施日期',
        department       VARCHAR(200)                  COMMENT '主管部门',
        org_department   VARCHAR(200)                  COMMENT '归口部门',
        publisher        VARCHAR(500)                  COMMENT '发布单位',
        note             VARCHAR(500)                  COMMENT '备注',
        detail_url       VARCHAR(500)                  COMMENT '详情页 URL',
        source_name      VARCHAR(200)                  COMMENT '来源名称',
        created_at       DATETIME                      COMMENT '首次写入时间',
        updated_at       DATETIME                      COMMENT '最后更新时间',
        UNIQUE KEY uk_std_no (std_no)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='国家标准详情信息'
    """,
]


def init_db() -> None:
    """启动时自动建表（CREATE TABLE IF NOT EXISTS），并执行字段迁移，数据库未配置时跳过。"""
    engine = get_engine()
    if engine is None:
        return
    try:
        with engine.connect() as conn:
            for ddl in _INIT_SQLS:
                conn.execute(sql_text(ddl))
            # 迁移：为旧表补充 local_path 列（列已存在时忽略错误）
            try:
                conn.execute(sql_text(
                    "ALTER TABLE standard_download_record "
                    "ADD COLUMN local_path VARCHAR(1000) COMMENT '本地文件绝对路径'"
                ))
            except Exception:
                pass  # 列已存在，忽略
            conn.commit()
    except Exception as e:
        print(f"[DB] 自动建表失败: {e}", file=sys.stderr)


def get_engine():
    """获取 SQLAlchemy 同步引擎（单例）。数据库未配置时返回 None。"""
    global _engine
    if _engine is None:
        cfg = get_db_config()
        if not cfg.get("host"):
            return None
        url = (
            f"mysql+pymysql://{cfg['user']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['db']}"
            f"?charset=utf8mb4"
        )
        pool_size    = int(cfg.get("pool_size", 5))
        pool_recycle = int(cfg.get("pool_recycle", 1800))
        _engine = create_engine(
            url,
            pool_size=pool_size,
            max_overflow=10,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,
        )
    return _engine


def upsert_std_record(
    std_no: str,
    std_name: str,
    source_name: str,
    source_type: str,
    status: str,
    oss_url: str = None,
    oss_path: str = None,
    local_path: str = None,
) -> None:
    """
    写入或更新 standard_download_record 表。
    以 (std_no, source_name) 为唯一键，重复时更新所有字段。
    数据库未配置或写入失败时静默忽略，不影响主流程。
    """
    engine = get_engine()
    if engine is None:
        return
    now = _now()
    sql = (
        "INSERT INTO standard_download_record "
        "(std_no, std_name, source_name, source_type, status, "
        " oss_url, oss_path, local_path, created_at, updated_at) "
        "VALUES (:std_no, :std_name, :source_name, :source_type, :status, "
        "        :oss_url, :oss_path, :local_path, :now, :now) "
        "ON DUPLICATE KEY UPDATE "
        "std_name=VALUES(std_name), source_type=VALUES(source_type), "
        "status=VALUES(status), oss_url=VALUES(oss_url), "
        "oss_path=VALUES(oss_path), local_path=VALUES(local_path), "
        "updated_at=VALUES(updated_at)"
    )
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(sql), {
                "std_no":      std_no,
                "std_name":    std_name,
                "source_name": source_name,
                "source_type": source_type,
                "status":      status,
                "oss_url":     oss_url,
                "oss_path":    oss_path,
                "local_path":  local_path,
                "now":         now,
            })
            conn.commit()
    except Exception as e:
        print(f"[DB] 记录写入失败 [{std_no}]: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# hangbiao_detail  行标详情信息
# ---------------------------------------------------------------------------

def upsert_hangbiao_detail(meta: dict) -> None:
    """
    写入或更新 hangbiao_detail 表，以 std_no 为唯一键。
    meta 字段：std_no / std_name / industry_code / industry_name /
              mandatory_type / status / publish_date / implement_date /
              abolish_date / ccs / ics / org_unit / department / industry_category /
              scope / drafting_orgs / drafting_persons /
              record_no / record_notice / detail_url / source_name
    """
    engine = get_engine()
    if engine is None:
        return
    std_no = (meta.get("std_no") or "").strip()
    if not std_no:
        return
    now = _now()
    sql = (
        "INSERT INTO hangbiao_detail "
        "(std_no, std_name, industry_code, industry_name, mandatory_type, "
        " status, publish_date, implement_date, abolish_date, "
        " ccs, ics, org_unit, department, industry_category, "
        " scope, drafting_orgs, drafting_persons, "
        " record_no, record_notice, detail_url, source_name, "
        " created_at, updated_at) "
        "VALUES "
        "(:std_no, :std_name, :industry_code, :industry_name, :mandatory_type, "
        " :status, :publish_date, :implement_date, :abolish_date, "
        " :ccs, :ics, :org_unit, :department, :industry_category, "
        " :scope, :drafting_orgs, :drafting_persons, "
        " :record_no, :record_notice, :detail_url, :source_name, "
        " :now, :now) "
        "ON DUPLICATE KEY UPDATE "
        "std_name=VALUES(std_name), industry_code=VALUES(industry_code), "
        "industry_name=VALUES(industry_name), mandatory_type=VALUES(mandatory_type), "
        "status=VALUES(status), publish_date=VALUES(publish_date), "
        "implement_date=VALUES(implement_date), abolish_date=VALUES(abolish_date), "
        "ccs=VALUES(ccs), ics=VALUES(ics), "
        "org_unit=VALUES(org_unit), department=VALUES(department), "
        "industry_category=VALUES(industry_category), "
        "scope=VALUES(scope), drafting_orgs=VALUES(drafting_orgs), "
        "drafting_persons=VALUES(drafting_persons), "
        "record_no=VALUES(record_no), record_notice=VALUES(record_notice), "
        "detail_url=VALUES(detail_url), source_name=VALUES(source_name), "
        "updated_at=VALUES(updated_at)"
    )
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(sql), {
                "std_no":            std_no,
                "std_name":          meta.get("std_name") or None,
                "industry_code":     meta.get("industry_code") or None,
                "industry_name":     meta.get("industry_name") or None,
                "mandatory_type":    meta.get("mandatory_type") or None,
                "status":            meta.get("status") or None,
                "publish_date":      meta.get("publish_date") or None,
                "implement_date":    meta.get("implement_date") or None,
                "abolish_date":      meta.get("abolish_date") or None,
                "ccs":               meta.get("ccs") or None,
                "ics":               meta.get("ics") or None,
                "org_unit":          meta.get("org_unit") or None,
                "department":        meta.get("department") or None,
                "industry_category": meta.get("industry_category") or None,
                "scope":             meta.get("scope") or None,
                "drafting_orgs":     meta.get("drafting_orgs") or None,
                "drafting_persons":  meta.get("drafting_persons") or None,
                "record_no":         meta.get("record_no") or None,
                "record_notice":     meta.get("record_notice") or None,
                "detail_url":        meta.get("detail_url") or None,
                "source_name":       meta.get("source_name") or None,
                "now":               now,
            })
            conn.commit()
    except Exception as e:
        print(f"[DB] hangbiao_detail 写入失败 [{std_no}]: {e}", file=sys.stderr)


def upsert_hangbiao_replace_stds(std_no: str, replaced_list: list) -> None:
    """
    批量写入 hangbiao_replace_std 关联表。
    replaced_list：被代替标准号列表，如 ["AQ/T 2076—2020", "AQ/T 2077—2020"]
    重复主键时忽略，保留原记录。
    """
    engine = get_engine()
    if engine is None or not std_no or not replaced_list:
        return
    sql = (
        "INSERT IGNORE INTO hangbiao_replace_std "
        "(std_no, replaced_std_no, created_at) "
        "VALUES (:std_no, :replaced_std_no, :now)"
    )
    now = _now()
    try:
        with engine.connect() as conn:
            for rep in replaced_list:
                rep = rep.strip()
                if rep:
                    conn.execute(sql_text(sql), {
                        "std_no":          std_no,
                        "replaced_std_no": rep,
                        "now":             now,
                    })
            conn.commit()
    except Exception as e:
        print(f"[DB] hangbiao_replace_std 写入失败 [{std_no}]: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# guobiao_detail  国标详情信息
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# download_source  来源配置
# ---------------------------------------------------------------------------

def get_all_sources() -> list:
    """
    读取 download_source 表，返回来源列表。
    数据库未配置或读取失败时返回空列表（调用方自行 fallback）。
    每项格式：{"name": ..., "type": ..., "url": ...}
    """
    engine = get_engine()
    if engine is None:
        return []
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql_text(
                "SELECT name, source_type, url FROM download_source ORDER BY sort_order, id"
            )).fetchall()
        return [{"name": r[0], "type": r[1], "url": r[2]} for r in rows]
    except Exception as e:
        print(f"[DB] 读取来源失败: {e}", file=sys.stderr)
        return []


def replace_all_sources(sources: list) -> None:
    """
    用 sources 替换 download_source 表中的全部记录（先删除再插入）。
    sources 每项格式：{"name": ..., "type": ..., "url": ...}
    若某来源 URL 不变但名称变了，自动同步 standard_download_record 中的 source_name。
    数据库未配置或写入失败时静默忽略。
    """
    engine = get_engine()
    if engine is None:
        return
    now = _now()
    try:
        with engine.connect() as conn:
            # 读取旧来源列表，构建 url -> name 映射
            old_rows = conn.execute(sql_text(
                "SELECT name, url FROM download_source"
            )).fetchall()
            old_url_to_name = {r[1]: r[0] for r in old_rows}

            # 检测重命名（URL 相同但名称不同），同步下载记录
            for src in sources:
                old_name = old_url_to_name.get(src["url"])
                new_name = src["name"]
                if old_name and old_name != new_name:
                    result = conn.execute(sql_text(
                        "UPDATE standard_download_record "
                        "SET source_name = :new_name "
                        "WHERE source_name = :old_name"
                    ), {"new_name": new_name, "old_name": old_name})
                    affected = result.rowcount
                    if affected > 0:
                        print(
                            f"[DB] 来源重命名同步: '{old_name}' -> '{new_name}'，"
                            f"影响 {affected} 条下载记录",
                            file=sys.stderr,
                        )

            # 全量替换来源表
            conn.execute(sql_text("DELETE FROM download_source"))
            for i, src in enumerate(sources):
                conn.execute(sql_text(
                    "INSERT INTO download_source "
                    "(name, source_type, url, sort_order, created_at, updated_at) "
                    "VALUES (:name, :source_type, :url, :sort_order, :now, :now)"
                ), {
                    "name":        src["name"],
                    "source_type": src.get("type", "guobiao"),
                    "url":         src["url"],
                    "sort_order":  i,
                    "now":         now,
                })
            conn.commit()
    except Exception as e:
        print(f"[DB] 保存来源失败: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# guobiao_detail  国标详情信息
# ---------------------------------------------------------------------------

def upsert_guobiao_detail(meta: dict) -> None:
    """
    写入或更新 guobiao_detail 表，以 std_no 为唯一键。
    meta 字段：std_no / std_name_zh / std_name_en / mandatory_type /
              status / ccs / ics / publish_date / implement_date /
              department / org_department / publisher / note /
              detail_url / source_name
    """
    engine = get_engine()
    if engine is None:
        return
    std_no = (meta.get("std_no") or "").strip()
    if not std_no:
        return
    now = _now()
    sql = (
        "INSERT INTO guobiao_detail "
        "(std_no, std_name_zh, std_name_en, mandatory_type, status, "
        " ccs, ics, publish_date, implement_date, "
        " department, org_department, publisher, note, "
        " detail_url, source_name, created_at, updated_at) "
        "VALUES "
        "(:std_no, :std_name_zh, :std_name_en, :mandatory_type, :status, "
        " :ccs, :ics, :publish_date, :implement_date, "
        " :department, :org_department, :publisher, :note, "
        " :detail_url, :source_name, :now, :now) "
        "ON DUPLICATE KEY UPDATE "
        "std_name_zh=VALUES(std_name_zh), std_name_en=VALUES(std_name_en), "
        "mandatory_type=VALUES(mandatory_type), status=VALUES(status), "
        "ccs=VALUES(ccs), ics=VALUES(ics), "
        "publish_date=VALUES(publish_date), implement_date=VALUES(implement_date), "
        "department=VALUES(department), org_department=VALUES(org_department), "
        "publisher=VALUES(publisher), note=VALUES(note), "
        "detail_url=VALUES(detail_url), source_name=VALUES(source_name), "
        "updated_at=VALUES(updated_at)"
    )
    try:
        with engine.connect() as conn:
            conn.execute(sql_text(sql), {
                "std_no":         std_no,
                "std_name_zh":    meta.get("std_name_zh") or None,
                "std_name_en":    meta.get("std_name_en") or None,
                "mandatory_type": meta.get("mandatory_type") or None,
                "status":         meta.get("status") or None,
                "ccs":            meta.get("ccs") or None,
                "ics":            meta.get("ics") or None,
                "publish_date":   meta.get("publish_date") or None,
                "implement_date": meta.get("implement_date") or None,
                "department":     meta.get("department") or None,
                "org_department": meta.get("org_department") or None,
                "publisher":      meta.get("publisher") or None,
                "note":           meta.get("note") or None,
                "detail_url":     meta.get("detail_url") or None,
                "source_name":    meta.get("source_name") or None,
                "now":            now,
            })
            conn.commit()
    except Exception as e:
        print(f"[DB] guobiao_detail 写入失败 [{std_no}]: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 标准库检索
# ---------------------------------------------------------------------------

def count_records_by_source(source_name: str) -> int:
    """
    统计某个来源在 standard_download_record 表中的记录数。
    数据库未配置时返回 0。
    """
    engine = get_engine()
    if engine is None:
        return 0
    try:
        with engine.connect() as conn:
            result = conn.execute(
                sql_text(
                    "SELECT COUNT(*) FROM standard_download_record WHERE source_name = :s"
                ),
                {"s": source_name},
            ).scalar()
        return int(result or 0)
    except Exception as e:
        print(f"[DB] count_records_by_source 失败: {e}", file=sys.stderr)
        return 0


def search_records(
    keyword: str = None,
    source_type: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    分页检索 standard_download_record。
    返回 {"total": int, "items": list[dict]}，失败时返回空结果。
    """
    engine = get_engine()
    if engine is None:
        return {"total": 0, "items": []}

    conditions = []
    base_params: dict = {}
    if keyword:
        conditions.append("(std_no LIKE :kw OR std_name LIKE :kw)")
        base_params["kw"] = f"%{keyword}%"
    if source_type:
        conditions.append("source_type = :source_type")
        base_params["source_type"] = source_type
    if status:
        conditions.append("status = :status")
        base_params["status"] = status

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_sql = f"SELECT COUNT(*) FROM standard_download_record {where}"
    data_sql = (
        f"SELECT id, std_no, std_name, source_name, source_type, status, "
        f"oss_url, oss_path, local_path, created_at, updated_at "
        f"FROM standard_download_record {where} "
        f"ORDER BY updated_at DESC "
        f"LIMIT :limit OFFSET :offset"
    )

    try:
        with engine.connect() as conn:
            total = conn.execute(sql_text(count_sql), base_params).scalar() or 0
            data_params = {**base_params, "limit": page_size, "offset": (page - 1) * page_size}
            rows = conn.execute(sql_text(data_sql), data_params).fetchall()

        def _fmt(v):
            return v.isoformat() if v and hasattr(v, "isoformat") else v

        items = [
            {
                "id":          r[0],
                "std_no":      r[1],
                "std_name":    r[2],
                "source_name": r[3],
                "source_type": r[4],
                "status":      r[5],
                "oss_url":     r[6],
                "oss_path":    r[7],
                "local_path":  r[8],
                "created_at":  _fmt(r[9]),
                "updated_at":  _fmt(r[10]),
            }
            for r in rows
        ]
        return {"total": int(total), "items": items}
    except Exception as e:
        print(f"[DB] 检索记录失败: {e}", file=sys.stderr)
        return {"total": 0, "items": []}


def get_record_detail(record_id: int):
    """
    按主键获取下载记录，并联合查询对应详情表（hangbiao_detail / guobiao_detail）。
    返回 None 表示记录不存在。
    """
    engine = get_engine()
    if engine is None:
        return None

    def _fmt(v):
        return str(v) if v is not None else None

    try:
        with engine.connect() as conn:
            row = conn.execute(sql_text(
                "SELECT id, std_no, std_name, source_name, source_type, status, "
                "oss_url, oss_path, local_path, created_at, updated_at "
                "FROM standard_download_record WHERE id = :id"
            ), {"id": record_id}).fetchone()
            if not row:
                return None

            result = {
                "id":          row[0],
                "std_no":      row[1],
                "std_name":    row[2],
                "source_name": row[3],
                "source_type": row[4],
                "status":      row[5],
                "oss_url":     row[6],
                "oss_path":    row[7],
                "local_path":  row[8],
                "created_at":  _fmt(row[9]),
                "updated_at":  _fmt(row[10]),
                "detail":      None,
            }

            std_no      = row[1]
            source_type = row[4]

            if source_type == "hangbiao":
                dr = conn.execute(sql_text(
                    "SELECT std_name, industry_code, industry_name, mandatory_type, status, "
                    "publish_date, implement_date, abolish_date, ccs, ics, "
                    "org_unit, department, industry_category, scope, "
                    "drafting_orgs, drafting_persons, record_no, record_notice "
                    "FROM hangbiao_detail WHERE std_no = :s"
                ), {"s": std_no}).fetchone()
                if dr:
                    replaced = conn.execute(sql_text(
                        "SELECT replaced_std_no FROM hangbiao_replace_std WHERE std_no = :s"
                    ), {"s": std_no}).fetchall()
                    result["detail"] = {
                        "std_name":          dr[0],
                        "industry_code":     dr[1],
                        "industry_name":     dr[2],
                        "mandatory_type":    dr[3],
                        "status":            dr[4],
                        "publish_date":      _fmt(dr[5]),
                        "implement_date":    _fmt(dr[6]),
                        "abolish_date":      _fmt(dr[7]),
                        "ccs":               dr[8],
                        "ics":               dr[9],
                        "org_unit":          dr[10],
                        "department":        dr[11],
                        "industry_category": dr[12],
                        "scope":             dr[13],
                        "drafting_orgs":     dr[14],
                        "drafting_persons":  dr[15],
                        "record_no":         dr[16],
                        "record_notice":     dr[17],
                        "replaced_stds":     [r[0] for r in replaced],
                    }

            elif source_type == "guobiao":
                dr = conn.execute(sql_text(
                    "SELECT std_name_zh, std_name_en, mandatory_type, status, ccs, ics, "
                    "publish_date, implement_date, department, org_department, publisher, note "
                    "FROM guobiao_detail WHERE std_no = :s"
                ), {"s": std_no}).fetchone()
                if dr:
                    result["detail"] = {
                        "std_name_zh":    dr[0],
                        "std_name_en":    dr[1],
                        "mandatory_type": dr[2],
                        "status":         dr[3],
                        "ccs":            dr[4],
                        "ics":            dr[5],
                        "publish_date":   _fmt(dr[6]),
                        "implement_date": _fmt(dr[7]),
                        "department":     dr[8],
                        "org_department": dr[9],
                        "publisher":      dr[10],
                        "note":           dr[11],
                    }

        return result
    except Exception as e:
        print(f"[DB] 获取记录详情失败: {e}", file=sys.stderr)
        return None
