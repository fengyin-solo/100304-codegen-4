"""基站电磁环境备案接口。

覆盖：备案文书建档与 待提交/已受理/已备案/已失效 流转、退回后只补缺材料、
监测点位登记与限值版本换版，以及站点台账合规栏的统一取数入口。
路由层不做业务判断，全部交给 EmfilingService。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult

router = APIRouter(prefix="/api/emfiling", tags=["电磁环境备案"])

# 延迟导入，避免与站点台账模块在导入期互相牵扯。
from app.services.emfiling import (  # noqa: E402
    REQUIRED_MATERIALS,
    ROLE_CHOICES,
    EmfilingError,
    emfiling_service as service,
)

STATUSES = ["待提交", "已受理", "已备案", "已失效"]


def _role_of(payload: EntryPayload) -> str:
    return str(payload.values.get("role") or payload.values.get("operator_role") or "").strip()


@router.get("/meta")
def meta() -> dict[str, Any]:
    """页面初始化口径：可选角色、状态序列、材料清单都从后端取，避免两边写岔。"""
    return {
        "statuses": STATUSES,
        "roles": ROLE_CHOICES,
        "required_materials": REQUIRED_MATERIALS,
        "current_version": service.current_version(),
        "versions": service.list_versions(),
    }


@router.get("/versions")
def list_versions() -> dict[str, Any]:
    return {"items": service.list_versions(), "current": service.current_version()}


@router.post("/versions", response_model=ActionResult)
def publish_version(payload: EntryPayload) -> ActionResult:
    """发布新版限值（换版）；只授环保归口管理员。"""
    entry, message, missing = service.publish_version(payload.values, _role_of(payload))
    return ActionResult(ok=entry is not None, message=message, entry=entry, missing_permission=missing)


@router.get("/filings", response_model=PageResult[dict])
def list_filings(
    keyword: str | None = Query(default=None, description="按备案编号或站点编号检索"),
    status: str | None = Query(default=None, description="待提交、已受理、已备案、已失效"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_filings(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/filings/{filing_id}", response_model=dict)
def get_filing(filing_id: int) -> dict:
    try:
        entry = service.get_filing(filing_id)
    except EmfilingError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"备案 {filing_id} 不存在或已归档")
    return entry


@router.post("/filings", response_model=ActionResult)
def create_filing(payload: EntryPayload) -> ActionResult:
    try:
        entry, missing = service.create_filing(payload.values)
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="备案档案已建立，状态为待提交", entry=entry)


@router.post("/filings/{filing_id}/submit", response_model=ActionResult)
def submit_filing(filing_id: int) -> ActionResult:
    try:
        entry, message = service.submit_filing(filing_id)
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/filings/{filing_id}/return", response_model=ActionResult)
def return_filing(filing_id: int, payload: EntryPayload) -> ActionResult:
    try:
        entry, message = service.return_filing(filing_id, payload.values.get("退回原因"))
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.post("/filings/{filing_id}/decision", response_model=ActionResult)
def decide_filing(filing_id: int, payload: EntryPayload) -> ActionResult:
    """签发备案结论（已受理→已备案）；越权打回并写明缺的授权项。"""
    try:
        entry, message, missing = service.decide_filing(filing_id, payload.values, _role_of(payload))
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message, missing_permission=exc.missing_permission)
    return ActionResult(ok=entry is not None, message=message, entry=entry, missing_permission=missing)


@router.post("/filings/{filing_id}/expire", response_model=ActionResult)
def expire_filing(filing_id: int) -> ActionResult:
    try:
        entry, message = service.expire_filing(filing_id)
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.get("/filings/{filing_id}/materials")
def list_materials(filing_id: int) -> dict[str, Any]:
    try:
        items = service.list_materials(filing_id)
    except EmfilingError as exc:
        raise HTTPException(status_code=404, detail=exc.message)
    return {"items": items}


@router.post("/filings/{filing_id}/materials", response_model=ActionResult)
def supplement_material(filing_id: int, payload: EntryPayload) -> ActionResult:
    """退回补交：只收缺的/不合规的材料，已交的不允许重复提交。"""
    try:
        entry, message = service.supplement_material(filing_id, payload.values)
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.get("/points")
def list_points(filing_id: int | None = None) -> dict[str, Any]:
    return {"items": service.list_points(filing_id)}


@router.post("/points", response_model=ActionResult)
def register_point(payload: EntryPayload) -> ActionResult:
    """按监测点位登记功率密度和监测日期；越线点位一律记不合格。"""
    try:
        entry, message = service.register_point(payload.values)
    except EmfilingError as exc:
        return ActionResult(ok=False, message=exc.message)
    return ActionResult(ok=entry is not None, message=message, entry=entry)


@router.get("/site-compliance")
def site_compliance(site_no: str = Query(..., description="站点编号（基站编号）")) -> dict[str, Any]:
    """另一个入口查备案结论：与站点台账合规栏取的是同一份计算结果。"""
    return service.site_compliance(site_no)


@router.get("/export")
def export_filings() -> dict[str, Any]:
    items, total = service.list_filings(page=1, size=10000)
    return {"module": "emfiling", "total": total, "items": items}
