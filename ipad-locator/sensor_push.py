# -*- coding: utf-8 -*-
"""
把生成的传感器数据流推到 iPad 上（不需要越狱，走 AFC 文件服务）

落点：/var/mobile/Media/sensorspoof.json
越狱后的注入插件（sensor_spoof/）就从这里读，边跑边回放给 CoreMotion。

注意：这一步只是「把数据放到设备上」，真正让 App 读到假数据需要越狱注入。
"""

import asyncio
import os

import sensor_gen

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_PATH = os.path.join(HERE, "sensorspoof.json")
REMOTE_PATH = "/sensorspoof.json"


async def _push(local: str, remote: str, serial=None) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lk = await create_using_usbmux(serial=serial, autopair=True)
    try:
        afc = AfcService(lockdown=lk)
        await afc.push(local, remote)
    finally:
        try:
            await lk.close()
        except Exception:
            pass


def push_stream(stream, serial=None, local_path: str = LOCAL_PATH, remote: str = REMOTE_PATH) -> str:
    """生成的文件落盘后推到设备，返回本地路径。"""
    sensor_gen.save_json(stream, local_path)
    asyncio.run(_push(local_path, remote, serial))
    return local_path


def push_file(local_path: str, serial=None, remote: str = REMOTE_PATH) -> str:
    asyncio.run(_push(local_path, remote, serial))
    return remote
