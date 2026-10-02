"""基站电磁环境备案业务规则。

把原先各存各的环评备案和辐射监测收成一份档案，关键口径：

1. 监测点位按「监测点编号 + 所属站点」登记功率密度（W/m²）、监测日期、天线轮次；
   合格与否由服务端按监测当时生效的限值版本计算，前端传什么“合格”都不算数——越线一律记不合格。
2. 备案文书沿 待提交 → 已受理 → 已备案 → 已失效 流转；退回补正只补交缺失的材料，交过的保留。
3. 限值换版后，存量站点的“现行符合性”按新版重算；监测留档与备案结论仍锁定监测当时那一版。
4. 备案结论是整份档案的唯一事实源（conclusion 对象），站点台账合规栏和其他入口都从这里取同一份。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

# 演示环境统一“今天”，保证备案日期/失效日期可复现。
TODAY = date(2026, 10, 2)
NOW_TEXT = TODAY.strftime("%Y-%m-%d") + " 09:00"

LIMIT_MODULE = "emr_limit"
FILING_MODULE = "emr_filing"
MEASURE_MODULE = "emr_measure"

# 备案文书要求的材料清单；退回时按这个清单核对缺哪几份。
REQUIRED_MATERIALS = ["电磁环境监测报告", "天线参数登记表", "环评备案申请表", "站点位置示意图"]

STATUS_DRAFT = "待提交"
STATUS_ACCEPTED = "已受理"
STATUS_FILED = "已备案"
STATUS_EXPIRED = "已失效"
STATUS_RETURNED = "已退回"  # 业务上仍回到“待提交”队列，单独标记用于提示补交

STATUS_ORDER = [STATUS_DRAFT, STATUS_ACCEPTED, STATUS_FILED, STATUS_EXPIRED]

# 各站点最新一次备案结论的合规判定值（合规栏只认这两个/三种字面值）
VERDICT_PASS = "合格"
VERDICT_FAIL = "不合格"
VERDICT_PENDING = "待备案"

_initialized = False


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _bootstrap() -> None:
    """内存仓库首次使用时灌入限值版本与示范档案，保证克隆下来就能演示完整链路。"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    limits = store.rows(LIMIT_MODULE)
    if not limits:
        limits.extend([
            {
                "id": 1,
                "版本编号": "GB8702-2014",
                "标准名称": "电磁环境控制限值",
                "功率密度限值": 0.40,  # W/m²，30MHz～3GHz 公众曝露控制限值（示例口径）
                "生效日期": "2015-01-01",
                "状态": "现行",
                "是否当前版本": True,
            },
        ])

    filings = store.rows(FILING_MODULE)
    if not filings:
        # 站点1：已备案，两次监测，天线换过一轮，留档按当时限值。
        filings.append({
            "id": 1,
            "备案编号": "EMR-SITE-0001",
            "所属站点编号": "SITE-0001",
            "所属站点名称": "滨江路基站",
            "status": STATUS_FILED,
            "材料": {name: ("已提交" if name != "站点位置示意图" else "已提交") for name in REQUIRED_MATERIALS},
            "退回原因": "",
            "缺失材料": [],
            "备案日期": "2026-08-18",
            "失效日期": "2031-08-17",
            "conclusion": {
                "所属站点编号": "SITE-0001",
                "备案编号": "EMR-SITE-0001",
                "备案状态": STATUS_FILED,
                "备案结论": VERDICT_PASS,
                "判定依据版本": "GB8702-2014",
                "限值": 0.40,
                "现行符合性": VERDICT_PASS,
                "现行依据版本": "GB8702-2014",
                "留档结论": VERDICT_PASS,
                "留档依据版本": "GB8702-2014",
                "更新时间": "2026-08-18 10:20",
                "说明": "备案时全部监测点位低于限值；留档结论锁定监测当时版本。",
                "更新人": "归环保·林岚",
            },
        })
        # 站点2：受理在审，新增一轮天线后的监测待复核。
        filings.append({
            "id": 2,
            "备案编号": "EMR-SITE-0002",
            "所属站点编号": "SITE-0002",
            "所属站点名称": "云栖路基站",
            "status": STATUS_ACCEPTED,
            "材料": {name: "已提交" for name in REQUIRED_MATERIALS},
            "退回原因": "",
            "缺失材料": [],
            "备案日期": "",
            "失效日期": "",
            "conclusion": None,
        })
        # 站点3：被退回，只缺一份材料，交过的三份不能要求再交。
        filings.append({
            "id": 3,
            "备案编号": "EMR-SITE-0003",
            "所属站点编号": "SITE-0003",
            "所属站点名称": "望江台基站",
            "status": STATUS_DRAFT,
            "材料": {
                "电磁环境监测报告": "已提交",
                "天线参数登记表": "已提交",
                "环评备案申请表": "已提交",
                "站点位置示意图": "待补交",
            },
            "退回原因": "站点位置示意图缺指北针与监测点位标注，退回补正",
            "缺失材料": ["站点位置示意图"],
            "备案日期": "",
            "失效日期": "",
            "conclusion": None,
        })

    measures = store.rows(MEASURE_MODULE)
    if not measures:
        measures.extend([
            # 站点1：第一轮天线（2026-03），第二轮换天线后复测（2026-08），均合格。
            {"id": 1, "所属站点编号": "SITE-0001", "监测点编号": "MP-01", "监测点位置": "天线主瓣方向 20m",
             "天线轮次": "第1轮天线", "功率密度": 0.21, "监测日期": "2026-03-10",
             "依据版本": "GB8702-2014", "限值": 0.40, "监测结论": "合格", "登记时间": "2026-03-11 09:00"},
            {"id": 2, "所属站点编号": "SITE-0001", "监测点编号": "MP-02", "监测点位置": "基站楼下人行道",
             "天线轮次": "第2轮天线", "功率密度": 0.31, "监测日期": "2026-08-12",
             "依据版本": "GB8702-2014", "限值": 0.40, "监测结论": "合格", "登记时间": "2026-08-13 09:00"},
            # 站点2：换了高增益天线后一个点位越线——绝不能记成合格。
            {"id": 3, "所属站点编号": "SITE-0002", "监测点编号": "MP-01", "监测点位置": "天线主瓣方向 15m",
             "天线轮次": "第1轮天线", "功率密度": 0.30, "监测日期": "2026-04-02",
             "依据版本": "GB8702-2014", "限值": 0.40, "监测结论": "合格", "登记时间": "2026-04-03 09:00"},
            {"id": 4, "所属站点编号": "SITE-0002", "监测点编号": "MP-02", "监测点位置": "对面居民楼阳台",
             "天线轮次": "第2轮天线", "功率密度": 0.47, "监测日期": "2026-09-15",
             "依据版本": "GB8702-2014", "限值": 0.40, "监测结论": "不合格", "登记时间": "2026-09-16 09:00"},
            # 站点3：监测本身合格，卡在材料补交。
            {"id": 5, "所属站点编号": "SITE-0003", "监测点编号": "MP-01", "监测点位置": "站址围墙外 10m",
             "天线轮次": "第1轮天线", "功率密度": 0.18, "监测日期": "2026-07-20",
             "依据版本": "GB8702-2014", "限值": 0.40, "监测结论": "合格", "登记时间": "2026-07-21 09:00"},
        ])


class EmrService:
    # ---------- 限值版本 ----------
    def list_limits(self) -> list[dict[str, Any]]:
        _bootstrap()
        return list(store.rows(LIMIT_MODULE))

    def current_limit(self) -> dict[str, Any]:
        _bootstrap()
        rows = store.rows(LIMIT_MODULE)
        current = next((row for row in rows if row.get("是否当前版本")), None)
        if current is None:  # 兜底：取生效日期最新的一版
            current = sorted(rows, key=lambda r: str(r.get("生效日期", "")), reverse=True)[0]
        return current

    def limit_at(self, date_text: str) -> dict[str, Any]:
        """取某个监测日期当天生效的限值版本：生效日期 <= 监测日期中最新的一版。"""
        _bootstrap()
        rows = [r for r in store.rows(LIMIT_MODULE) if str(r.get("生效日期", "")) <= date_text]
        if not rows:  # 监测早于任何一版，则沿用最早一版
            rows = store.rows(LIMIT_MODULE)
        return sorted(rows, key=lambda r: str(r.get("生效日期", "")), reverse=True)[0]

    def publish_limit(self, values: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, list[str]]:
        """换版：登记新版本、置为现行，并对全部存量站点按新版重算现行符合性。"""
        _bootstrap()
        required = ["版本编号", "标准名称", "功率密度限值", "生效日期"]
        missing = [f for f in required if str(values.get(f) or "").strip() == ""]
        if missing:
            return None, missing
        try:
            limit_value = float(values["功率密度限值"])
        except (TypeError, ValueError):
            return None, ["功率密度限值（需为数字，单位 W/m²）"]
        if limit_value <= 0:
            return None, ["功率密度限值（需为正数）"]

        rows = store.rows(LIMIT_MODULE)
        for row in rows:
            row["是否当前版本"] = False
            row["状态"] = "历史版本"
        new_row = {
            "id": _next_id(rows),
            "版本编号": str(values["版本编号"]).strip(),
            "标准名称": str(values["标准名称"]).strip(),
            "功率密度限值": limit_value,
            "生效日期": str(values["生效日期"]).strip(),
            "状态": "现行",
            "是否当前版本": True,
        }
        rows.append(new_row)

        # 存量站点按新版重算“现行符合性”；留档结论一行不动。
        for filing in store.rows(FILING_MODULE):
            self._recompute_current(filing, operator=operator,
                                    reason=f"限值换版为 {new_row['版本编号']}，存量站点按新版重算")
        return new_row, []

    # ---------- 监测点位 ----------
    def list_measures(self, site_code: str | None = None) -> list[dict[str, Any]]:
        _bootstrap()
        rows = store.rows(MEASURE_MODULE)
        if site_code:
            rows = [r for r in rows if r.get("所属站点编号") == site_code]
        return sorted(rows, key=lambda r: (str(r.get("所属站点编号", "")), str(r.get("监测日期", ""))))

    def register_measure(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        """登记一个监测点位。合格/不合格由服务端按监测当时限值裁定，忽略调用方自带的结论。"""
        _bootstrap()
        required = ["所属站点编号", "监测点编号", "监测点位置", "功率密度", "监测日期", "天线轮次"]
        missing = [f for f in required if str(values.get(f) or "").strip() == ""]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        try:
            density = float(values["功率密度"])
        except (TypeError, ValueError):
            return None, "功率密度必须是数字（单位 W/m²）"
        if density < 0:
            return None, "功率密度不能为负数"

        date_text = str(values["监测日期"]).strip()
        limit_row = self.limit_at(date_text)
        # 硬性规则：越线一律不合格，调用方传“合格”也覆盖不掉。
        verdict = VERDICT_PASS if density <= float(limit_row["功率密度限值"]) else VERDICT_FAIL

        rows = store.rows(MEASURE_MODULE)
        for row in rows:  # 同一点位重复登记视为复测，更新而不是造第二条
            if row.get("所属站点编号") == str(values["所属站点编号"]).strip() and \
               row.get("监测点编号") == str(values["监测点编号"]).strip():
                row.update({
                    "监测点位置": str(values["监测点位置"]).strip(),
                    "天线轮次": str(values["天线轮次"]).strip(),
                    "功率密度": density,
                    "监测日期": date_text,
                    "依据版本": limit_row["版本编号"],
                    "限值": limit_row["功率密度限值"],
                    "监测结论": verdict,
                })
                self._touch_filing(str(values["所属站点编号"]).strip())
                return row, None

        entry = {
            "id": _next_id(rows),
            "所属站点编号": str(values["所属站点编号"]).strip(),
            "监测点编号": str(values["监测点编号"]).strip(),
            "监测点位置": str(values["监测点位置"]).strip(),
            "天线轮次": str(values["天线轮次"]).strip(),
            "功率密度": density,
            "监测日期": date_text,
            "依据版本": limit_row["版本编号"],
            "限值": limit_row["功率密度限值"],
            "监测结论": verdict,  # 服务端裁定，越线不可能是“合格”
            "登记时间": date_text + " 00:00",
        }
        rows.append(entry)
        self._touch_filing(entry["所属站点编号"])
        return entry, None

    def _latest_measure_verdict(self, site_code: str) -> tuple[str, dict[str, Any] | None, list[dict[str, Any]]]:
        """现行符合性：每个监测点位取最新一次监测，按当前限值版本重算；任一点位越线即不合格。"""
        current = self.current_limit()
        limit_value = float(current["功率密度限值"])
        latest_by_point: dict[str, dict[str, Any]] = {}
        for row in self.list_measures(site_code):
            point = str(row.get("监测点编号", ""))
            old = latest_by_point.get(point)
            if old is None or str(row.get("监测日期", "")) >= str(old.get("监测日期", "")):
                latest_by_point[point] = row
        if not latest_by_point:
            return VERDICT_PENDING, current, []
        evaluated = []
        overall = VERDICT_PASS
        for row in latest_by_point.values():
            point_verdict = VERDICT_PASS if float(row["功率密度"]) <= limit_value else VERDICT_FAIL
            if point_verdict == VERDICT_FAIL:
                overall = VERDICT_FAIL
            evaluated.append({**row, "现行判定": point_verdict})
        return overall, current, sorted(evaluated, key=lambda r: str(r.get("监测点编号", "")))

    # ---------- 备案文书 ----------
    def list_filings(self, status: str | None = None, keyword: str | None = None) -> list[dict[str, Any]]:
        _bootstrap()
        rows = store.rows(FILING_MODULE)
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if keyword:
            rows = [r for r in rows if keyword in str(r.get("所属站点编号", ""))
                    or keyword in str(r.get("所属站点名称", ""))
                    or keyword in str(r.get("备案编号", ""))]
        return [self._decorate_filing(r) for r in rows]

    def get_filing(self, filing_id: int) -> dict[str, Any] | None:
        _bootstrap()
        row = store.find(FILING_MODULE, filing_id)
        return self._decorate_filing(row) if row else None

    def find_filing_by_site(self, site_code: str) -> dict[str, Any] | None:
        _bootstrap()
        for row in store.rows(FILING_MODULE):
            if row.get("所属站点编号") == site_code:
                return self._decorate_filing(row)
        return None

    def _decorate_filing(self, filing: dict[str, Any]) -> dict[str, Any]:
        """列表/明细统一附带：材料提交情况、监测点位、当前唯一结论。"""
        current_verdict, current_limit_row, evaluated = self._latest_measure_verdict(
            str(filing.get("所属站点编号", "")))
        view = dict(filing)
        view["缺失材料"] = [name for name, state in filing.get("材料", {}).items() if state != "已提交"]
        view["监测点位"] = [
            {
                "监测点编号": m.get("监测点编号"),
                "监测点位置": m.get("监测点位置"),
                "天线轮次": m.get("天线轮次"),
                "功率密度": m.get("功率密度"),
                "监测日期": m.get("监测日期"),
                "依据版本": m.get("依据版本"),
                "监测结论": m.get("监测结论"),  # 留档：监测当时那一版下的判定
                "现行判定": m.get("现行判定", m.get("监测结论")),
            }
            for m in evaluated
        ]
        view["现行符合性"] = current_verdict
        view["现行依据版本"] = current_limit_row["版本编号"]
        # 备案详情页与站点台账/外部入口取的是同一个函数的同一份结果，不存在两份口径。
        view["conclusion"] = self._conclusion_for(filing, current_verdict, current_limit_row)
        return view

    def submit_filing(self, filing_id: int) -> tuple[dict[str, Any] | None, str]:
        """待提交/被退回 → 已受理。被退回补交时只补缺的那几份，已交的不用再交。"""
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] not in (STATUS_DRAFT, STATUS_RETURNED):
            return None, f"当前状态为「{filing['status']}」，只有待提交/已退回的档案可以提交受理"
        missing = [name for name, state in filing.get("材料", {}).items() if state != "已提交"]
        if missing:
            return None, f"材料不齐，还差：{'、'.join(missing)}；已交过的材料无需重复提交"
        filing["status"] = STATUS_ACCEPTED
        filing["缺失材料"] = []
        filing["退回原因"] = ""
        return self.get_filing(filing_id), "材料已齐，备案文书受理成功"

    def supplement(self, filing_id: int, materials: list[str]) -> tuple[dict[str, Any] | None, str]:
        """退回补正：只接收缺失清单里的材料；交过的材料保持已提交，不允许重复补交。"""
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] != STATUS_DRAFT:
            return None, f"当前状态为「{filing['status']}」，没有待补交的材料"
        wanted = [m for m in materials if str(m or "").strip()]
        accepted, already, unknown = [], [], []
        for name in wanted:
            if name not in REQUIRED_MATERIALS:
                unknown.append(name)
            elif filing["材料"].get(name) == "已提交":
                already.append(name)
            else:
                filing["材料"][name] = "已提交"
                accepted.append(name)
        still_missing = [n for n, s in filing["材料"].items() if s != "已提交"]
        filing["缺失材料"] = still_missing
        parts = []
        if accepted:
            parts.append(f"已补交：{'、'.join(accepted)}")
        if already:
            parts.append(f"以下材料此前已交，无需再交：{'、'.join(already)}")
        if unknown:
            parts.append(f"不属于备案材料清单：{'、'.join(unknown)}")
        if not still_missing:
            parts.append("材料已补齐，可提交受理")
        else:
            parts.append(f"仍缺：{'、'.join(still_missing)}")
        return self.get_filing(filing_id), "；".join(parts)

    def accept_filing(self, filing_id: int, operator: str) -> tuple[dict[str, Any] | None, str]:
        """已受理 → 已备案，并由服务端出具唯一备案结论；越线的一律不许记成合格。"""
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] != STATUS_ACCEPTED:
            return None, f"当前状态为「{filing['status']}」，只有已受理的档案可以备案"

        verdict, current, _ = self._latest_measure_verdict(str(filing.get("所属站点编号", "")))
        if verdict == VERDICT_PENDING:
            return None, "该站点还没有任何辐射监测点位记录，无法出具备案结论"
        if verdict == VERDICT_FAIL:
            # 硬规则：存在越线监测点，禁止出具备案合格结论，打回整改而不是备案。
            fail_conclusion = self._build_conclusion(filing, VERDICT_FAIL, current, operator,
                                                     note="存在越线监测点位，备案审查不合格")
            filing["status"] = STATUS_DRAFT
            filing["退回原因"] = "存在功率密度越线的监测点位，不予备案合格，整改后重新复测提交"
            filing["缺失材料"] = ["电磁环境监测报告（整改复测后重新出具）"]
            filing["材料"]["电磁环境监测报告"] = "待补交"
            fail_conclusion["备案状态"] = STATUS_DRAFT
            filing["conclusion"] = fail_conclusion
            return self.get_filing(filing_id), "存在辐射监测越线点位，备案结论为不合格，已打回整改"

        filing["status"] = STATUS_FILED
        filing["备案日期"] = TODAY.isoformat()
        filing["失效日期"] = (TODAY + timedelta(days=5 * 365)).isoformat()
        filing["conclusion"] = self._build_conclusion(filing, VERDICT_PASS, current, operator,
                                                       note="全部监测点位低于现行限值，准予备案")
        return self.get_filing(filing_id), "备案结论（合格）已出具并同步站点台账合规栏"

    def return_filing(self, filing_id: int, reason: str, missing_materials: list[str],
                      operator: str) -> tuple[dict[str, Any] | None, str]:
        """已受理 → 退回待提交：只点出缺的那几份材料，其余材料保留。"""
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] != STATUS_ACCEPTED:
            return None, f"当前状态为「{filing['status']}」，只有已受理的档案可以退回"
        missing = [m for m in missing_materials if m in REQUIRED_MATERIALS]
        for name in missing:
            filing["材料"][name] = "待补交"
        filing["status"] = STATUS_DRAFT
        filing["退回原因"] = reason or "材料需补正"
        filing["缺失材料"] = [n for n, s in filing["材料"].items() if s != "已提交"]
        filing["conclusion"] = None
        return self.get_filing(filing_id), f"已退回，补交 {('、'.join(missing) or '补正材料')} 后重新提交"

    def expire_filing(self, filing_id: int, operator: str) -> tuple[dict[str, Any] | None, str]:
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] != STATUS_FILED:
            return None, f"当前状态为「{filing['status']}」，只有已备案的档案可以置为失效"
        filing["status"] = STATUS_EXPIRED
        conclusion = filing.get("conclusion")
        if conclusion:
            conclusion["备案状态"] = STATUS_EXPIRED
            conclusion["更新时间"] = NOW_TEXT
            conclusion["更新人"] = operator
            conclusion["说明"] = "备案已过有效期，结论归档为已失效"
        return self.get_filing(filing_id), "备案已置为失效，站点台账合规栏同步更新"

    def amend_conclusion(self, filing_id: int, verdict: str, note: str,
                         operator: str) -> tuple[dict[str, Any] | None, str]:
        """修改备案结论：仅环保归口管理员可调用（权限在路由层强制）。

        留档结论不允许被这个动作改写；这里只允许在已备案档案上更正现行结论，
        且服务端会用当前监测数据复核——试图把越线站点改成合格一律拒绝。
        """
        _bootstrap()
        filing = store.find(FILING_MODULE, filing_id)
        if filing is None:
            return None, f"备案档案 {filing_id} 不存在"
        if filing["status"] != STATUS_FILED:
            return None, f"当前状态为「{filing['status']}」，只有已备案档案可以更正结论"
        if verdict not in (VERDICT_PASS, VERDICT_FAIL):
            return None, "结论只允许是「合格」或「不合格」"
        measured_verdict, current, _ = self._latest_measure_verdict(str(filing.get("所属站点编号", "")))
        if verdict == VERDICT_PASS and measured_verdict == VERDICT_FAIL:
            return None, "服务端复核未通过：存在越线监测点位，备案结论不得记为合格"
        filing["conclusion"] = self._build_conclusion(filing, verdict, current, operator,
                                                       note=note or "环保归口管理员更正结论")
        return self.get_filing(filing_id), f"备案结论已更正为「{verdict}」，站点台账已同步同一份结论"

    # ---------- 结论：唯一事实源 ----------
    def _build_conclusion(self, filing: dict[str, Any], verdict: str,
                          current_limit_row: dict[str, Any], operator: str,
                          note: str) -> dict[str, Any]:
        """构造/替换档案里唯一的 conclusion 对象；所有入口读到的都是它。"""
        prior = filing.get("conclusion")
        archived_verdict = prior.get("留档结论") if prior else (
            verdict if filing["status"] == STATUS_FILED else VERDICT_PENDING)
        archived_version = prior.get("留档依据版本") if prior else current_limit_row["版本编号"]
        conclusion = {
            "所属站点编号": filing.get("所属站点编号"),
            "备案编号": filing.get("备案编号"),
            "备案状态": filing["status"],
            "备案结论": verdict,
            "判定依据版本": current_limit_row["版本编号"],
            "限值": current_limit_row["功率密度限值"],
            "现行符合性": verdict,
            "现行依据版本": current_limit_row["版本编号"],
            # 留档锁定：监测/备案当时那一版，不随后续换版变更。
            "留档结论": archived_verdict,
            "留档依据版本": archived_version,
            "更新时间": NOW_TEXT,
            "更新人": operator,
            "说明": note,
        }
        filing["conclusion"] = conclusion
        return conclusion

    def _recompute_current(self, filing: dict[str, Any], *, operator: str, reason: str) -> None:
        """限值换版后重算现行符合性。只动“现行”字段，留档结论与依据版本保持不变。"""
        verdict, current, _ = self._latest_measure_verdict(str(filing.get("所属站点编号", "")))
        conclusion = filing.get("conclusion")
        if conclusion is None:
            return  # 还没出结论的档案，列表接口会实时算现行符合性，无需落地
        conclusion["现行符合性"] = verdict
        conclusion["现行依据版本"] = current["版本编号"]
        conclusion["限值"] = current["功率密度限值"]
        conclusion["更新时间"] = NOW_TEXT
        conclusion["更新人"] = operator
        conclusion["说明"] = reason
        # 备案结论（留档）与留档依据版本刻意不改。

    def _touch_filing(self, site_code: str) -> None:
        """新增/复测监测点位后刷新档案的现行符合性视图（不改变已留档结论）。"""
        filing = next((r for r in store.rows(FILING_MODULE)
                       if r.get("所属站点编号") == site_code), None)
        if filing is None:
            return
        verdict, current, _ = self._latest_measure_verdict(site_code)
        conclusion = filing.get("conclusion")
        if conclusion:
            conclusion["现行符合性"] = verdict
            conclusion["现行依据版本"] = current["版本编号"]
            conclusion["限值"] = current["功率密度限值"]

    def _conclusion_for(self, filing: dict[str, Any], current_verdict: str,
                        current_limit_row: dict[str, Any]) -> dict[str, Any]:
        """构造该档案对外的唯一结论；尚未出结论时给出统一的“待备案”占位结构。

        站点台账合规栏、备案详情页、按站点编号的外部入口，最终拿到的都是这一份结果。
        入参直接用 store 里的原始档案行，不经过装饰，避免与装饰函数互相递归。
        """
        stored = filing.get("conclusion")
        if stored is not None:
            return dict(stored)
        return {
            "所属站点编号": filing.get("所属站点编号"),
            "备案编号": filing.get("备案编号"),
            "备案状态": filing.get("status"),
            "备案结论": VERDICT_PENDING if filing.get("status") != STATUS_EXPIRED else "已失效",
            "判定依据版本": current_limit_row["版本编号"],
            "限值": current_limit_row["功率密度限值"],
            "现行符合性": current_verdict,
            "现行依据版本": current_limit_row["版本编号"],
            "留档结论": VERDICT_PENDING,
            "留档依据版本": current_limit_row["版本编号"],
            "更新时间": "",
            "更新人": "",
            "说明": "尚未出具备案结论" if filing.get("status") != STATUS_EXPIRED else "备案已失效",
        }

    def site_compliance(self, site_code: str) -> dict[str, Any]:
        """供站点台账与其他入口调用：按站点编号取同一份备案结论（合规栏数据源）。

        直接读 store 原始档案行再走 _conclusion_for，与备案详情页结论严格同源。
        """
        _bootstrap()
        filing = next((r for r in store.rows(FILING_MODULE)
                       if r.get("所属站点编号") == site_code), None)
        current_verdict, current, _ = self._latest_measure_verdict(site_code)
        if filing is None:
            return {
                "所属站点编号": site_code,
                "备案编号": "",
                "备案状态": "未建档",
                "备案结论": VERDICT_PENDING,
                "合规栏": VERDICT_PENDING,
                "现行符合性": VERDICT_PENDING,
                "现行依据版本": current["版本编号"],
                "留档结论": VERDICT_PENDING,
                "留档依据版本": current["版本编号"],
                "说明": "该站点尚无电磁环境备案档案",
            }
        conclusion = self._conclusion_for(filing, current_verdict, current)
        # 合规栏：已备案看备案结论，其余状态给现行符合性或待备案。
        if filing["status"] == STATUS_FILED:
            compliance = conclusion["备案结论"]
        elif filing["status"] == STATUS_EXPIRED:
            compliance = "已失效"
        else:
            compliance = conclusion["现行符合性"] if conclusion["现行符合性"] != VERDICT_PENDING else VERDICT_PENDING
        return {**conclusion, "合规栏": compliance}


emr_service = EmrService()
