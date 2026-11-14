# sensor_spoof —— 传感器数据流注入（越狱侧）

把电脑算好的加速度/陀螺仪/设备运动/计步数据，按真实采样率回放给 CoreMotion，
让微信（及小程序）读到的传感器数据和 GPS 轨迹是**同一个运动学**。

> **交付状态说明（必读）**
> - ✅ 数据生成：`../sensor_gen.py`，已用 FFT 验证主频 = 步频（2.84 Hz vs 2.833 Hz）、
>   二次谐波、峰值 2.38 g、转弯 1.08 rad/s 都在真人范围。
> - ✅ 数据下发：`../sensor_push.py`，已实测通过 AFC 写入
>   `/var/mobile/Media/sensorspoof.json`（69 KB / 1350 点）。
> - ⚠️ **本目录的 Tweak.x 未编译、未验证** —— 我手上没有越狱设备，无法 `make package` 和上机。
>   代码是按 CoreMotion 常规 hook 方式写的，能不能跑通需要你在越狱机上自己验证。

## 为什么必须越狱

电脑通过 USB 能做的只有 DVT（定位、截图、进程列表、syslog…）。实测这台 iPad：

- RSD 服务 59 个，**含 motion/sensor/accel/gyro 关键词的：0 个**
- `pymobiledevice3` 全库搜索 accelerometer/gyroscope，只命中 MobileGestalt 的**能力声明**和
  `DiagnosticsService` 的**只读** ioregistry
- 诊断接口的方法面：`mobilegestalt / info / ioregistry / get_battery / get_wifi / restart / shutdown / sleep`

也就是说：**没有"写入传感器读数"的通道**。CoreMotion 的数据来自运动协处理器，
只有在内核/用户态被 hook 才能改。

## 编译（需要一个 Linux/macOS + Theos）

```bash
# Theos
export THEOS=~/theos
git clone --recursive https://github.com/theos/theos.git $THEOS

# 本目录（rootless）
cd sensor_spoof
make clean package THEOS_PACKAGE_SCHEME=rootless
# 产物：packages/com.local.sensorspoof_1.0.0_iphoneos-arm64.deb
```

装到设备：

```bash
scp packages/*.deb root@<设备IP>:/var/mobile/
ssh root@<设备IP> "dpkg -i /var/mobile/*.deb && killall -9 WeChat"
```

（或直接把 deb 丢进 Sileo/Zebra 安装。）

## 数据流从哪来

电脑端：画好轨迹 → 勾「拟真步态」→ 点 **传感器流**，会：

1. 用和 GPS 完全相同的 `gait_samples()` 推进轨迹；
2. 按 `fs=50` 生成 `ax/ay/az`（g，含重力）与 `gx/gy/gz`（rad/s）；
3. 写入 `sensorspoof.json` 并推到设备 `/var/mobile/Media/`。

```
meta: fs=50, cadence=170, step_hz=2.833, duration=85s, distance=249m, steps=237
data: [[0.0, 0.031, 0.042, 1.093, 0.12, 0.07, 0.02], ...]
```

Tweak 每 1/fs 秒取一行，构造 `CMAccelerometerData` / `CMGyroData` / `CMDeviceMotion`，
`timestamp` 用「载入时刻 + 索引/fs」，这样 1 秒窗口的样本数与真机一致。

## 已知限制

- 只覆盖 `CMMotionManager` 与 `CMPedometer` 这两条路。如果小程序走 `CMSensorRecorder`
  或 `HealthKit` 的步数，本插件管不到。
- `CMPedometerData` 是只读 class cluster，这里用 KVC 兜底；失败会放行原始实现（宁可不伪造也不崩）。
- 微信有越狱检测（`/var/jb`、Sileo、ellekit、可疑 dylib 列表），**注入本身可能直接暴露**。
  风险自己权衡：伪造传感器是为了过传感器校验，但越狱会把"检测到越狱环境"这个更大红旗立起来。
- 设备是 iPad 时别指望"还原真实手机运动"：iPad 通常不带计步协处理器，`CMPedometer` 可能直接不可用。
