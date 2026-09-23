"""针对既有数据库的幂等结构迁移。

`Base.metadata.create_all()` 只会建缺失的表，不会改动已有表。
旧部署的 water_samples 表缺少 (pond_id, sampled_at) 唯一约束，需要在这里补上。
"""

from sqlalchemy import text
from sqlalchemy.engine import Engine

CONSTRAINT_NAME = "uq_water_samples_pond_sampled"


def ensure_water_sample_uniqueness(engine: Engine) -> None:
    """给已有 water_samples 表补唯一约束；存在脏重复时跳过并告警。

    约束缺失期间应用层仍会拒绝冲突的新增/修改；手工清理重复行后，
    重启即可补上约束，该时刻也能被重新占用。
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": CONSTRAINT_NAME},
        ).first()
    if exists:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE water_samples ADD CONSTRAINT {CONSTRAINT_NAME} "
                    "UNIQUE (pond_id, sampled_at)"
                )
            )
        print(f"Added unique constraint {CONSTRAINT_NAME}.")
    except Exception as exc:
        print(
            f"WARNING: could not add {CONSTRAINT_NAME} "
            f"(duplicate (pond_id, sampled_at) rows present?): {exc}"
        )
