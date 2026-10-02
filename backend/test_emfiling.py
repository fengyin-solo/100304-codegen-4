"""电磁环境备案需求逐条验证：用 FastAPI TestClient 走完整 HTTP 链路。"""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {detail}")


def post(path: str, values: dict | None = None):
    return client.post(path, json={"values": values or {}})


print("== 1. 监测点位登记：越线一律不许记合格 ==")
r = post("/api/emfiling/points", {"filing_id": 3, "监测点位编号": "P-0003-B",
                                  "功率密度": 0.5, "监测日期": "2026-09-19"})
body = r.json()
check("越线点位登记成功但结论=不合格", body["ok"] and body["entry"]["留档结论"] == "不合格", str(body))
f3 = client.get("/api/emfiling/filings/3").json()
check("越线点位在已受理备案上现行判定为不合格", f3["全部点位现行合格"] is False and f3["越线点位数"] >= 1, str(f3)[:200])

r = post("/api/emfiling/points", {"filing_id": 3, "监测点位编号": "P-0003-C",
                                  "功率密度": "abc", "监测日期": "2026-09-19"})
check("功率密度非数字被拒", r.json()["ok"] is False)

r = post("/api/emfiling/points", {"filing_id": 3, "监测点位编号": "P-0003-D",
                                  "功率密度": 0.01, "监测日期": "2026/09/19"})
check("监测日期格式错误被拒", r.json()["ok"] is False)

print("== 2. 备案文书流转：待提交→已受理→已备案；缺材料不受理 ==")
r = post("/api/emfiling/filings/2/submit")
check("材料不齐不受理并列出缺项",
      r.json()["ok"] is False and "基站基本信息表" in r.json()["message"], r.json()["message"])

r = post("/api/emfiling/filings/2/materials", {"材料名称": "电磁环境监测报告"})
check("已交材料不允许重复提交", r.json()["ok"] is False and "无需重复提交" in r.json()["message"], r.json()["message"])

r = post("/api/emfiling/filings/2/materials", {"材料名称": "基站基本信息表"})
check("补交缺交材料成功", r.json()["ok"] is True and "仍缺" in r.json()["message"], r.json()["message"])

r = post("/api/emfiling/filings/2/materials", {"材料名称": "电磁环境影响说明"})
check("补交不合规材料成功且提示可提交受理", r.json()["ok"] is True and "可重新提交受理" in r.json()["message"], r.json()["message"])

r = post("/api/emfiling/filings/2/submit")
check("补齐后受理成功→已受理", r.json()["ok"] is True and r.json()["entry"]["status"] == "已受理", r.json()["message"])

print("== 3. 退回后只补缺的那几份 ==")
r = post("/api/emfiling/filings/2/return", {"退回原因": "天线换版后补图"})
check("已受理可退回待提交", r.json()["ok"] is True and r.json()["entry"]["status"] == "待提交", r.json()["message"])
mats = {m["材料名称"]: m["status"] for m in client.get("/api/emfiling/filings/2/materials").json()["items"]}
check("退回后已交材料仍为已提交留档", all(v == "已提交" for v in mats.values()), str(mats))

print("== 4. 改备案结论的权限：越权打回并写明缺哪项授权 ==")
r = post("/api/emfiling/filings/3/decision", {"备案结论": "备案合格", "role": "运维人员"})
b = r.json()
check("非环保管理员被打回", b["ok"] is False and "越权" in b["message"], b["message"])
check("打回响应写明缺失授权项", b.get("missing_permission") and "环保归口管理员" in b["missing_permission"], str(b))
f3b = client.get("/api/emfiling/filings/3").json()
check("越权请求未改变备案状态", f3b["status"] == "已受理" and f3b["备案结论"] is None)

print("== 5. 越线即使用环保管理员也不能记合格（硬规则） ==")
r = post("/api/emfiling/filings/3/decision", {"备案结论": "备案合格", "role": "环保归口管理员"})
b = r.json()
check("越线备案被强制记为不合格", b["ok"] is True and b["entry"]["备案结论"] == "备案不合格", b["message"])
check("消息说明越线不允许记合格", "不允许记成合格" in b["message"], b["message"])

print("== 6. 合格路径：新建合格点位的备案可正常签发 ==")
r = post("/api/emfiling/filings", {"备案编号": "EMF-2026-0009", "站点编号": "SITE-0009",
                                   "站点名称": "新建演示站"})
check("新建备案为待提交并生成材料清单", r.json()["ok"] and len(r.json()["entry"]["材料"]) == 4, str(r.json())[:200])
fid = r.json()["entry"]["id"]
for name in ["电磁环境监测报告", "天线及辐射设备布设图", "基站基本信息表", "电磁环境影响说明"]:
    post(f"/api/emfiling/filings/{fid}/materials", {"材料名称": name})
post("/api/emfiling/points", {"filing_id": fid, "监测点位编号": "P-0009-A",
                              "功率密度": 0.01, "监测日期": "2026-09-30"})
post(f"/api/emfiling/filings/{fid}/submit")
r = post(f"/api/emfiling/filings/{fid}/decision", {"备案结论": "备案合格", "role": "环保归口管理员"})
check("全部合格时环保管理员可签发合格", r.json()["entry"]["备案结论"] == "备案合格", r.json()["message"])

print("== 7. 限值换版：存量按新版重算、留档仍按当时版 ==")
# 先建一个按老版限值 0.08 合格出结论的备案，验证发布新版（0.02）后才打回不合格，
# 而在发布之前无论读取多少次，历史结论都不改写。
r = post("/api/emfiling/filings", {"备案编号": "EMF-2026-0008", "站点编号": "SITE-0008",
                                   "站点名称": "换版存量站"})
fid8 = r.json()["entry"]["id"]
for name in ["电磁环境监测报告", "天线及辐射设备布设图", "基站基本信息表", "电磁环境影响说明"]:
    post(f"/api/emfiling/filings/{fid8}/materials", {"材料名称": name})
post("/api/emfiling/points", {"filing_id": fid8, "监测点位编号": "P-0008-A",
                              "功率密度": 0.05, "监测日期": "2026-09-20"})
post(f"/api/emfiling/filings/{fid8}/submit")
post(f"/api/emfiling/filings/{fid8}/decision", {"备案结论": "备案合格", "role": "环保归口管理员"})
before = client.get(f"/api/emfiling/filings/{fid8}").json()
check("换版前：0.05 对现行 0.08 合格，结论为合格",
      before["备案结论"] == "备案合格" and before["全部点位现行合格"] is True, str(before)[:200])
client.get("/api/site")  # 台账读一遍，不应触发结论改写
still = client.get(f"/api/emfiling/filings/{fid8}").json()
check("单纯读取不改写已备案的历史结论", still["备案结论"] == "备案合格")

old_points = {p["监测点位编号"]: p for p in client.get("/api/emfiling/points").json()["items"]}
check("留档：0.20 按老版 0.4 仍判合格", old_points["P-0001-B"]["留档结论"] == "合格"
      and old_points["P-0001-B"]["判定限值标准号"] == "GB 8702-88")
r = post("/api/emfiling/versions", {"标准号": "TEST-2026", "功率密度限值": 0.02,
                                    "生效日期": "2026-09-01", "role": "运维人员"})
check("换版同样只授环保管理员，越权打回", r.json()["ok"] is False and r.json().get("missing_permission"))
r = post("/api/emfiling/versions", {"标准号": "TEST-2026", "功率密度限值": 0.02,
                                    "生效日期": "2026-09-01", "role": "环保归口管理员"})
check("新版限值发布成功", r.json()["ok"] and "重算" in r.json()["message"], r.json()["message"])
check("现行版已切换为 TEST-2026", client.get("/api/emfiling/versions").json()["current"]["标准号"] == "TEST-2026")
new_points = {p["监测点位编号"]: p for p in client.get("/api/emfiling/points").json()["items"]}
check("换版后 0.031 按新版重算为不合格", new_points["P-0001-A"]["现行限值结论"] == "不合格")
check("换版动作把存量合格档案打回不合格",
      client.get(f"/api/emfiling/filings/{fid8}").json()["备案结论"] == "备案不合格")
check("留档结论未被换版改写", new_points["P-0001-A"]["留档结论"] == "合格"
      and new_points["P-0001-B"]["留档结论"] == "合格")

print("== 8. 备案结论同步站点台账，另一入口取同一份 ==")
sites = {row["基站编号"]: row for row in client.get("/api/site").json()["items"]}
check("台账 SITE-0001 合规栏=不合规（换版后越线）",
      sites["SITE-0001"]["备案合规栏"].startswith("不合规"), sites["SITE-0001"].get("备案合规栏"))
check("台账未备案站点显示未备案", sites["SITE-0003"]["备案合规栏"] is not None)
c9 = client.get("/api/emfiling/site-compliance", params={"site_no": "SITE-0009"}).json()
check("另一入口 SITE-0009 读到备案合格结论",
      c9["合规栏"] == "合规" and c9["备案结论"] == "备案合格", str(c9))
c3 = client.get("/api/emfiling/site-compliance", params={"site_no": "SITE-0003"}).json()
check("SITE-0003 另一入口与台账同一份结论",
      c3["备案结论"] == sites["SITE-0003"]["备案结论"] == "备案不合格",
      f'{c3} vs {sites["SITE-0003"]}')
# 再查一次，模拟刷新/退出重进：必须是同一条
c3b = client.get("/api/emfiling/site-compliance", params={"site_no": "SITE-0003"}).json()
check("重复读取结论稳定一致", c3 == c3b)

print("== 9. 失效流转 ==")
r = post(f"/api/emfiling/filings/{fid}/expire")
check("已备案可置失效", r.json()["ok"] and r.json()["entry"]["status"] == "已失效")
c9b = client.get("/api/emfiling/site-compliance", params={"site_no": "SITE-0009"}).json()
check("失效后合规栏同步为已失效", c9b["合规栏"] == "已失效")

print(f"\n结果：通过 {PASS}，失败 {FAIL}")
sys.exit(1 if FAIL else 0)
