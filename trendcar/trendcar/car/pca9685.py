try:
    import smbus2 as smbus
except:
    import smbus


# PCA9685 spec: # http://wiki.sunfounder.cc/images/e/ea/PCA9685_datasheet.pdf
class PCA9685(object):
    # Register constants
    _MODE1          = 0x00
    _MODE2          = 0x01
    _SUBADR1        = 0x02
    _SUBADR2        = 0x03
    _SUBADR3        = 0x04
    _ALLCALLADR     = 0x05
    _LED0_ON_L      = 0x06
    _LED0_ON_H      = 0x07
    _LED0_OFF_L     = 0x08
    _LED0_OFF_H     = 0x09
#   ...
    _LED15_ON_L     = 0x42
    _LED15_ON_H     = 0x43
    _LED15_OFF_L    = 0x44
    _LED15_OFF_H    = 0x45
#   ...reserved...
    _ALL_LED_ON_L   = 0xFA
    _ALL_LED_ON_H   = 0xFB
    _ALL_LED_OFF_L  = 0xFC
    _ALL_LED_OFF_H  = 0xFD
    _PRESCALE       = 0xFE
    _TESTMODE       = 0xFF

    # Mode 1 constants
    _MODE1_RESTART  = (1 << 7)
    _MODE1_EXTCLK   = (1 << 6)
    _MODE1_AI       = (1 << 5)
    _MODE1_SLEEP    = (1 << 4)
    _MODE1_SUB1     = (1 << 3)
    _MODE1_SUB2     = (1 << 2)
    _MODE1_SUB1     = (1 << 1)
    _MODE1_ALLCALL  = (1 << 0)

    # Mode 2 constants
    _MODE2_INVRT    = (1 << 4)
    _MODE2_OCH      = (1 << 3)
    _MODE2_OUTDRV   = (1 << 2)
    _MODE2_OUTNE_00 = 0x00
    _MODE2_OUTNE_01 = 0x01
    _MODE2_OUTNE_10 = 0x10


    def __init__(self, i2c_addr = 0x40, pwm_freq = 50, cacheable = True):
        self._cache     = {}
        self._cacheable = cacheable

        self._delay()
        self._i2c_bus   = smbus.SMBus(1)  # /dev/i2c-1
        self.i2c_addr   = i2c_addr
        self.pwm_freq   = pwm_freq


    @property
    def i2c_addr(self):
        return self._i2c_addr


    @i2c_addr.setter
    def i2c_addr(self, _i2c_addr):
        self._i2c_addr = _i2c_addr
        self.reset()


    def _delay(self):
        import time
        time.sleep(0.005)


    @property
    def pwm_freq(self):
        return 1.0 / ((self.prescale + 1) * 4096 / 25e6)


    @pwm_freq.setter
    def pwm_freq(self, value):
        self.sleeping = True
        self.prescale = int(25e6 / 4096 / float(value) - 1.0)
        self._delay()
        self.sleeping = False


    def reset(self):
        self._cache = {}

        self._i2c_bus.write_byte_data(self._i2c_addr, self._ALL_LED_ON_L , 0)
        self._i2c_bus.write_byte_data(self._i2c_addr, self._ALL_LED_ON_H , 0)
        self._i2c_bus.write_byte_data(self._i2c_addr, self._ALL_LED_OFF_L, 0)
        self._i2c_bus.write_byte_data(self._i2c_addr, self._ALL_LED_OFF_H, 0)

        self.channel[-1] = {"on": True, "duty": 0}
        self.mode2 = self._MODE2_OUTDRV
        self.mode1 = self._MODE1_ALLCALL | self._MODE1_AI
        self._delay()


    @property
    def mode1(self):
        if not self._cacheable or "mode1" not in self._cache:
            self._cache["mode1"] = self._i2c_bus.read_byte_data(self._i2c_addr, self._MODE1)
        return self._cache["mode1"]


    @mode1.setter
    def mode1(self, value):
        if not self._cacheable or "mode1" not in self._cache or self._cache["mode1"] != value:
            self._i2c_bus.write_byte_data(self._i2c_addr, self._MODE1, value)
            self._cache["mode1"] = value


    @property
    def mode2(self):
        if not self._cacheable or "mode2" not in self._cache:
            self._cache["mode2"] = self._i2c_bus.read_byte_data(self._i2c_addr, self._MODE2)
        return self._cache["mode2"]


    @mode2.setter
    def mode2(self, value):
        if not self._cacheable or "mode2" not in self._cache or self._cache["mode2"] != value:
            self._i2c_bus.write_byte_data(self._i2c_addr, self._MODE2, value)
            self._cache["mode2"] = value


    @property
    def prescale(self):
        if not self._cacheable or "prescale" not in self._cache:
            self._cache["prescale"] = self._i2c_bus.read_byte_data(self._i2c_addr, self._PRESCALE)
        return self._cache["prescale"]


    @prescale.setter
    def prescale(self, value):
        if not self._cacheable or "prescale" not in self._cache or self._cache["prescale"] != value:
            self._i2c_bus.write_byte_data(self._i2c_addr, self._PRESCALE, value)
            self._cache["prescale"] = value


    @property
    def auto_increment(self):
        return (self.mode1 & self._MODE1_AI) != 0


    @auto_increment.setter
    def auto_increment(self, enabled):
        if enabled:
            self.mode1 = self.mode1 | self._MODE1_AI
        else:
            self.mode1 = self.mode1 & ~self._MODE1_AI


    @property
    def sleeping(self):
        return (self.mode1 & self._MODE1_SLEEP) != 0


    @sleeping.setter
    def sleeping(self, enabled):
        if enabled:
            self.mode1 = self.mode1 | self._MODE1_SLEEP
        else:
            self.mode1 = self.mode1 & ~self._MODE1_SLEEP


    def set_channel(self, ch, duty = None, on = None):
        if 0 <= ch <= 15:
            base_index = ch * 4 + self._LED0_ON_L
        elif ch < 0 or ch >= 16:
            base_index = self._ALL_LED_ON_L
        elif self._LED0_ON_L <= ch <= self._LED15_ON_L:
            base_index = ch
            ch -= self._LED0_ON_L
        elif ch == self._ALL_LED_ON_L:
            base_index = ch
            ch = -1
        else:
            return False

        if duty is None:
            if on is None:
                return False

            on = bool(on)

            if ch < 0:
                for ch in range(16):
                    if self._cacheable and ch in self._cache and (self._cache[ch][1] & 0x10 == 0) == on:
                        continue

                    if ch not in self._cache:
                        self._cache[ch] = self._i2c_bus.read_i2c_block_data(self._i2c_addr, base_index + 2, 2)

                    value = self._cache[ch][1]

                    if on:
                        value &= 0x0f
                    else:
                        value |= 0x10

                    self._i2c_bus.write_byte_data(self._i2c_addr, base_index + 3, value)
                    self._cache[ch][1] = value

            elif not self._cacheable or ch not in self._cache or (self._cache[ch][1] & 0x10 == 0) != on:
                if ch not in self._cache:
                    self._cache[ch] = self._i2c_bus.read_i2c_block_data(self._i2c_addr, base_index + 2, 2)

                value = self._cache[ch][1]

                if on:
                    value &= 0x0f
                else:
                    value |= 0x10

                self._i2c_bus.write_byte_data(self._i2c_addr, base_index + 3, value)
                self._cache[ch][1] = value

            return True

        if isinstance(duty, float):
            duty = min(max(duty, 0.0), 100.0)
            duty = int(4095.0 / 100.0 * duty)
        else:
            try:
                duty = min(max(int(duty), 0), 4095)
            except:
                return False

        value = [duty & 0xff, (duty >> 8) & 0x0f]

        if on is not None and bool(on) is False:
            value[1] |= 0x10

        if self._cacheable and ch in self._cache and self._cache[ch] == value:
            return True

        self._i2c_bus.write_i2c_block_data(self._i2c_addr, base_index + 2, value)
        self._cache[ch] = value
        return True


    def get_channel(self, ch):
        if 0 <= ch <= 15:
            base_index = ch * 4 + self._LED0_ON_L
        elif ch < 0 or ch >= 16:
            base_index = self._ALL_LED_ON_L
        elif self._LED0_ON_L <= ch <= self._LED15_ON_L:
            base_index = ch
            ch -= self._LED0_ON_L
        elif ch == self._ALL_LED_ON_L:
            base_index = ch
            ch = -1
        else:
            return None

        if not self._cacheable or ch not in self._cache:
            self._cache[ch] = self._i2c_bus.read_i2c_block_data(self._i2c_addr, base_index + 2, 2)

        return {
            "duty": self._cache[ch][0] + ((self._cache[ch][1] & 0x0f) << 8),
            "on"  : (self._cache[ch][1] & 0x10) == 0,
        }


    @property
    def channel(self):
        class ChannelProxy:
            def __init__(self, controller):
                self._controller = controller

            def __getitem__(self, ch):
                if isinstance(ch, slice):
                    result = []
                    for i in range(ch.start or 0, ch.stop or 16, ch.step or 1):
                        result.append(self._controller.get_channel(ch))
                    return result

                return self._controller.get_channel(ch)

            def __setitem__(self, ch, value):
                params = {}
                if isinstance(value, bool):
                    params["on"] = value
                elif isinstance(value, int):
                    params["duty"] = int(value)
                elif isinstance(value, float):
                    params["duty"] = float(value)
                elif isinstance(value, dict):
                    if "on" in value and isinstance(value["on"], bool):
                        params["on"] = value["on"]
                    if "duty" in value:
                        if isinstance(value["duty"], int):
                            params["duty"] = int(value["duty"])
                        elif isinstance(value["duty"], float):
                            params["duty"] = float(value["duty"])

                if isinstance(ch, slice):
                    for i in range(ch.start or 0, ch.stop or 16, ch.step or 1):
                        self._controller.set_channel(ch, **params)
                else:
                    self._controller.set_channel(ch, **params)

        return ChannelProxy(self)


    @property
    def info(self):
        info = {
            "mode1": self.mode1,
            "mode2": self.mode2,
            "sleeping": self.sleeping,
            "prescale": self.prescale,
            "pwm_freq": self.pwm_freq,
        }
        for ch in range(16):
            info[ch] = self.channel[ch]

        return info


if __name__ == "__main__":
    from pprint import pprint
    controller = PCA9685()
    pprint(controller.info)
    controller.channel[0] = 900
    controller.channel[1] = 0
    controller.channel[2] = 900

    controller.channel[3] = 900
    controller.channel[4] = 0
    controller.channel[5] = 900

    controller.channel[6] = 0
    controller.channel[7] = 900
    controller.channel[8] = 900

    controller.channel[9] = 0
    controller.channel[10] = 900
    controller.channel[11] = 900
    pprint(controller.info)

