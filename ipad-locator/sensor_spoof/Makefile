TARGET := iphone:clang:latest:15.0
ARCHS = arm64 arm64e
INSTALL_TARGET_PROCESSES = WeChat

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = sensor_spoof
sensor_spoof_FILES = Tweak.x
sensor_spoof_FRAMEWORKS = UIKit CoreMotion Foundation
sensor_spoof_CFLAGS = -fobjc-arc

include $(THEOS_MAKE_PATH)/tweak.mk
