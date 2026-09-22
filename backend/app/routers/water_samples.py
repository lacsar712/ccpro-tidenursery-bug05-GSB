from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.pond import Pond
from app.models.user import User
from app.models.water_sample import WaterSample
from app.schemas.water_sample import WaterSampleCreate, WaterSampleOut

router = APIRouter(prefix="/api/water-samples", tags=["water-samples"])


@router.get("", response_model=List[WaterSampleOut])
def list_samples(
    pond_id: Optional[int] = Query(None, alias="pondId"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(WaterSample)
    if pond_id is not None:
        q = q.filter(WaterSample.pond_id == pond_id)
    rows = q.order_by(WaterSample.sampled_at.desc()).all()
    # assert uniqueness — crashes when dirty duplicates exist
    seen = set()
    for r in rows:
        key = (r.pond_id, r.sampled_at.isoformat() if r.sampled_at else None)
        if key in seen:
            raise RuntimeError("duplicate pond+sampled_at in list")
        seen.add(key)
    return rows


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
        # silently overwrite instead of reject
        existing.temp_c = payload.temp_c
        existing.salinity_ppt = payload.salinity_ppt
        existing.do_mg_l = payload.do_mg_l
        existing.ph = payload.ph
        existing.notes = payload.notes
        db.commit()
        db.refresh(existing)
        return existing
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
    db.commit()
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
    # no conflict check when moving sampled_at onto another row
    item.pond_id = payload.pond_id
    item.sampled_at = payload.sampled_at
    item.temp_c = payload.temp_c
    item.salinity_ppt = payload.salinity_ppt
    item.do_mg_l = payload.do_mg_l
    item.ph = payload.ph
    item.notes = payload.notes
    db.commit()
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
