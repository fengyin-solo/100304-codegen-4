"""基站电磁环境备案业务规则。

一份「能对上的档案」拆成四张表，全部落在内存仓库里：

- ``emfiling_limit_versions``：功率密度限值版本，谁是现行版由 ``current`` 标记，
  换版只新增版本、不改老版本，存量监测记录按监测当时那版留档。
- ``emfiling_points``：监测点位档案，按点位登记功率密度和监测日期；登记当时用
  现行限值判定，越线的点位结论只能是「不合格」，不接受人工覆盖。
- ``emfiling_filings``：备案文书主表，沿 待提交→已受理→已备案→已失效 流转，
  被退回回到「待提交」只补缺的材料。
- ``emfiling_materials``：每份备案的材料清单与补交状态。

备案结论的权威来源只有本模块一个出口：站点台账的合规栏和台账的另一个查询入口
都调用 :meth:`EmfilingService.site_compliance` 取同一份计算结果，刷新页面或退出
重进拿到的都是同一条。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "emfiling_filings"
T_FILINGS = "emfiling_filings"
T_POINTS = "emfiling_points"
T_MATERIALS = "emfiling_materials"
T_VERSIONS = "emfiling_limit_versions"

# 备案文书状态机：只允许沿序列前进；退回是唯一的回退，且只回到「待提交」。
STATUS_ORDER = ["待提交", "已受理", "已备案", "已失效"]
STATUS_REJECTED = "待提交"

REQUIRED_FIELDS = ["备案编号", "站点编号", "站点名称"]
REQUIRED_MATERIALS = ["电磁环境监测报告", "天线及辐射设备布设图", "基站基本信息表", "电磁环境影响说明"]

# 结论只有两种；合格的硬条件是全部监测点位都不越「现行版」限值。
CONCLUSION_PASS = "备案合格"
CONCLUSION_FAIL = "备案不合格"

# 站点台账合规栏取到的文案；另一个入口读到的也是这里的同一份字符串。
SITE_PASS = "合规"
SITE_FAIL_LIMIT = "不合规·监测越现行限值"
SITE_FAIL_CONCLUSION = "不合规·备案结论不合格"
SITE_NO_FILING = "未备案"
SITE_EXPIRED = "已失效"
SITE_PENDING = "备案办理中"

# 修改备案结论 / 发布新版限值只授给环保归口管理员；越权时明确写出缺的授权项。
ENV_ADMIN_ROLE = "环保归口管理员"
ENV_ADMIN_PERMISSION = "环保归口管理员（电磁环境备案结论签发）"
ROLE_CHOICES = ["值班管理员", "运维人员", ENV_ADMIN_ROLE]


class EmfilingError(Exception):
    """业务校验失败：消息直接回给页面，missing_permission 指明缺哪一项授权。"""

    def __init__(self, message: str, *, missing_permission: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.missing_permission = missing_permission


def _today() -> str:
    return date.today().isoformat()


def _new_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _parse_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise EmfilingError(f"{field}必须是数字，收到的是「{value}」")
    if number < 0:
        raise EmfilingError(f"{field}不能为负数")
    return number


def _parse_date(value: Any) -> str:
    text = str(value or "").strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        raise EmfilingError("监测日期格式应为 YYYY-MM-DD")
    return text


class EmfilingService:
    # ---------- 限值版本 ----------

    def list_versions(self) -> list[dict[str, Any]]:
        return list(store.rows(T_VERSIONS))

    def current_version(self) -> dict[str, Any] | None:
        for version in store.rows(T_VERSIONS):
            if version.get("current"):
                return version
        return None

    def _version(self, version_id: int) -> dict[str, Any] | None:
        return store.find(T_VERSIONS, version_id)

    def publish_version(self, values: dict[str, Any], role: str) -> tuple[dict[str, Any] | None, str, str | None]:
        """发布新版限值：老版全部置为非现行，存量站点按新版重算；留档版本不动。"""
        denied = self._check_env_admin(role)
        if denied:
            return None, denied.message, denied.missing_permission

        code = str(values.get("标准号") or "").strip()
        if not code:
            return None, "标准号不能为空", None
        try:
            limit = _parse_float(values.get("功率密度限值"), "功率密度限值")
        except EmfilingError as exc:
            return None, exc.message, None
        effective_on = _parse_date(values.get("生效日期", _today()))

        rows = store.rows(T_VERSIONS)
        if any(str(row.get("标准号")) == code and float(row.get("功率密度限值", 0)) == limit for row in rows):
            return None, f"标准号 {code}、限值 {limit} W/m² 的版本已经存在，无需重复发布", None

        for row in rows:
            row["current"] = False
        version = {
            "id": _new_id(rows),
            "标准号": code,
            "版本说明": str(values.get("版本说明") or "").strip() or f"{code} 限值换版",
            "功率密度限值": limit,
            "生效日期": effective_on,
            "current": True,
        }
        rows.append(version)
        affected = self._recompute_existing(version)
        self._sync_all_sites()
        return version, f"新版限值已发布为现行版，{affected} 个存量站点按 {limit} W/m² 重算，留档仍按监测当时版本", None

    # ---------- 备案文书 ----------

    def list_filings(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(T_FILINGS)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("备案编号", "")) or keyword in str(row.get("站点编号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._decorate_filing(row) for row in rows[start:start + size]], total

    def get_filing(self, filing_id: int) -> dict[str, Any] | None:
        row = store.find(T_FILINGS, filing_id)
        return self._decorate_filing(row) if row else None

    def create_filing(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(T_FILINGS)
        filing_no = str(values.get("备案编号")).strip()
        if any(str(row.get("备案编号")) == filing_no for row in rows):
            raise EmfilingError(f"备案编号 {filing_no} 已存在，同一份备案不能重复建档")
        entry = {
            "id": _new_id(rows),
            "备案编号": filing_no,
            "站点编号": str(values.get("站点编号")).strip(),
            "站点名称": str(values.get("站点名称")).strip(),
            "status": STATUS_ORDER[0],
            "备案结论": None,
            "结论签发时间": None,
            "判定限值版本id": None,
            "全部点位现行合格": False,
            "现行限值判定": None,
            "pending": True,
            "abnormal": False,
            "最近更新": _today(),
        }
        rows.append(entry)
        material_rows = store.rows(T_MATERIALS)
        for name in REQUIRED_MATERIALS:
            material_rows.append({
                "id": _new_id(material_rows),
                "filing_id": entry["id"],
                "材料名称": name,
                "status": "缺交",
                "提交时间": None,
                "备注": None,
            })
        self._sync_site(entry["站点编号"])
        return self._decorate_filing(entry), []

    def submit_filing(self, filing_id: int) -> tuple[dict[str, Any] | None, str]:
        """待提交 → 已受理：四项材料缺一项都不收，明确列出还缺什么。"""
        filing = self._require_filing(filing_id)
        if filing["status"] != "待提交":
            return None, f"当前状态为「{filing['status']}」，只有「待提交」的备案可以提交受理"
        missing = self._missing_materials(filing_id)
        if missing:
            return None, f"材料不齐，暂不受理；还缺：{'、'.join(missing)}"
        filing["status"] = "已受理"
        filing["最近更新"] = _today()
        filing["pending"] = True
        self._sync_site(filing["站点编号"])
        return self._decorate_filing(filing), "备案材料已收齐，文书受理"

    def return_filing(self, filing_id: int, reason: str | None) -> tuple[dict[str, Any] | None, str]:
        """已受理 → 待提交（退回）：已交材料保留，补交时只补缺的那几份。"""
        filing = self._require_filing(filing_id)
        if filing["status"] != "已受理":
            return None, f"当前状态为「{filing['status']}」，只有「已受理」的备案可以退回"
        filing["status"] = STATUS_REJECTED
        filing["最近更新"] = _today()
        filing["pending"] = True
        note = str(reason or "").strip() or "材料需补正"
        # 被点名为问题项的材料标成「不合规」，其余已交材料继续留档、不用再交。
        if note and note != "材料需补正":
            for material in self._materials(filing_id):
                if material["status"] in ("已提交", "不合规") and material["材料名称"] in note:
                    material["status"] = "不合规"
                    material["备注"] = note
        self._sync_site(filing["站点编号"])
        kept = [m["材料名称"] for m in self._materials(filing_id) if m["status"] == "已提交"]
        tail = f"；已交且无需重交：{'、'.join(kept)}" if kept else ""
        return self._decorate_filing(filing), f"备案已退回：{note}。补交时只需补未交/不合规的材料{tail}"

    def decide_filing(
        self, filing_id: int, values: dict[str, Any], role: str
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        """已受理 → 已备案：结论签发权只给环保归口管理员；越线一律不许记合格。"""
        denied = self._check_env_admin(role)
        if denied:
            return None, denied.message, denied.missing_permission

        filing = self._require_filing(filing_id)
        if filing["status"] != "已受理":
            return None, f"当前状态为「{filing['status']}」，只有「已受理」的备案可以出具结论", None

        # 硬规则先于一切：辐射监测值越线的，环保管理员也不能记成合格。
        self._recompute_filing(filing)
        if not filing["全部点位现行合格"]:
            filing["备案结论"] = CONCLUSION_FAIL
            filing["判定限值版本id"] = self.current_version()["id"]
            filing["结论签发时间"] = _today()
            filing["最近更新"] = _today()
            filing["status"] = "已备案"
            filing["pending"] = False
            filing["abnormal"] = True
            self._sync_site(filing["站点编号"])
            return self._decorate_filing(filing), (
                f"存在监测点位功率密度越出现行限值 {filing['现行限值判定']} W/m²，"
                "已按规则记为「备案不合格」，不允许记成合格"
            ), None

        requested = str(values.get("备案结论") or "").strip()
        if requested and requested not in (CONCLUSION_PASS, CONCLUSION_FAIL):
            return None, f"备案结论只能是「{CONCLUSION_PASS}」或「{CONCLUSION_FAIL}」", None
        conclusion = requested or CONCLUSION_PASS
        filing["备案结论"] = conclusion
        filing["判定限值版本id"] = self.current_version()["id"]
        filing["结论签发时间"] = _today()
        filing["最近更新"] = _today()
        filing["status"] = "已备案"
        filing["pending"] = False
        filing["abnormal"] = conclusion == CONCLUSION_FAIL
        self._sync_site(filing["站点编号"])
        return self._decorate_filing(filing), f"备案结论已签发：{conclusion}，同步进站点台账合规栏", None

    def expire_filing(self, filing_id: int) -> tuple[dict[str, Any] | None, str]:
        filing = self._require_filing(filing_id)
        if filing["status"] not in ("已备案", "已受理", "待提交"):
            return None, f"当前状态为「{filing['status']}」，无需再置为失效"
        filing["status"] = "已失效"
        filing["pending"] = False
        filing["最近更新"] = _today()
        self._sync_site(filing["站点编号"])
        return self._decorate_filing(filing), "备案已失效，站点台账合规栏同步更新"

    # ---------- 材料补交 ----------

    def list_materials(self, filing_id: int) -> list[dict[str, Any]]:
        self._require_filing(filing_id)
        return list(self._materials(filing_id))

    def supplement_material(
        self, filing_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """补交材料：已交且合格的不允许重复提交，只收缺交/不合规的那几份。"""
        filing = self._require_filing(filing_id)
        if filing["status"] != "待提交":
            return None, f"当前状态为「{filing['status']}」，只有被退回待补正的备案需要补交材料"
        name = str(values.get("材料名称") or "").strip()
        material = next((m for m in self._materials(filing_id) if m["材料名称"] == name), None)
        if material is None:
            return None, f"材料「{name}」不在本备案的必备材料清单里"
        if material["status"] == "已提交":
            return None, f"材料「{name}」已提交并留档，补交时无需重复提交"
        material["status"] = "已提交"
        material["提交时间"] = _today()
        material["备注"] = str(values.get("备注") or "退回补交").strip()
        filing["最近更新"] = _today()
        still_missing = self._missing_materials(filing_id)
        tail = "；材料已齐，可重新提交受理" if not still_missing else f"；仍缺：{'、'.join(still_missing)}"
        return material, f"已补交「{name}」，原已交材料保持不动{tail}"

    # ---------- 监测点位 ----------

    def list_points(self, filing_id: int | None = None) -> list[dict[str, Any]]:
        rows = store.rows(T_POINTS)
        if filing_id is not None:
            rows = [row for row in rows if int(row.get("filing_id", 0)) == filing_id]
        return [dict(row) for row in rows]

    def register_point(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记监测点位：功率密度+监测日期；按登记当时现行限值判定，越线即不合格。"""
        filing_id = values.get("filing_id")
        filing = store.find(T_FILINGS, int(filing_id)) if filing_id is not None else None
        if filing is None:
            site_no = str(values.get("站点编号") or "").strip()
            filing = next(
                (row for row in store.rows(T_FILINGS) if str(row.get("站点编号")) == site_no), None
            )
        if filing is None:
            return None, "该站点还没有备案档案，请先登记备案再录监测点位"

        point_no = str(values.get("监测点位编号") or "").strip()
        if not point_no:
            return None, "监测点位编号不能为空"
        try:
            density = _parse_float(values.get("功率密度"), "功率密度")
            monitored_on = _parse_date(values.get("监测日期"))
        except EmfilingError as exc:
            return None, exc.message

        rows = store.rows(T_POINTS)
        if any(str(row.get("监测点位编号")) == point_no for row in rows):
            return None, f"监测点位 {point_no} 已登记，同一点位请新增复测记录而不是覆盖"

        # 留档口径：登记当时哪版是现行版，就永远按哪版判定，换版不改这条记录。
        version = self._version_at(monitored_on) or self.current_version()
        conclusion = "合格" if density <= float(version["功率密度限值"]) else "不合格"
        point = {
            "id": _new_id(rows),
            "filing_id": filing["id"],
            "站点编号": filing["站点编号"],
            "监测点位编号": point_no,
            "功率密度": density,
            "监测日期": monitored_on,
            "判定限值版本id": version["id"],
            "判定限值标准号": version["标准号"],
            "判定限值": float(version["功率密度限值"]),
            "留档结论": conclusion,
            "现行限值结论": None,
        }
        rows.append(point)
        self._recompute_filing(filing)
        self._sync_site(filing["站点编号"])
        message = (
            f"监测点位 {point_no} 已登记：{density} W/m²，按监测当时限值"
            f"{version['功率密度限值']} W/m²（{version['标准号']}）判定为「{conclusion}」"
        )
        if conclusion == "不合格":
            message += "；越线点位不得记为合格，备案结论将被锁为不合格"
        return point, message

    def _version_at(self, day: str) -> dict[str, Any] | None:
        """监测当时的现行版：取生效日期不晚于监测日期的最新一版。"""
        candidates = [
            row for row in store.rows(T_VERSIONS) if str(row.get("生效日期", "")) <= day
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda row: (str(row["生效日期"]), int(row["id"])))[-1]

    # ---------- 站点合规同步（唯一权威出口） ----------

    def site_compliance(self, site_no: str) -> dict[str, Any]:
        """站点台账合规栏与另一个查询入口共用的取数口径。"""
        filing = next(
            (row for row in store.rows(T_FILINGS) if str(row.get("站点编号")) == site_no), None
        )
        if filing is None:
            return {
                "站点编号": site_no,
                "备案编号": None,
                "备案状态": None,
                "备案结论": None,
                "合规栏": SITE_NO_FILING,
                "合规": False,
                "判定限值标准号": None,
                "最近更新": None,
            }
        self._recompute_filing(filing)
        version = self.current_version()
        if filing["status"] == "已备案":
            # 已备案档案也要按现行版重算口径展示：越线即不合规，哪怕结论尚未补签。
            if not filing["全部点位现行合格"]:
                label, compliant = SITE_FAIL_LIMIT, False
            else:
                label = SITE_PASS if filing["备案结论"] == CONCLUSION_PASS else SITE_FAIL_CONCLUSION
                compliant = filing["备案结论"] == CONCLUSION_PASS
        elif filing["status"] == "已失效":
            label, compliant = SITE_EXPIRED, False
        elif filing["status"] == "待提交":
            label, compliant = SITE_PENDING, False
        else:  # 已受理：看现行限值重算结果，提前暴露越线
            label = SITE_PASS if filing["全部点位现行合格"] else SITE_FAIL_LIMIT
            compliant = filing["全部点位现行合格"]
        return {
            "站点编号": site_no,
            "备案编号": filing["备案编号"],
            "备案状态": filing["status"],
            "备案结论": filing["备案结论"],
            "合规栏": label,
            "合规": compliant,
            "判定限值标准号": version["标准号"] if version else None,
            "现行限值": version["功率密度限值"] if version else None,
            "最近更新": filing["最近更新"],
        }

    def compliance_map(self) -> dict[str, dict[str, Any]]:
        """给站点台账批量补合规栏用：仍然全部走 site_compliance，不做第二套口径。"""
        site_nos = [str(row.get("站点编号")) for row in store.rows(T_FILINGS)]
        # 同时覆盖站点台账里已有但未备案的站点。
        site_nos.extend(str(row.get("基站编号")) for row in store.rows("site"))
        return {no: self.site_compliance(no) for no in dict.fromkeys(site_nos) if no}

    # ---------- 内部规则 ----------

    def _recompute_existing(self, version: dict[str, Any]) -> int:
        """限值换版：存量站点的点位按新版重算「现行限值结论」，留档结论原样保留。"""
        limit = float(version["功率密度限值"])
        for point in store.rows(T_POINTS):
            point["现行限值结论"] = "合格" if float(point["功率密度"]) <= limit else "不合格"
        touched = set()
        for filing in store.rows(T_FILINGS):
            self._apply_version_recalc(filing)
            touched.add(str(filing["站点编号"]))
        return len(touched)

    def _recompute_filing(self, filing: dict[str, Any]) -> None:
        """按现行版重算一份备案的点位总体结果；不改任何点位的留档结论。"""
        version = self.current_version()
        points = [p for p in store.rows(T_POINTS) if int(p.get("filing_id", 0)) == int(filing["id"])]
        limit = float(version["功率密度限值"]) if version else None
        for point in points:
            point["现行限值结论"] = (
                "合格" if limit is not None and float(point["功率密度"]) <= limit else "不合格"
            )
        all_pass = bool(points) and all(point["现行限值结论"] == "合格" for point in points)
        filing["全部点位现行合格"] = all_pass
        filing["现行限值判定"] = limit

    def _apply_version_recalc(self, filing: dict[str, Any]) -> None:
        """换版时刻专用：在重算点位的基础上，把已备案合格但越新版限值的档案打回不合格。

        读取/列表不做任何结论改写，保证「留档还是按监测当时那一版」。
        """
        self._recompute_filing(filing)
        if (
            filing["status"] == "已备案"
            and filing["备案结论"] == CONCLUSION_PASS
            and not filing["全部点位现行合格"]
        ):
            filing["备案结论"] = CONCLUSION_FAIL
            filing["abnormal"] = True
            filing["最近更新"] = _today()

    def _sync_site(self, site_no: str) -> None:
        """备案结论变更同步写回站点台账的「备案合规栏」。"""
        compliance = self.site_compliance(site_no)
        site = next(
            (row for row in store.rows("site") if str(row.get("基站编号")) == site_no), None
        )
        if site is not None:
            site["备案合规栏"] = compliance["合规栏"]
            site["备案结论"] = compliance["备案结论"]

    def _sync_all_sites(self) -> None:
        for site_no in self.compliance_map():
            self._sync_site(site_no)

    def _decorate_filing(self, filing: dict[str, Any]) -> dict[str, Any]:
        self._recompute_filing(filing)
        result = dict(filing)
        materials = self._materials(int(filing["id"]))
        result["材料"] = [dict(m) for m in materials]
        result["缺交材料"] = [m["材料名称"] for m in materials if m["status"] != "已提交"]
        result["监测点位数"] = sum(
            1 for p in store.rows(T_POINTS) if int(p.get("filing_id", 0)) == int(filing["id"])
        )
        result["越线点位数"] = sum(
            1
            for p in store.rows(T_POINTS)
            if int(p.get("filing_id", 0)) == int(filing["id"]) and p.get("现行限值结论") == "不合格"
        )
        return result

    def _require_filing(self, filing_id: int) -> dict[str, Any]:
        filing = store.find(T_FILINGS, filing_id)
        if filing is None:
            raise EmfilingError(f"备案 {filing_id} 不存在或已归档")
        return filing

    def _materials(self, filing_id: int) -> list[dict[str, Any]]:
        return [
            row
            for row in store.rows(T_MATERIALS)
            if int(row.get("filing_id", 0)) == filing_id
        ]

    def _missing_materials(self, filing_id: int) -> list[str]:
        return [m["材料名称"] for m in self._materials(filing_id) if m["status"] != "已提交"]

    def _check_env_admin(self, role: str) -> EmfilingError | None:
        if str(role or "").strip() != ENV_ADMIN_ROLE:
            return EmfilingError(
                f"越权操作已打回：当前角色「{role or '未指定'}」无权修改备案结论，"
                f"缺少授权项：{ENV_ADMIN_PERMISSION}",
                missing_permission=ENV_ADMIN_PERMISSION,
            )
        return None


emfiling_service = EmfilingService()
