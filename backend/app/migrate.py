"""Best-effort schema upgrades for databases created before constraints existed.

create_all only creates missing tables — it never alters an existing one, so a
water_samples table created by an older release lacks the (pond_id, sampled_at)
unique constraint. ensure_water_sample_uniqueness() adds it when possible.

If dirty duplicate rows still block the constraint, the upgrade is skipped with
a warning and the app keeps running (the API rejects conflicting writes at the
application level in the meantime). Delete the duplicate rows manually and the
constraint is applied on the next boot. This function must never fail startup.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

CONSTRAINT_NAME = "uq_water_samples_pond_sampled"


def ensure_water_sample_uniqueness(engine: Engine) -> None:
    try:
        insp = inspect(engine)
        if "water_samples" not in insp.get_table_names():
            return
        for constraint in insp.get_unique_constraints("water_samples"):
            if set(constraint.get("column_names") or []) == {"pond_id", "sampled_at"}:
                return
        with engine.begin() as conn:
            duplicates = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "SELECT 1 FROM water_samples "
                    "GROUP BY pond_id, sampled_at HAVING COUNT(*) > 1"
                    ") AS dup"
                )
            ).scalar()
            if duplicates:
                print(
                    f"WARNING: water_samples has {duplicates} duplicate "
                    f"(pond_id, sampled_at) groups; skipping unique constraint "
                    f"{CONSTRAINT_NAME} until they are removed manually."
                )
                return
            conn.execute(
                text(
                    f"ALTER TABLE water_samples "
                    f"ADD CONSTRAINT {CONSTRAINT_NAME} "
                    f"UNIQUE (pond_id, sampled_at)"
                )
            )
            print(f"Added unique constraint {CONSTRAINT_NAME} on water_samples.")
    except Exception as exc:  # never block app startup on a best-effort upgrade
        print(f"WARNING: could not ensure water_samples uniqueness: {exc}")
