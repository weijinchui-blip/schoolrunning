# -*- coding: utf-8 -*-
"""
中国三家坐标系之间的换算

- WGS84：GPS 原始坐标，iPad 的定位用的就是它
- GCJ-02：高德 / 腾讯 / 谷歌中国 的坐标（国测局加密，俗称火星坐标）
- BD-09：百度坐标（在 GCJ-02 上又加了一层偏移）
- BD09MC：百度墨卡托米制坐标（百度瓦片/POI 内部用的投影坐标）

设备只认 WGS84，所以任何从地图服务拿到的坐标都要先转回来。
"""

import math

_A = 6378245.0
_EE = 0.00669342162296594323
_X_PI = math.pi * 3000.0 / 180.0


def out_of_china(lat, lon):
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _tlat(x, y):
    r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return r


def _tlon(x, y):
    r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return r


def wgs84_to_gcj02(lat, lon):
    if out_of_china(lat, lon):
        return lat, lon
    dlat = _tlat(lon - 105.0, lat - 35.0)
    dlon = _tlon(lon - 105.0, lat - 35.0)
    rad = lat / 180.0 * math.pi
    magic = math.sin(rad)
    magic = 1 - _EE * magic * magic
    sqrtm = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtm) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrtm * math.cos(rad) * math.pi)
    return lat + dlat, lon + dlon


def gcj02_to_wgs84(lat, lon):
    if out_of_china(lat, lon):
        return lat, lon
    mlat, mlon = wgs84_to_gcj02(lat, lon)
    return lat * 2 - mlat, lon * 2 - mlon


def gcj02_to_bd09(gcj_lat, gcj_lon):
    z = math.sqrt(gcj_lon * gcj_lon + gcj_lat * gcj_lat) + 0.00002 * math.sin(gcj_lat * _X_PI)
    theta = math.atan2(gcj_lat, gcj_lon) + 0.000003 * math.cos(gcj_lon * _X_PI)
    return z * math.sin(theta) + 0.006, z * math.cos(theta) + 0.0065


def bd09_to_gcj02(bd_lat, bd_lon):
    x = bd_lon - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return z * math.sin(theta), z * math.cos(theta)


def wgs84_to_bd09(lat, lon):
    g = wgs84_to_gcj02(lat, lon)
    return gcj02_to_bd09(g[0], g[1])


def bd09_to_wgs84(bd_lat, bd_lon):
    g = bd09_to_gcj02(bd_lat, bd_lon)
    return gcj02_to_wgs84(g[0], g[1])


# --------------------------------------------------------------- BD09MC 投影
# 百度墨卡托不是标准 Web Mercator，官方用分段多项式反算，
# 下表是百度地图 JS 里的 MC2LL 系数（按 |y| 分 6 段）
_MCBAND = [12890594.86, 8362377.87, 5591021, 3481989.83, 1678043.12, 0]
_MC2LL = [
    [1.410526172116255e-8, 8.98305509648872e-6, -1.9939833816331, 200.9824383106796,
     -187.2403703815547, 91.6087516669843, -23.38765649603339, 2.57121317296198,
     -0.03801003308653, 17337981.2],
    [-7.435856389565537e-9, 8.983055097726239e-6, -0.78625201886289, 96.32687599759846,
     -1.85204757529826, -59.36935905485877, 47.40033549296737, -16.50741931063887,
     2.28786674699375, 10260144.86],
    [-3.030883460898826e-8, 8.98305509983578e-6, 0.30071316287616, 59.74293618442277,
     7.357984074871, -25.38371002664745, 13.45380521110908, -3.29883767235584,
     0.32710905363475, 6856817.37],
    [-1.981981304930552e-8, 8.983055099779535e-6, 0.03278182852591, 40.31678527705744,
     0.65659298677277, -4.44255534477492, 0.85341911805263, 0.12923347998204,
     -0.04625736007561, 4482777.06],
    [3.09191371068437e-9, 8.983055096812155e-6, 6.995724062e-5, 23.10934304144901,
     -2.3663490511e-4, -0.6321817810242, -0.00663494467273, 0.03430082397953,
     -0.00466043876332, 2555164.4],
    [2.890871144776878e-9, 8.983055095805407e-6, -3.068298e-8, 7.47137025468032,
     -3.53937994e-6, -0.02145144861037, -1.234426596e-5, 1.0322952773e-4,
     -3.23890364e-6, 826088.5],
]


def bd09mc_to_bd09(x, y):
    """百度墨卡托米 -> BD09 经纬度"""
    if x is None or y is None:
        return None
    c = _MC2LL[-1]
    for i, band in enumerate(_MCBAND):
        if abs(y) >= band:
            c = _MC2LL[i]
            break
    lon = c[0] + c[1] * abs(x)
    t = abs(y) / c[9]
    lat = (c[2] + c[3] * t + c[4] * t ** 2 + c[5] * t ** 3
           + c[6] * t ** 4 + c[7] * t ** 5 + c[8] * t ** 6)
    return (-lat if y < 0 else lat), (-lon if x < 0 else lon)


def bd09mc_to_wgs84(x, y):
    bd = bd09mc_to_bd09(x, y)
    if bd is None:
        return None
    return bd09_to_wgs84(bd[0], bd[1])
