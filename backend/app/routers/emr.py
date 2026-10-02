"""基站电磁环境备案接口：限值版本、监测点位、备案文书、备案结论（唯一事实源）。

权限口径：
- 读接口（列表/详情/站点合规栏）不设限，任何入口读到的都是同一份结论；
- 出具备案结论（受理后备案）、退回审查、限值换版、更正结论，仅环保归口管理员可执行，
  越权由 auth.require_perm 统一打回 403，并在提示里写明缺的授权项。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import (
    Account,
    PERM_CONCLUSION_EDIT,
    PERM_LIMIT_PUBLISH,
    PERM_REVIEW,
    current_user,
    require_perm,
)
from app.schemas import ActionResult, PageResult
from app.services.emr import (
    REQUIRED_MATERIALS,
    STATUS_ACCEPTED,
    STATUS_DRAFT,
    STATUS_FILED,
    emr_service,
)

router = APIRouter(prefix="/api/emr", tags=["电磁环境备案"])


class LoginPayload(BaseModel):
    values: dict[str, Any]


def _operator(user: Account | None) -> str:
    return user.display_name if user else "未登录操作人"


# ---------------- 限值版本 ----------------
@router.get("/limits")
def list_limits() -> dict[str, Any]:
    """限值版本清单与当前版本。"""
    rows = emr_service.list_limits()
    return {"items": rows, "current": emr_service.current_limit()}


@router.post("/limits/publish", response_model=ActionResult)
def publish_limit(payload: LoginPayload,
                  user: Account = Depends(current_user)) -> ActionResult:
    """限值换版：仅环保归口管理员；发布后存量站点自动按新版重算现行符合性。"""
    account = require_perm(user, PERM_LIMIT_PUBLISH)
    entry, missing = emr_service.publish_limit(payload.values, operator=account.display_name)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True,
                        message=f"限值新版本 {entry['版本编号']} 已发布，存量站点现行符合性已按新版重算（留档结论不变）",
                        entry=entry)


# ---------------- 监测点位 ----------------
@router.get("/measures", response_model=PageResult[dict])
def list_measures(site: str | None = Query(default=None, description="按站点编号过滤")) -> PageResult[dict]:
    items = emr_service.list_measures(site)
    return PageResult(items=items, total=len(items), page=1, size=len(items) or 1)


@router.post("/measures", response_model=ActionResult)
def register_measure(payload: LoginPayload,
                     user: Account = Depends(current_user)) -> ActionResult:
    """登记监测点位的功率密度与监测日期；合格与否服务端裁定，越线一律不合格。"""
    require_perm(user, PERM_REVIEW)  # 监测数据登记归口环保，运维越权同样打回
    entry, error = emr_service.register_measure(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=error or "监测点位登记失败")
    tip = "监测越线，已记为不合格，备案不得出具合格结论" if entry["监测结论"] == "不合格" else "监测点位已登记，结论为合格"
    return ActionResult(ok=True, message=tip, entry=entry)


# ---------------- 备案文书 ----------------
@router.get("/filings", response_model=PageResult[dict])
def list_filings(
    status: str | None = Query(default=None, description="待提交、已受理、已备案、已失效"),
    keyword: str | None = Query(default=None, description="按站点编号/名称/备案编号检索"),
) -> PageResult[dict]:
    items = emr_service.list_filings(status=status, keyword=keyword)
    return PageResult(items=items, total=len(items), page=1, size=len(items) or 1)


@router.get("/filings/{filing_id}", response_model=dict)
def get_filing(filing_id: int) -> dict[str, Any]:
    entry = emr_service.get_filing(filing_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"备案档案 {filing_id} 不存在")
    return entry


@router.post("/filings/{filing_id}/submit", response_model=ActionResult)
def submit_filing(filing_id: int, user: Account = Depends(current_user)) -> ActionResult:
    """提交受理：被退回的档案只校验剩余缺失材料，交过的不要求再交。"""
    require_perm(user, PERM_REVIEW)
    entry, message = emr_service.submit_filing(filing_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/filings/{filing_id}/supplement", response_model=ActionResult)
def supplement_filing(filing_id: int, payload: LoginPayload,
                      user: Account = Depends(current_user)) -> ActionResult:
    """补交材料：只补缺的那几份，重复提交已交材料会被明确告知无需再交。"""
    require_perm(user, PERM_REVIEW)
    materials = payload.values.get("materials") or []
    if isinstance(materials, str):
        materials = [materials]
    entry, message = emr_service.supplement(filing_id, list(materials))
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/filings/{filing_id}/accept", response_model=ActionResult)
def accept_filing(filing_id: int, user: Account = Depends(current_user)) -> ActionResult:
    """受理审查 → 出具备案结论。结论修改/出具权限：仅环保归口管理员。"""
    account = require_perm(user, PERM_CONCLUSION_EDIT)
    entry, message = emr_service.accept_filing(filing_id, operator=account.display_name)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/filings/{filing_id}/return", response_model=ActionResult)
def return_filing(filing_id: int, payload: LoginPayload,
                  user: Account = Depends(current_user)) -> ActionResult:
    """退回补正：点出缺哪几份材料，只把这几份打回，其余保留。"""
    account = require_perm(user, PERM_REVIEW)
    values = payload.values
    missing = values.get("missing_materials") or []
    if isinstance(missing, str):
        missing = [missing]
    missing = [m for m in missing if m in REQUIRED_MATERIALS]
    entry, message = emr_service.return_filing(
        filing_id, reason=str(values.get("reason") or ""),
        missing_materials=missing, operator=account.display_name)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/filings/{filing_id}/expire", response_model=ActionResult)
def expire_filing(filing_id: int, user: Account = Depends(current_user)) -> ActionResult:
    """已备案 → 已失效，结论同步归档，站点台账合规栏同步。"""
    account = require_perm(user, PERM_REVIEW)
    entry, message = emr_service.expire_filing(filing_id, operator=account.display_name)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/filings/{filing_id}/conclusion", response_model=ActionResult)
def amend_conclusion(filing_id: int, payload: LoginPayload,
                     user: Account = Depends(current_user)) -> ActionResult:
    """更正备案结论：只给环保归口管理员；越权提交一律 403 打回并写明缺的授权项。

    即便有权限，服务端仍会按最新监测数据复核，越线站点不允许改成合格。
    """
    account = require_perm(user, PERM_CONCLUSION_EDIT)
    verdict = str(payload.values.get("verdict") or "").strip()
    note = str(payload.values.get("note") or "").strip()
    entry, message = emr_service.amend_conclusion(
        filing_id, verdict=verdict, note=note, operator=account.display_name)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# ---------------- 站点台账合规栏（外部入口） ----------------
@router.get("/sites/{site_code}/conclusion", response_model=dict)
def site_conclusion(site_code: str) -> dict[str, Any]:
    """其他入口按站点编号读备案结论；与备案详情页是同一个数据源的同一份结果。"""
    return emr_service.site_compliance(site_code)
