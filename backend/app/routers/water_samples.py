from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.pond import Pond
from app.models.user import User
from app.models.water_sample import WaterSample
from app.schemas.water_sample import WaterSampleCreate, WaterSampleOut

router = APIRouter(prefix="/api/water-samples", tags=["water-samples"])

CONFLICT_DETAIL = "该塘口在该采样时刻已存在水质样，不能重复登记；如需修改请编辑原记录或先删除原记录"


def _find_conflict(
    db: Session, pond_id: int, sampled_at: datetime, exclude_id: Optional[int] = None
) -> Optional[WaterSample]:
    q = db.query(WaterSample).filter(
        WaterSample.pond_id == pond_id,
        WaterSample.sampled_at == sampled_at,
    )
    if exclude_id is not None:
        q = q.filter(WaterSample.id != exclude_id)
    return q.first()


def _commit(db: Session) -> None:
    """提交事务；唯一约束被并发写入触发时转成 409 而不是 500。"""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        message = str(exc.orig) if exc.orig is not None else ""
        if (
            constraint == "uq_water_samples_pond_sampled"
            or "uq_water_samples_pond_sampled" in message
            or "water_samples.pond_id" in message
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=CONFLICT_DETAIL
            )
        raise HTTPException(status_code=400, detail="保存失败：数据违反数据库约束")


@router.get("", response_model=List[WaterSampleOut])
def list_samples(
    pond_id: Optional[int] = Query(None, alias="pondId"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(WaterSample)
    if pond_id is not None:
        q = q.filter(WaterSample.pond_id == pond_id)
    # 历史脏数据可能含重复 (塘口, 时刻)，列表照常返回，不做唯一性断言
    return q.order_by(WaterSample.sampled_at.desc(), WaterSample.id.desc()).all()


@router.post("", response_model=WaterSampleOut, status_code=status.HTTP_201_CREATED)
def create_sample(
    payload: WaterSampleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    pond = db.query(Pond).filter(Pond.id == payload.pond_id).first()
    if not pond:
        raise HTTPException(status_code=400, detail="塘口不存在")
    if _find_conflict(db, payload.pond_id, payload.sampled_at) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CONFLICT_DETAIL)
    item = WaterSample(
        pond_id=payload.pond_id,
        sampled_at=payload.sampled_at,
        temp_c=payload.temp_c,
        salinity_ppt=payload.salinity_ppt,
        do_mg_l=payload.do_mg_l,
        ph=payload.ph,
        notes=payload.notes,
    )
    db.add(item)
    _commit(db)
    db.refresh(item)
    return item


@router.put("/{sample_id}", response_model=WaterSampleOut)
def update_sample(
    sample_id: int,
    payload: WaterSampleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(WaterSample).filter(WaterSample.id == sample_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="水质样不存在")
    pond = db.query(Pond).filter(Pond.id == payload.pond_id).first()
    if not pond:
        raise HTTPException(status_code=400, detail="塘口不存在")
    if _find_conflict(db, payload.pond_id, payload.sampled_at, exclude_id=sample_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=CONFLICT_DETAIL)
    item.pond_id = payload.pond_id
    item.sampled_at = payload.sampled_at
    item.temp_c = payload.temp_c
    item.salinity_ppt = payload.salinity_ppt
    item.do_mg_l = payload.do_mg_l
    item.ph = payload.ph
    item.notes = payload.notes
    _commit(db)
    db.refresh(item)
    return item


@router.delete("/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sample(
    sample_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(WaterSample).filter(WaterSample.id == sample_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="水质样不存在")
    db.delete(item)
    db.commit()
