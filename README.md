# 运动工大 · 微信小程序逆向报告

| 项 | 值 |
|---|---|
| 目标 | `运动工大`（`C:\Users\Administrator\Desktop\运动工大.lnk`） |
| 类型 | 微信小程序（半屏快捷方式 `weixin://launchapplet/?app_id=wx02c99293b6fb15c3`） |
| AppID | `wx02c99293b6fb15c3` |
| 版本 | `1.5.9 [8f5e3b22]`（`app.js` globalData.version） |
| 主体 | 齐鲁工业大学（山东省科学院）体育体测 / 跑步打卡系统 |
| 后端 | `https://tytc.qlu.edu.cn`；统一认证 `https://sso.qlu.edu.cn`；人脸设备 `renlianweixin.qlu.edu.cn` |
| 小程序包 | `%APPDATA%\Tencent\xwechat\radium\users\4befa0808ebdf5a2b19a88c046afa3f1\applet\packages\wx02c99293b6fb15c3\57\__APP__.wxapkg` |
| 包体积 / MD5 | 1,036,887 B / `5973ab98ac7d839ce1eeac02b43fb6c5` |
| 解出内容 | 233 个文件、1,852,542 B；`app-service.js` 内含 74 个 AMD 模块 |

---

## 1. 包封装与解密

微信 4.x（`xwechat`）改掉了 3.x 的纯异或封装，换成了 `V1MMWX` 双层结构：

```
偏移 0x00   6 字节    b"V1MMWX"
偏移 0x06   1024 字节 AES-256-CBC 密文（装的是明文前 1023 字节 + 1 字节占位符）
偏移 0x406  余下全部  与单字节密钥异或
```

| 参数 | 值 |
|---|---|
| 密钥 | `PBKDF2-HMAC-SHA1(appid, salt="saltiest", iterations=1000, dkLen=32)` |
| 实例密钥 | `35d1c2679aefc1609cfd491db7e72baf17163124f9eb6e627acc4916c237e757` |
| IV | 固定字符串 `b"the iv: 16 bytes"` |
| 异或密钥 | `ord(appid[-2])` = `0x63`（`'c'`） |

**踩坑点（必须处理，否则索引表整体错位 1 字节）**：AES 段按 1024 字节整块加密，但明文有效长度只有 1023，第 1024 字节（偏移 `0x3FF`）是固定 `0x01` 占位符，不属于明文流。直接 `head(1024)+tail` 会让第一个文件名长度字段读出 `0x36000000`，索引解析当场崩掉。正确做法：`head[:1023] + tail`。

解密后是标准 wxapkg：`0xBE` 开头、`0xED` 在偏移 13、大端索引表。

```
0   uint8   0xBE
1   uint32  info1
5   uint32  indexInfoLength   （11355，含 14 字节头）
9   uint32  bodyInfoLength    （1025511）
13  uint8   0xED
14  uint32  fileCount         （233）
18  ...     条目: uint32 nameLen + name + uint32 offset + uint32 size
```

---

## 2. 技术栈与工程结构

- 编译产物形如 `chunk_N.appservice.js` + `chunk_N.webview.js`：**微信原生小程序**，逻辑层与渲染层分包，`page-frame.html` 是渲染骨架
- 逻辑代码全部在 `app-service.js`，以 `define("pages/xxx/xxx.js", function(...){})` 的 AMD 形式注册
- 依赖：`@babel/runtime`（helpers）、`miniprogram-sm-crypto`（**sm3 签名**）、`crypto-js`（AES）、`jsbn`、`base64-arraybuffer`
- 无 uni-app / Taro 特征；WXML 模板走 `$gwx_XC_N` 编译器函数

页面共 32 个，两套角色：

| 角色 | 页面 |
|---|---|
| 学生端 | `login-guide` `login-webview` `nav` `me` `run` `running` `run-face-check` `records` `points-map` `physical-test-scores` `semester-scores` `graduation-scores` `feedback-records` `face-information` `mine-run` `map-test` `sm-test` `help-webview` |
| 教师/管理端 | `login`（教师登录）`admin-index` `admin-select-student` `admin-select-class` `admin-input-score` `admin-student-scores` `admin-sprint-timer` `admin-face-detection` `admin-face-detection-process` `admin-device-face-import` `admin-height-and-weight` `admin-lungs-capacity` `admin-bluetooth-tutorial` `admin-bluetooth-debug` |

---

## 3. 鉴权体系（四层，全部在客户端完成）

### 3.1 固定 Basic 头

`app.js` globalData 里硬编码，**所有**请求都带：

```js
basicAuth: "Basic d2x5dzplanJ1eXNhaHdnYWRvaXZic3p1eWVzZGE4NzY5SUFB"
// base64 -> wlyw:ejruysahwgadoivbszuyesda8769IAA
```

**实测结论（与直觉不同，已核对）**：这个头不是网关强制的。`/api/notice/get-notice` 不带 `Authorization` 也照样返回 `code:10000` + 通知数据，带与不带响应完全一致（`2026-09-12T23:38:00` 那条"暂无通知"）。它更像给反向代理/业务层做客户端识别用的标记，真正的权限位点是 `LOGIN_SESSION`。凭据本身仍是硬编码泄露项，但不构成独立入口。

### 3.2 会话 Cookie

登录成功后服务端下发 `loginSession`，之后所有业务请求带：

```
Cookie: LOGIN_SESSION=<loginSession>
```

### 3.3 登录链路（学生）

```
wx.login() -> code
   └─ POST /api/wx-login-callback {code}
        ├─ code=10000  已绑定 -> 返回 userInfo + loginSession -> 按 permission 进 me / admin-index
        └─ code=10020  未绑定 -> 返回 openid，弹"仅限本校学生"提示，进 WebView
              └─ WebView 打开 https://sso.qlu.edu.cn/login?service=https://tytc.qlu.edu.cn/api/wx-login
                   └─ CAS 登录成功回调 /api/wx-login?ticket=ST-xxx
                        └─ POST /api/wx-login {ticket}  -> 拿到 loginSession（明文串）
                             └─ POST /api/wx-bind {openid, cipher:loginSession} -> 绑定完成
```

### 3.4 教师"登录码"（客户端复刻要点，`pages/login/login.js`）

教师不走微信登录，而是粘贴一串登录码，客户端**纯本地**解密后直接当会话用：

```js
长度必须 128 或 152，且以 "U2FsdGVkX1" 开头（CryptoJS 口令模式密文头 "Salted__"）
AES-ECB / PKCS7，口令 = "1919810@我是雷电 忘川守 芽衣和流萤和知更鸟的狗@114514@@"
明文 = "userName@userNumber@loginSession"
解出来后：globalData.userInfo.permission = "teacher"; globalData.loginSession = 第三段
→ redirectTo admin-index
```

口令常量在源码里用 `[+!+[]]` 这类数组混淆拼接（`login.js:36`），拆开就是上面那串。**全程没有任何服务端校验**，客户端只检查长度、前缀、`@` 分段数。会话串本身必须是服务端认可的，所以登录码本质是"别人替你登录一次拿到的凭据"。

### 3.5 请求签名（仅跑步相关）

`pages/running/running.js:362 getSignature()`：

```js
signature = SM3( loginSession + "#" + timestamp_ms + "#114WLYWGIVEYOU80KMSPORT514 )
请求体附带 { timestamp, signature }
```

- 哈希是 **SM3**（国密），来自 `miniprogram-sm-crypto`
- 拼接尾串 `114WLYWGIVEYOU80KMSPORT514` 由 `["114","WLYWGIVEYOU","80","KMSPORT514"]` 四段拼成，前三段被数组混淆
- 只用于 `/api/run/start-run`；`submit-running-data` 反而没签（照样带 timestamp/signature 字段，因为复用了同一个对象）

---

## 4. 接口全表（27 个端点）

| 接口 | 方法 | 鉴权 | 主要字段 | 用途 |
|---|---|---|---|---|
| `/api/notice/get-notice` | GET | Basic | — | 首页公告，`priority:-1` 会禁用跑步 |
| `/api/wx-login-callback` | POST | Basic | `code` | 微信 code 换会话 |
| `/api/wx-login?ticket=` | POST | Basic | `ticket` | CAS ticket 换会话 |
| `/api/wx-bind` | POST | Basic | `openid`,`cipher` | 会话绑 openid |
| `/api/admin/getservertoken` | GET | Basic | — | 返回 `TokenPublicKey`（客户端只存不用，死代码） |
| `/api/run/run-status` | GET | Cookie | — | 学期配置、已跑里程、及格/满分线、性别 |
| `/api/run/start-run` | POST | Cookie+**SM3** | `uuid`,`latitude`,`longitude` | 开始跑步，返回 `routeList` 打卡点 |
| `/api/run/submit-running-data` | POST | Cookie | `uuid`,`checkPoints`,`polyline`,`totalDistance`,`pauseTotalTime`,`soterAuth`,`batteryInfo`,`deviceSensor`,`wifiInfo`,`systemInfo` | 提交成绩（服务端复核） |
| `/api/run/set-run-status` | POST | Cookie | 同上 + `uiData`,`pureData`（JSON 字符串） | 每 45 s 暂存断点 |
| `/api/run/get-run-status` | GET | Cookie | — | 恢复断点续跑 |
| `/api/run/get-run-record` | GET | Cookie | — | 跑步记录列表 |
| `/api/run/get-checkpoint` | GET | Cookie | — | 打卡点地图 |
| `/api/physical/student-score-search` | GET | Cookie | — | 学生查体测成绩（按学期分组） |
| `/api/physical/confirm-score` | POST | Cookie | `number`,`term` | 学生确认成绩 |
| `/api/physical/student-search` | POST | Cookie | `keyword`,`index` | 教师检索学生 |
| `/api/physical/modify-score` | POST | Cookie | `id:-1`,`name`,`number`,`scores[]` | 教师录入体测成绩 |
| `/api/physical-general/modify-score` | POST | Cookie | 同上 | 课堂表现 / 技能分 |
| `/api/physical-general/student-search` | POST | Cookie | `keyword`,`index` | 同上检索 |
| `/api/class/get-all-fixed-class` | GET | Cookie | — | 行政班列表 |
| `/api/class/get-all-teach-class` | GET | Cookie | — | 教学班列表 |
| `/api/class/student-search` | POST | Cookie | `mode`,`index` | 按班级拉学生 |
| `/api/class/face-sync-single` | POST | Cookie | `studentId`,`faceBase64` | 单人人脸入库 |
| `/api/face/get-info` | GET | Cookie | — | 我的照片状态 |
| `/api/face/compare` | POST | Cookie | `image`(base64),`width`,`height`,`duration` | 跑步后本人核验 |
| `/api/face/find` | POST | Cookie | `image`,`width`,`height` | 教师端拍照找人（M:N 检索） |
| `/api/logger/lightlogger` | POST | Cookie | 任意数组 | 客户端日志上报 |
| `/bluetooth.json` | GET | Cookie | — | 蓝牙设备读取方案（身高体重秤等） |

科目 ID 映射（`app.js getSubjectId`）：`1` 肺活量、`2` 50 米、`3` 800/1000 米、`4` 立定跳远、`5` 坐位体前屈、`6` 引体向上、`7` 仰卧起坐、`8` BMI、`-1` 身高、`-2` 体重。

---

## 5. 跑步打卡逻辑还原

### 5.1 闭环

```
/api/run/start-run  (带 SM3 签名, 提交当前 GPS)
   └─ 返回 routeList（打卡点: name / latitude / longitude / radius）
   └─ 客户端定时 setInterval 每 45s -> /api/run/set-run-status  (整包状态 + 断点)
定位回调 onLocationChange：
   短区间测速  v = haversine(p1,p2) / Δt，单位 m/s
   命中区间   1.5 m/s < v < 6.5 m/s 才计入里程（normalVelocityRange）
   打卡判定   2000 * haversine(点, 我) < radius 且前一个点已打（有 allowRandomCheck 开关）
   通过时     震动 + 采电池 + 采传感器 + 立即 /api/run/set-run-status
结束：
   里程 ≥ passLine -> 进 run-face-check 人脸核验（3 次机会 / 30 s 限时）
   -> /api/face/compare 通过或失败（失败也提交）
   -> createUploadData() 组装整包 -> /api/run/submit-running-data
   -> 成功则 wx.shareToWeRun 上报微信运动
```

### 5.2 轨迹处理细节

- `fuzzyLocation()`：经纬度 `toFixed(5)`，约 1 米精度，抹掉细微抖动
- `douglasPeucker(points, 0.6)`：上传前抽稀，0.6 米容差
- 暂停上限 1800 s（30 min），超时自动结束并强制人脸
- 三个校区围栏（`running.js:279`）：长清 `116.8~116.82 / 36.55~36.568`、彩石 `117.26~117.273 / 36.658~36.668`、菏泽 `115.46~115.47 / 35.286~35.297`

### 5.3 反作弊采集项（随成绩一起上传）

| 数据 | 采集时机 | 说明 |
|---|---|---|
| `batteryInfo[]` | onLoad / onShow / onHide / 每个打卡点 / 结束 | `{time, remark, level, isCharging}` |
| `deviceSensor{}` | 同上，每次采样 1 s | 陀螺仪 + 加速度 + 指南针 + 运动姿态，四路一起 |
| `wifiInfo[]` | 每 14 s（仅 Android） | 周边 AP 列表，用于位置旁证 |
| `soterAuth` | 开始时 `checkIsSupportSoterAuthentication` | 生物识别能力探测 |
| `systemInfo` | 每次提交 | 设备型号 / 系统 / 微信版本 JSON |
| 人脸 | 结束且里程达标 | `/api/face/compare`，3 次机会 |

设计意图很清楚：**服务端不信任客户端算出来的里程**，靠"速度区间 + 点位顺序 + 传感器时序 + 电池跳变 + WiFi 环境"交叉验证轨迹是不是真跑出来的。判定全部在服务端，客户端只是采集器和上传器。

---

## 6. 教师端与设备

- **体测录入**：`admin-input-score` 逐项提交，`scores[].id` 用上面的科目 ID；课堂表现/技能分走 `physical-general`
- **短跑计时**：`admin-sprint-timer` 内置计时器，结束后直接 `modify-score` 写 50 米
- **蓝牙体测设备**：`/bluetooth.json` 下发读取方案（service / characteristic / 起始字节 / 大小端 / 除数）。内置方案：
  - `180F/2A19` 读电池
  - `FFE0/FFE1` Beryl 身高体重秤：offset 30 取 Uint16 ÷10 → 身高(cm)；offset 4 取 Uint16 ÷100 → 体重(kg)
- **人脸**：`admin-face-detection` 拍照 → `/api/face/find` 服务端 M:N 检索返回 `confidence` 排序候选；`admin-device-face-import` 从相册导图 → `/api/class/face-sync-single` 入库

---

## 7. 客户端弱点清单

按可利用性排序，全部有源码位置可查：

1. **全局 Basic 凭据硬编码**（`app.js`）：`wlyw:ejruysahwgadoivbszuyesda8769IAA`。实测公共接口不校验它，所以它不是独立入口；但用户名口令形态的凭据落在代码里，若同一套账密在别处复用（内网网关、其他子系统），横向价值很高。
2. **教师登录码可自造**（`login.js:23-36`）：AES 口令写死在包里，格式检查全在本地。任何人能构造出 `userName@userNumber@loginSession` 就能进教师端 UI —— 真正的门槛只剩"第三段会话是否有效"。
3. **签名密钥硬编码**（`running.js:362`）：`114WLYWGIVEYOU80KMSPORT514` 就在代码里，SM3 也是公开算法，客户端签名等于没有签名，只能挡"完全没读过包的人"。
4. **`permission` 由客户端字段决定**（`login.js:9`）：`globalData.userInfo.permission = "teacher"` 是前端赋值，页面跳转靠它。服务端若不二次校验，越权入口就在 `/api/physical/*`、`/api/class/*`。
5. **反作弊参数可读**（`running.js` 常量）：速度区间 `[1.5, 6.5]`、容差 `0.6 m`、采样周期、打卡半径判定公式全部明文，规则逆向成本为零。
6. **上传体字段无签名保护**：`submit-running-data` 不带 SM3，整包可离线组装重放；服务端只能靠传感器/电池时序自洽性判断。
7. **日志接口可写**：`/api/logger/lightlogger` 接受任意数组，未验证是否校验会话。若校验宽松，可无会话灌日志（未实测，避免污染对方日志库）。
8. **公钥接口空转**：`/api/admin/getservertoken` 下发 `TokenPublicKey`，客户端 `fetchPublicKey()` 存进 `data.publicKey` 后无任何引用，SM2 只在 import 里出现一次。

---

## 8. 工具链

| 文件 | 作用 |
|---|---|
| `wxapkg_tool.py` | **一键**：解密 → 解包 → 格式化 → 拆模块 → 出接口表 |
| `decrypt.py` | V1MMWX 解密（含 1023 字节坑的处理与结构自检） |
| `unpack.py` | wxapkg 大端索引解析与落盘（带路径穿越防护） |
| `fmt.py` | 自研 JS 格式化器（token 流，保留源码换行以维持 ASI 语义） |
| `split_modules.py` | 按 `define("path")` 括号配平拆分单模块 |
| `extract_api.py` | 扫描 `wx.request` 生成 `api_map.json` |
| `sm3.py` | 纯 Python SM3（与国标向量一致） |
| `qlu_client.py` | 完整 API 客户端（含签名、跑步、成绩、人脸） |
| `login_code.py` | 教师登录码编解码 |

```bash
# 1. 一键还原
python wxapkg_tool.py \
  --pkg "%APPDATA%/Tencent/xwechat/radium/users/4befa0808ebdf5a2b19a88c046afa3f1/applet/packages/wx02c99293b6fb15c3/57/__APP__.wxapkg" \
  --appid wx02c99293b6fb15c3 --out out
# 预期：[1/4] 解密 1036887 -> 1036880 / [2/4] 233 files / [3/4] 82 JS / [4/4] 74 modules

# 2. 用客户端打接口
export QLU_SESSION='<登录后拿到的 loginSession>'
python qlu_client.py status
python qlu_client.py records
python qlu_client.py start --lat 36.557897 --lon 116.81167
python qlu_client.py scores

# 3. 登录码往返
python login_code.py encode --name 张三 --number 2023123456 --session "<session>"
python login_code.py decode "U2FsdGVkX1..."
```

**已验证的实跑结果**（未带会话，仅验证协议栈）：

```
$ python qlu_client.py notice
{"status":200,"body":{"code":10000,"message":"获取通知","data":{"content":"暂无通知",...}}}

$ python qlu_client.py status
{"status":200,"body":{"code":10005,"message":"未登录","data":null}}
```

前者证明 Basic 头与请求格式还原正确；后者证明会话校验位点与预期一致（未登录被 10005 拦住）。带真实会话的业务接口未执行 —— 需要一份有效的 `LOGIN_SESSION`。

---

## 9. 产物清单

```
wxre/wx02c99293b6fb15c3/
├── out/__APP__.dec.wxapkg      明文包 1,036,880 B
├── out/src/                    233 个原始文件（wxml/wxss/js/json/png/svg/html）
├── out/pretty/                 82 个格式化 JS（全部通过 node --check）
├── out/modules/                74 个单模块源码（app / 32 页面 / 14 组件 / npm 依赖）
├── api_map.json                接口调用表
├── raw/__APP__.wxapkg          解密产物（中间态）
└── *.py                        工具链 + 客户端 + 编解码器
```
