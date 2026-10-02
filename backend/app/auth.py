"""会话与授权：平台没有真实用户库，这里用内存账号模拟登录态。

- 账号在 USERS 里固定，登录换发 token；
- 角色分两类：env_admin（环保归口管理员）和 ops（运维人员），另有 viewer（只读）；
- 需要权限的接口依赖 require_perm，缺权限直接抛 403，并在 detail 里写明缺的是哪一项授权。
"""
from __future__ import annotations

from dataclasses import dataclass
from fastapi import Header, HTTPException

# 授权点：权限名字就是越权提示里要写清楚的“缺的那一项授权”。
PERM_CONCLUSION_EDIT = "emr:conclusion:edit"  # 出具/修改备案结论
PERM_REVIEW = "emr:review"  # 受理、退回、备案审查
PERM_LIMIT_PUBLISH = "emr:limit:publish"  # 限值换版发布

PERM_LABELS = {
    PERM_CONCLUSION_EDIT: "环保归口·备案结论修改",
    PERM_REVIEW: "环保归口·备案审查",
    PERM_LIMIT_PUBLISH: "环保归口·限值版本发布",
}


@dataclass(frozen=True)
class Account:
    login_name: str
    display_name: str
    role: str
    role_label: str
    permissions: frozenset[str]


# 固定账号：一个环保归口管理员、一个运维人员、一个只读访客。
USERS: dict[str, Account] = {
    "envadmin": Account(
        login_name="envadmin",
        display_name="归环保·林岚",
        role="env_admin",
        role_label="环保归口管理员",
        permissions=frozenset({PERM_CONCLUSION_EDIT, PERM_REVIEW, PERM_LIMIT_PUBLISH}),
    ),
    "ops": Account(
        login_name="ops",
        display_name="网优·周岭",
        role="ops",
        role_label="运维人员",
        permissions=frozenset(),
    ),
    "viewer": Account(
        login_name="viewer",
        display_name="查阅·访客",
        role="viewer",
        role_label="只读访客",
        permissions=frozenset(),
    ),
}

# token 直接等于登录名，内存态重启即失效，符合当前骨架的演示定位。
TOKENS: dict[str, str] = {}


def issue_token(login_name: str) -> str:
    token = f"tok-{login_name}"
    TOKENS[token] = login_name
    return token


def account_from_token(token: str | None) -> Account | None:
    if not token:
        return None
    login_name = TOKENS.get(token.removeprefix("Bearer "))
    if login_name is None:
        return None
    return USERS.get(login_name)


def current_user(
    authorization: str | None = Header(default=None),
    x_token: str | None = Header(default=None),
) -> Account | None:
    """可选登录态：读接口允许匿名，写接口自行决定要什么权限。"""
    return account_from_token(authorization or x_token)


def require_login(user: Account | None) -> Account:
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或登录已失效，请重新登录后再操作")
    return user


def require_perm(user: Account | None, permission: str) -> Account:
    """越权一律打回，并写明差的是哪一项授权。"""
    account = require_login(user)
    if permission not in account.permissions:
        label = PERM_LABELS.get(permission, permission)
        raise HTTPException(
            status_code=403,
            detail=(
                f"越权操作被打回：当前账号「{account.display_name}」（{account.role_label}）"
                f"缺少授权项「{label}」（{permission}），仅环保归口管理员可执行本操作"
            ),
        )
    return account
