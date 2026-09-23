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

DUPLICATE_DETAIL = "该塘口在该采样时刻已有水质样，同一塘口同一时刻只能登记一条"


@router.get("", response_model=List[WaterSampleOut])
def list_samples(
    pond_id: Optional[int] = Query(None, alias="pondId"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(WaterSample)
    if pond_id is not None:
        q = q.filter(WaterSample.pond_id == pond_id)
    # dirty duplicate rows (from before the unique constraint) must not break listing
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
    existing = (
        db.query(WaterSample)
        .filter(
            WaterSample.pond_id == payload.pond_id,
            WaterSample.sampled_at == payload.sampled_at,
        )
        .first()
    )
    if existing:
        # reject the conflict — never silently overwrite the existing row
        raise HTTPException(status_code=400, detail=DUPLICATE_DETAIL)
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
    try:
        db.commit()
    except IntegrityError:
        # lost the race against a concurrent insert of the same pond+moment
        db.rollback()
        raise HTTPException(status_code=400, detail=DUPLICATE_DETAIL)
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
    conflict = (
        db.query(WaterSample)
        .filter(
            WaterSample.pond_id == payload.pond_id,
            WaterSample.sampled_at == payload.sampled_at,
            WaterSample.id != sample_id,
        )
        .first()
    )
    if conflict:
        raise HTTPException(status_code=400, detail=DUPLICATE_DETAIL)
    item.pond_id = payload.pond_id
    item.sampled_at = payload.sampled_at
    item.temp_c = payload.temp_c
    item.salinity_ppt = payload.salinity_ppt
    item.do_mg_l = payload.do_mg_l
    item.ph = payload.ph
    item.notes = payload.notes
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=DUPLICATE_DETAIL)
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
