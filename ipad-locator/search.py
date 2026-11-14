# -*- coding: utf-8 -*-
"""
地名搜索（把名字变成坐标）

三个来源，按顺序尝试，任何一个能用就返回：

1. 百度地图 官方地点检索 API —— 需要自己在 settings.json 里填 baidu_ak
   （免费申请：https://lbsyun.baidu.com/ → 控制台 → 应用管理 → 创建应用 → 服务端）
2. 百度地图 Web 检索接口 —— 免 AK，返回 BD09MC 坐标，本模块转成 WGS84
3. Photon（OSM 数据）—— 免 AK 兜底，返回 WGS84

不管走哪条，返回的 lat/lon 都是 **WGS84**，可以直接喂给设备。
"""

import requests

import geo

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 12


def _get(url, **kw):
    headers = dict(kw.pop("headers", {}))
    headers.setdefault("User-Agent", UA)
    return requests.get(url, headers=headers, timeout=TIMEOUT, **kw)


# ------------------------------------------------------------------ 百度：AK
def _baidu_ak(query, limit, ak):
    r = _get(
        "https://api.map.baidu.com/place/v2/search",
        params={
            "query": query,
            "region": "全国",
            "output": "json",
            "ak": ak,
            "page_size": min(max(limit, 1), 20),
            "scope": 2,
        },
    )
    data = r.json()
    if data.get("status") != 0:
        raise RuntimeError(f"百度 AK 检索失败：{data.get('message') or data.get('status')}")
    out = []
    for it in data.get("results", []) or []:
        loc = it.get("location") or {}
        if "lat" not in loc or "lng" not in loc:
            continue
        lat, lon = geo.bd09_to_wgs84(float(loc["lat"]), float(loc["lng"]))
        out.append(
            {
                "name": it.get("name", ""),
                "addr": (it.get("address") or it.get("area") or "").strip(),
                "lat": lat,
                "lon": lon,
                "src": "百度(AK)",
            }
        )
    return out[:limit]


# ------------------------------------------------------- 百度：Web 接口免 AK
def _parse_geo(geo_str):
    """'1|12958170.88,4825940.97;...' -> (mcx, mcy)"""
    try:
        body = geo_str.split("|", 1)[1]
        first = body.split(";")[0]
        x, y = first.split(",")[:2]
        return float(x), float(y)
    except Exception:
        return None


def _baidu_web(query, limit):
    r = _get(
        "https://map.baidu.com/",
        params={
            "qt": "s",
            "wd": query,
            "c": "1",          # 1 = 全国
            "ie": "utf-8",
            "from": "webmap",
            "src": "0",
            "wd2": "",
            "pn": "0",
            "sug": "0",
            "l": "12",
        },
        headers={"Referer": "https://map.baidu.com/"},
    )
    data = r.json()
    items = data.get("content") or []
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        mc = _parse_geo(it.get("geo") or "")
        if not mc:
            continue
        wgs = geo.bd09mc_to_wgs84(mc[0], mc[1])
        if not wgs:
            continue
        out.append(
            {
                "name": it.get("name", ""),
                "addr": (it.get("addr") or it.get("area_name") or "").strip(),
                "lat": wgs[0],
                "lon": wgs[1],
                "src": "百度",
            }
        )
    # 名字完全匹配的排前面
    out.sort(key=lambda x: 0 if x["name"] == query else 1)
    return out[:limit]


# ----------------------------------------------------------------- Photon 兜底
def _photon(query, limit):
    r = _get("https://photon.komoot.io/api/", params={"q": query, "limit": limit})
    data = r.json()
    out = []
    for f in data.get("features", []):
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        name = p.get("name") or p.get("street") or query
        parts = [p.get("city"), p.get("state"), p.get("country")]
        addr = " ".join([x for x in parts if x])
        out.append({"name": name, "addr": addr, "lat": float(coords[1]), "lon": float(coords[0]), "src": "OSM"})
    return out[:limit]


def search_places(query, limit=8, ak=None):
    """返回 [{'name','addr','lat','lon','src'}, ...]，坐标是 WGS84。"""
    query = (query or "").strip()
    if not query:
        return []
    errors = []

    if ak:
        try:
            res = _baidu_ak(query, limit, ak)
            if res:
                return res
        except Exception as exc:  # noqa: BLE001
            errors.append(f"AK: {exc}")

    try:
        res = _baidu_web(query, limit)
        if res:
            return res
    except Exception as exc:  # noqa: BLE001
        errors.append(f"百度: {type(exc).__name__}")

    try:
        res = _photon(query, limit)
        if res:
            return res
    except Exception as exc:  # noqa: BLE001
        errors.append(f"OSM: {type(exc).__name__}")

    if errors:
        raise RuntimeError("搜不到（" + "；".join(errors) + "）")
    return []


def label_of(item):
    """给下拉框用的显示文本"""
    name = item["name"] or "未命名"
    addr = item["addr"]
    tag = item.get("src", "")
    return f"{name} · {addr}  [{tag}]" if addr else f"{name}  [{tag}]"
