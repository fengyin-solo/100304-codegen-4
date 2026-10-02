"""登录/登出/当前会话接口：前端刷新页面后凭 token 恢复同一个登录身份。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import (
    Account,
    USERS,
    current_user,
    issue_token,
)

router = APIRouter(prefix="/api/auth", tags=["会话授权"])


class LoginForm(BaseModel):
    login_name: str


@router.post("/login")
def login(form: LoginForm) -> dict[str, Any]:
    account = USERS.get(form.login_name.strip())
    if account is None:
        return {"ok": False, "message": "账号不存在，演示账号：envadmin（环保归口管理员）/ ops（运维人员）/ viewer（只读访客）"}
    token = issue_token(account.login_name)
    return {
        "ok": True,
        "message": f"欢迎，{account.display_name}",
        "token": token,
        "user": {
            "login_name": account.login_name,
            "display_name": account.display_name,
            "role": account.role,
            "role_label": account.role_label,
            "permissions": sorted(account.permissions),
        },
    }


@router.post("/logout")
def logout(user: Account | None = Depends(current_user)) -> dict[str, Any]:
    return {"ok": True, "message": "已退出登录" if user else "当前本就未登录"}


@router.get("/me")
def me(user: Account | None = Depends(current_user)) -> dict[str, Any]:
    if user is None:
        return {"ok": False, "user": None}
    return {
        "ok": True,
        "user": {
            "login_name": user.login_name,
            "display_name": user.display_name,
            "role": user.role,
            "role_label": user.role_label,
            "permissions": sorted(user.permissions),
        },
    }
