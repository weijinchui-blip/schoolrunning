// sensor_spoof —— 把预先算好的传感器流回放给 CoreMotion
//
// 适用：越狱设备（rootless / palera1n + ellekit），注入微信进程 com.tencent.xin
// 数据：/var/mobile/Media/sensorspoof.json（由电脑端「传感器流」按钮生成并推上来）
//
// 钩的面：
//   加速度计  startAccelerometerUpdates(ToQueue:withHandler:) / accelerometerData
//   陀螺仪    startGyroUpdates(ToQueue:withHandler:) / gyroData
//   设备运动  startDeviceMotionUpdates*(ToQueue:withHandler:) / deviceMotion
//   计步器    CMPedometer queryPedometerDataFromDate:toDate:withHandler:
//
// 回放时序：按 meta.fs 定频，timestamp 用「载入时刻 + 索引/fs」，
// 保证 1 秒窗口里的样本数与真实设备一致（小程序按秒取窗口做频谱判断）。

#import <CoreMotion/CoreMotion.h>
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <math.h>

#define SP_STREAM_PATH @"/var/mobile/Media/sensorspoof.json"

#pragma mark - 数据

static NSArray *gSPData = nil;
static double gSPFs = 50.0;
static NSTimeInterval gSPStart = 0;

static void SPLoadStream(void) {
    NSData *raw = [NSData dataWithContentsOfFile:SP_STREAM_PATH];
    if (!raw) {
        NSLog(@"[sensorspoof] 没找到 %@", SP_STREAM_PATH);
        return;
    }
    NSError *err = nil;
    NSDictionary *root = [NSJSONSerialization JSONObjectWithData:raw options:0 error:&err];
    if (![root isKindOfClass:[NSDictionary class]]) {
        NSLog(@"[sensorspoof] 解析失败: %@", err);
        return;
    }
    NSDictionary *meta = root[@"meta"];
    if ([meta isKindOfClass:[NSDictionary class]]) {
        id fs = meta[@"fs"];
        if ([fs respondsToSelector:@selector(doubleValue)] && [fs doubleValue] > 1) {
            gSPFs = [fs doubleValue];
        }
    }
    gSPData = root[@"data"];
    NSLog(@"[sensorspoof] 载入 %lu 点 @ %.0f Hz（%.1f 秒）", (unsigned long)gSPData.count, gSPFs,
          gSPData.count / gSPFs);
}

static NSArray *SPSampleAtIndex(NSInteger idx) {
    if (!gSPData.count) return nil;
    if (idx < 0) idx = 0;
    if (idx >= (NSInteger)gSPData.count) idx = (NSInteger)gSPData.count - 1;
    return gSPData[idx];
}

#pragma mark - 假数据对象
// CMAccelerometerData / CMGyroData / CMDeviceMotion / CMAttitude 的属性都是只读的
// （class cluster），这里用子类覆盖 getter —— 这类 tweak 的常规做法。

@interface SPAccelerometerData : CMAccelerometerData
@property(nonatomic, assign) CMAcceleration spAcceleration;
@property(nonatomic, assign) NSTimeInterval spTimestamp;
@end
@implementation SPAccelerometerData
- (CMAcceleration)acceleration { return _spAcceleration; }
- (NSTimeInterval)timestamp { return _spTimestamp; }
@end

@interface SPGyroData : CMGyroData
@property(nonatomic, assign) CMRotationRate spRotationRate;
@property(nonatomic, assign) NSTimeInterval spTimestamp;
@end
@implementation SPGyroData
- (CMRotationRate)rotationRate { return _spRotationRate; }
- (NSTimeInterval)timestamp { return _spTimestamp; }
@end

@interface SPAttitude : CMAttitude
@property(nonatomic, assign) double spRoll;
@property(nonatomic, assign) double spPitch;
@property(nonatomic, assign) double spYaw;
@end
@implementation SPAttitude
- (double)roll { return _spRoll; }
- (double)pitch { return _spPitch; }
- (double)yaw { return _spYaw; }
@end

@interface SPDeviceMotion : CMDeviceMotion
@property(nonatomic, assign) CMAcceleration spUserAcceleration;
@property(nonatomic, assign) CMRotationRate spRotationRate;
@property(nonatomic, strong) CMAttitude *spAttitude;
@property(nonatomic, assign) NSTimeInterval spTimestamp;
@end
@implementation SPDeviceMotion
- (CMAcceleration)userAcceleration { return _spUserAcceleration; }
- (CMRotationRate)rotationRate { return _spRotationRate; }
- (CMAttitude *)attitude { return _spAttitude; }
- (NSTimeInterval)timestamp { return _spTimestamp; }
@end

#pragma mark - 回放引擎

@interface SPEngine : NSObject
@property(nonatomic, strong) NSOperationQueue *accelQueue;
@property(nonatomic, strong) NSOperationQueue *gyroQueue;
@property(nonatomic, strong) NSOperationQueue *motionQueue;
@property(nonatomic, copy) CMAccelerometerHandler accelHandler;
@property(nonatomic, copy) CMGyroHandler gyroHandler;
@property(nonatomic, copy) CMDeviceMotionHandler motionHandler;
@property(nonatomic, strong) dispatch_source_t timer;
@property(nonatomic, assign) double roll, pitch, yaw;
@property(nonatomic, strong) SPAccelerometerData *lastAccel;
@property(nonatomic, strong) SPGyroData *lastGyro;
@property(nonatomic, strong) SPDeviceMotion *lastMotion;
+ (instancetype)shared;
- (void)ensureLoaded;
@end

@implementation SPEngine

+ (instancetype)shared {
    static SPEngine *inst = nil;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        inst = [SPEngine new];
    });
    return inst;
}

- (void)ensureLoaded {
    if (!gSPData.count) {
        SPLoadStream();
    }
}

- (void)ensureTimer {
    if (self.timer) return;
    uint64_t nsec = (uint64_t)(NSEC_PER_SEC / gSPFs);
    self.timer = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0,
                                        dispatch_get_global_queue(QOS_CLASS_USER_INTERACTIVE, 0));
    dispatch_source_set_timer(self.timer, dispatch_time(DISPATCH_TIME_NOW, 0), nsec, nsec / 4);
    __weak typeof(self) weakSelf = self;
    dispatch_source_set_event_handler(self.timer, ^{
        [weakSelf tick];
    });
    dispatch_resume(self.timer);
}

- (void)tick {
    if (!gSPData.count) return;
    if (!gSPStart) gSPStart = CACurrentMediaTime();
    NSTimeInterval now = CACurrentMediaTime() - gSPStart;
    NSInteger idx = (NSInteger)floor(now * gSPFs);
    NSArray *row = SPSampleAtIndex(idx);
    if (!row || row.count < 7) return;

    // JSON 行: [t, ax, ay, az, gx, gy, gz]；accel 单位 g，gyro 单位 rad/s
    double ax = [row[1] doubleValue], ay = [row[2] doubleValue], az = [row[3] doubleValue];
    double gx = [row[4] doubleValue], gy = [row[5] doubleValue], gz = [row[6] doubleValue];
    NSTimeInterval ts = gSPStart + idx / gSPFs;

    double dt = 1.0 / gSPFs;
    self.roll += gx * dt;
    self.pitch += gy * dt;
    self.yaw += gz * dt;

    SPAccelerometerData *acc = [SPAccelerometerData new];
    acc.spAcceleration = (CMAcceleration){ ax, ay, az };
    acc.spTimestamp = ts;

    SPGyroData *gyro = [SPGyroData new];
    gyro.spRotationRate = (CMRotationRate){ gx, gy, gz };
    gyro.spTimestamp = ts;

    SPAttitude *att = [SPAttitude new];
    att.spRoll = self.roll;
    att.spPitch = self.pitch;
    att.spYaw = self.yaw;

    SPDeviceMotion *motion = [SPDeviceMotion new];
    motion.spUserAcceleration = (CMAcceleration){ ax, ay, az - 1.0 };  // 扣掉重力
    motion.spRotationRate = (CMRotationRate){ gx, gy, gz };
    motion.spAttitude = att;
    motion.spTimestamp = ts;

    self.lastAccel = acc;
    self.lastGyro = gyro;
    self.lastMotion = motion;

    if (self.accelHandler && self.accelQueue) {
        CMAccelerometerHandler h = self.accelHandler;
        [self.accelQueue addOperationWithBlock:^{
            h(acc, nil);
        }];
    }
    if (self.gyroHandler && self.gyroQueue) {
        CMGyroHandler h = self.gyroHandler;
        [self.gyroQueue addOperationWithBlock:^{
            h(gyro, nil);
        }];
    }
    if (self.motionHandler && self.motionQueue) {
        CMDeviceMotionHandler h = self.motionHandler;
        [self.motionQueue addOperationWithBlock:^{
            h(motion, nil);
        }];
    }
}

@end

#pragma mark - Hooks

%hook CMMotionManager

- (void)startAccelerometerUpdatesToQueue:(NSOperationQueue *)queue
                            withHandler:(CMAccelerometerHandler)handler {
    SPEngine *e = [SPEngine shared];
    [e ensureLoaded];
    if (!gSPData.count) {
        %orig;
        return;
    }
    e.accelQueue = queue ?: [NSOperationQueue mainQueue];
    e.accelHandler = handler;
    [e ensureTimer];
}

- (void)stopAccelerometerUpdates {
    [SPEngine shared].accelHandler = nil;
    %orig;
}

- (CMAccelerometerData *)accelerometerData {
    SPAccelerometerData *fake = [SPEngine shared].lastAccel;
    return fake ?: %orig;
}

- (void)startGyroUpdatesToQueue:(NSOperationQueue *)queue withHandler:(CMGyroHandler)handler {
    SPEngine *e = [SPEngine shared];
    [e ensureLoaded];
    if (!gSPData.count) {
        %orig;
        return;
    }
    e.gyroQueue = queue ?: [NSOperationQueue mainQueue];
    e.gyroHandler = handler;
    [e ensureTimer];
}

- (void)stopGyroUpdates {
    [SPEngine shared].gyroHandler = nil;
    %orig;
}

- (CMGyroData *)gyroData {
    SPGyroData *fake = [SPEngine shared].lastGyro;
    return fake ?: %orig;
}

- (void)startDeviceMotionUpdatesToQueue:(NSOperationQueue *)queue
                            withHandler:(CMDeviceMotionHandler)handler {
    SPEngine *e = [SPEngine shared];
    [e ensureLoaded];
    if (!gSPData.count) {
        %orig;
        return;
    }
    e.motionQueue = queue ?: [NSOperationQueue mainQueue];
    e.motionHandler = handler;
    [e ensureTimer];
}

- (void)startDeviceMotionUpdatesUsingReferenceFrame:(CMAttitudeReferenceFrame)frame
                                            toQueue:(NSOperationQueue *)queue
                                        withHandler:(CMDeviceMotionHandler)handler {
    SPEngine *e = [SPEngine shared];
    [e ensureLoaded];
    if (!gSPData.count) {
        %orig;
        return;
    }
    e.motionQueue = queue ?: [NSOperationQueue mainQueue];
    e.motionHandler = handler;
    [e ensureTimer];
}

- (void)stopDeviceMotionUpdates {
    [SPEngine shared].motionHandler = nil;
    %orig;
}

- (CMDeviceMotion *)deviceMotion {
    SPDeviceMotion *fake = [SPEngine shared].lastMotion;
    return fake ?: %orig;
}

%end

// 计步器：避免「GPS 跑了 1900 步、系统步数却是 0」这种明显穿帮
%hook CMPedometer

- (void)queryPedometerDataFromDate:(NSDate *)from
                            toDate:(NSDate *)to
                       withHandler:(CMPedometerHandler)handler {
    if (!handler) return;
    [SPEngine.shared ensureLoaded];
    NSString *metaPath = SP_STREAM_PATH;
    NSData *raw = [NSData dataWithContentsOfFile:metaPath];
    NSDictionary *meta = nil;
    if (raw) {
        NSDictionary *root = [NSJSONSerialization JSONObjectWithData:raw options:0 error:nil];
        if ([root isKindOfClass:[NSDictionary class]]) meta = root[@"meta"];
    }
    if (![meta isKindOfClass:[NSDictionary class]]) {
        %orig;
        return;
    }
    double steps = [meta[@"steps"] doubleValue];
    double dist = [meta[@"distance_m"] doubleValue];
    double dur = MAX([meta[@"duration"] doubleValue], 1.0);
    double frac = MIN(1.0, MAX(0.0, [to timeIntervalSinceDate:from] / dur));

    id obj = nil;
    @try {
        Class cls = NSClassFromString(@"CMPedometerData");
        obj = [[cls alloc] init];
        [obj setValue:@(steps * frac) forKey:@"numberOfSteps"];
        [obj setValue:@(dist * frac) forKey:@"distance"];
        [obj setValue:from forKey:@"startDate"];
        [obj setValue:to forKey:@"endDate"];
    } @catch (NSException *e) {
        NSLog(@"[sensorspoof] pedometer 构造失败，放行原始实现: %@", e);
        %orig;
        return;
    }
    NSLog(@"[sensorspoof] pedometer %.0f%% -> %.0f 步 / %.0f 米", frac * 100, steps * frac, dist * frac);
    handler(obj, nil);
}

%end

#pragma mark - 初始化

%ctor {
    SPLoadStream();
    NSLog(@"[sensorspoof] 注入 %@", [[NSBundle mainBundle] bundleIdentifier]);
    [[NSNotificationCenter defaultCenter]
        addObserverForName:UIApplicationDidBecomeActiveNotification
                    object:nil
                     queue:[NSOperationQueue mainQueue]
                usingBlock:^(NSNotification *n) {
                  // 回到前台时重载一次：换数据流不用重启微信
                  SPLoadStream();
                  gSPStart = 0;
                }];
}
