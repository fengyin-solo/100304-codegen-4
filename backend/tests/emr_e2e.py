"""电磁环境备案端到端用例：对运行中的后端（127.0.0.1:8000）打真实 HTTP 请求。

覆盖：授权打回、退回只补缺失材料、越线不得记合格、限值换版重算与留档锁定、
备案结论单一事实源（详情/站点入口/站点台账三处一致）、失效流转、重复读取一致。
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PASSED = 0


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, cond, extra=""):
    global PASSED
    assert cond, f"{name} {extra}"
    PASSED += 1
    print(f"PASS {name}")


_, r = call("POST", "/api/auth/login", body={"login_name": "envadmin"})
admin = r["token"]
_, r = call("POST", "/api/auth/login", body={"login_name": "ops"})
ops = r["token"]
_, r = call("POST", "/api/auth/login", body={"login_name": "viewer"})
viewer = r["token"]

# A. 授权：越权打回并写明缺的授权项
s, r = call("POST", "/api/emr/filings/2/accept", ops)
check("A1 运维越权出具结论 403", s == 403 and "emr:conclusion:edit" in r["detail"])
s, r = call("POST", "/api/emr/filings/2/accept", viewer)
check("A2 访客越权 403", s == 403)
s, r = call("POST", "/api/emr/filings/2/accept")
check("A3 未登录 401", s == 401)

# B. 退回补交：只补缺的那几份
s, f3 = call("GET", "/api/emr/filings/3")
check("B1 档案3待提交且只缺示意图",
      f3["status"] == "待提交" and f3["缺失材料"] == ["站点位置示意图"])
s, r = call("POST", "/api/emr/filings/3/submit", admin)
check("B2 缺材料不予受理", not r["ok"] and "站点位置示意图" in r["message"])
s, r = call("POST", "/api/emr/filings/3/supplement", admin,
            {"values": {"materials": ["站点位置示意图", "电磁环境监测报告"]}})
check("B3 只收缺的、已交的不用再交",
      "已补交：站点位置示意图" in r["message"] and "无需再交" in r["message"])
s, f3b = call("GET", "/api/emr/filings/3")
check("B4 交过的材料保持已提交",
      all(state == "已提交" for state in f3b["材料"].values()) and not f3b["缺失材料"])
s, r = call("POST", "/api/emr/filings/3/submit", admin)
check("B5 补齐后受理", r["entry"]["status"] == "已受理")

# C. 合格站点备案：结论同步站点台账合规栏
s, r = call("POST", "/api/emr/filings/3/accept", admin)
check("C1 合格站点准予备案",
      r["ok"] and r["entry"]["conclusion"]["备案结论"] == "合格", r.get("message"))
s, ext = call("GET", "/api/emr/sites/SITE-0003/conclusion")
check("C2 站点入口取到同一份合格", ext["备案结论"] == "合格" and ext["合规栏"] == "合格")
s, sites = call("GET", "/api/site?keyword=SITE-0003")
row = next(x for x in sites["items"] if x["基站编号"] == "SITE-0003")
check("C3 站点台账合规栏同步", row["电磁合规栏"] == "合格" and row["备案状态"] == "已备案")

# D. 越线站点：不许记合格，管理员强改也被复核拒绝
s, r = call("POST", "/api/emr/filings/2/accept", admin)
check("D1 越线站点不予备案合格",
      "不合格" in r["message"] and r["entry"]["status"] == "待提交")
check("D2 打回时结论即为不合格", r["entry"]["conclusion"]["备案结论"] == "不合格")
s, r = call("POST", "/api/emr/filings/2/conclusion", admin,
            {"values": {"verdict": "合格", "note": "强改"}})
check("D3 未备案档案不允许更正结论（打回态改不动）",
      not r["ok"] and "只有已备案档案可以更正结论" in r["message"], r.get("message"))

# E. 监测点位登记：服务端裁定，越线必不合格，同点位复测更新
s, r = call("POST", "/api/emr/measures", ops,
            {"values": {"所属站点编号": "SITE-0003", "监测点编号": "MP-09", "监测点位置": "x",
                        "天线轮次": "第2轮天线", "功率密度": 0.5, "监测日期": "2026-09-20",
                        "监测结论": "合格"}})
check("E1 运维登记监测 403 且写明授权", s == 403 and "emr:review" in r["detail"])
s, r = call("POST", "/api/emr/measures", admin,
            {"values": {"所属站点编号": "SITE-0003", "监测点编号": "MP-09",
                        "监测点位置": "天台边缘", "天线轮次": "第2轮天线",
                        "功率密度": 0.5, "监测日期": "2026-09-20", "监测结论": "合格"}})
check("E2 越线一律记不合格（伪造合格无效）", r["entry"]["监测结论"] == "不合格")
s, r = call("POST", "/api/emr/measures", admin,
            {"values": {"所属站点编号": "SITE-0003", "监测点编号": "MP-09",
                        "监测点位置": "天台边缘", "天线轮次": "第2轮天线",
                        "功率密度": 0.22, "监测日期": "2026-09-28"}})
check("E3 复测合格覆盖同点位", r["entry"]["监测结论"] == "合格")
s, ms = call("GET", "/api/emr/measures?site=SITE-0003")
check("E4 同点位只有一条记录",
      len([m for m in ms["items"] if m["监测点编号"] == "MP-09"]) == 1)
s, r = call("POST", "/api/emr/measures", admin, {"values": {"所属站点编号": "X"}})
check("E5 缺字段给可读原因", not r["ok"] and "缺少必填字段" in r["message"])

# F. 限值换版：存量重算、留档锁定
s, r = call("POST", "/api/emr/limits/publish", ops, {"values": {"版本编号": "x"}})
check("F1 运维无权换版", s == 403 and "emr:limit:publish" in r["detail"])
s, r = call("POST", "/api/emr/limits/publish", admin,
            {"values": {"版本编号": "GB8702-2026", "标准名称": "新修限值",
                        "功率密度限值": 0.08, "生效日期": "2026-10-01"}})
check("F2 管理员发布新版", r["ok"])
s, f1 = call("GET", "/api/emr/filings/1")
c = f1["conclusion"]
check("F3 存量现行按新版重算为不合格",
      c["现行符合性"] == "不合格" and c["现行依据版本"] == "GB8702-2026")
check("F4 留档结论与依据锁定旧版",
      c["留档结论"] == "合格" and c["留档依据版本"] == "GB8702-2014")
check("F5 备案结论留档不随换版变", c["备案结论"] == "合格")
mp = next(m for m in f1["监测点位"] if m["监测点编号"] == "MP-02")
check("F6 监测留档记监测当时版本", mp["监测结论"] == "合格" and mp["依据版本"] == "GB8702-2014")
check("F7 同一点位现行判定按新版", mp["现行判定"] == "不合格")
s, ms = call("GET", "/api/emr/measures?site=SITE-0001")
check("F8 历史监测依据版本全部留旧版",
      all(m["依据版本"] == "GB8702-2014" for m in ms["items"]))
s, ext1 = call("GET", "/api/emr/sites/SITE-0001/conclusion")
check("F9 详情/站点入口两处同源",
      ext1["现行符合性"] == f1["conclusion"]["现行符合性"]
      and ext1["留档结论"] == f1["conclusion"]["留档结论"])
# 已备案档案换版后现行越线：即使是管理员，强改“合格”也被服务端复核拒绝
s, r = call("POST", "/api/emr/filings/1/conclusion", admin,
            {"values": {"verdict": "合格", "note": "强改合格"}})
check("F10 管理员强改越线已备案站为合格被拒",
      not r["ok"] and "不得记为合格" in r["message"], r.get("message"))
s, r = call("POST", "/api/emr/filings/1/conclusion", ops,
            {"values": {"verdict": "不合格", "note": "越权"}})
check("F11 运维更正结论 403 写明授权",
      s == 403 and "emr:conclusion:edit" in r["detail"])

# G. 失效流转
s, r = call("POST", "/api/emr/filings/3/expire", admin)
check("G1 已备案→已失效", r["entry"]["status"] == "已失效")
s, ext3 = call("GET", "/api/emr/sites/SITE-0003/conclusion")
check("G2 合规栏同步已失效", ext3["合规栏"] == "已失效")
s, r = call("POST", "/api/emr/filings/3/expire", admin)
check("G3 已失效不可重复失效", not r["ok"])

# H. 未建档站点 & 只读权限
s, r = call("GET", "/api/emr/sites/NOPE/conclusion")
check("H1 未建档站点给待备案", r["合规栏"] == "待备案")
s, r = call("GET", "/api/emr/filings", viewer)
check("H2 访客可读列表", s == 200)

# I. 退出再进来/重复读取：同一条结果
a = call("GET", "/api/emr/sites/SITE-0001/conclusion")[1]
b = call("GET", "/api/emr/sites/SITE-0001/conclusion")[1]
check("I1 重复读取得到同一条结果", a == b)

print(f"\n=== 全部 {PASSED} 项端到端用例通过 ===")
