from common.stuff import *

import numpy as np
from common import imgutils
from collections import OrderedDict

_models = OrderedDict()


def register_model(cls):
    _models[cls.__name__] = cls


def get_model(name, *args, **argv):
    if name is None:
        name = "NullModel"
    return _models[name](*args, **argv)


def get_model_names():
    return _models.keys()


def set_default_frame_width(frame_width):
    config.set("CAMERA", "default_frame_width", int(frame_width))


def get_default_frame_width():
    return config.getint("CAMERA", "default_frame_width", 320)


def set_default_frame_height(frame_height):
    config.set("CAMERA", "default_frame_height", int(frame_height))


def get_default_frame_height():
    return config.getint("CAMERA", "default_frame_height", 240)


def set_default_frame_rate(frame_rate):
    config.set("CAMERA", "default_frame_rate", int(frame_rate))


def get_default_frame_rate():
    return config.getint("CAMERA", "default_frame_rate", 30)


def get_default_camera_exposure():
    return config.getint("CAMERA", "default_camera_exposure", 180)


def set_default_camera_exposure(exposure):
    config.set("CAMERA", "default_camera_exposure", int(exposure))


class Model(object):
    def __init__(self):
        pass


    def __str__(self):
        return type(self).__name__


    def __repr__(self):
        return type(self).__name__


    def begin(self, is_detecting = False, ignore_platform_check = False):
        raise Exception("%s.begin(): Implementation required" % (repr(self)))


    def end(self):
        raise Exception("%s.end(): Implementation required" % (repr(self)))


    def control_motors(self, throttle_pwms = None):
        raise Exception("%s.control_motors(): Implementation required" % (repr(self)))


    def vibrate(self, count, interval = 0):
        raise Exception("%s.vibrate(): Implementation required" % (repr(self)))


    def drive_by_pwms(self, front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration = 0.0):
        raise Exception("%s.drive_motor_pwms(): Implementation required" % (repr(self)))


    def drive(self, steering, throttle, duration = 0.0, flipped = False):
        raise Exception("%s.drive(): Implementation required" % (repr(self)))


    def get_snapshot(self, ndx = None):
        raise Exception("%s.get_snapshot(): Implementation required" % (repr(self)))


    def ready_to_go(self):
        raise Exception("%s.ready_to_go(): Implementation required" % (repr(self)))


    def get_camera_name(self, ndx = 0):
        return config.get("CAMERA", "camera%d_name" % ndx, "camera%d" % ndx)


    def set_camera_name(self, ndx, name):
        return config.set("CAMERA", "camera%d_name" % ndx, name)


    def get_frame_width(self, ndx = 0):
        return config.getint("CAMERA", "camera%d_frame_width" % ndx, get_default_frame_width())


    def set_frame_width(self, ndx, frame_width):
        return config.set("CAMERA", "camera%d_frame_width" % ndx, int(frame_width))


    def get_frame_height(self, ndx = 0):
        return config.getint("CAMERA", "camera%d_frame_height" % ndx, get_default_frame_height())


    def set_frame_height(self, ndx, frame_height):
        return config.set("CAMERA", "camera%d_frame_height" % ndx, int(frame_height))


    def get_frame_rate(self, ndx = 0):
        return config.getint("CAMERA", "camera%d_frame_rate" % ndx, get_default_frame_rate())


    def set_frame_rate(self, ndx, frame_rate):
        return config.set("CAMERA", "camera%d_frame_rate" % ndx, int(frame_rate))


    def get_camera_exposure(self, ndx = 0):
        return config.getint("CAMERA", "camera%d_exposure" % ndx, get_default_camera_exposure())


    def set_camera_exposure(self, ndx, exposure):
        return config.set("CAMERA", "camera%d_exposure" % ndx, int(exposure))


@register_model
class NullModel(Model):
    def begin(self, is_detecting = False, ignore_platform_check = False):
        return False


    def end(self):
        return False


@register_model
class TrendCarModel(Model):
    DEF_MAX_CAMERA_COUNT      = 1
    DEF_CAMERA_CACHE_MAX_LIFE = 5.0

    ALL_MOTORS                = "ALL_MOTORS"
    FRONT_LEFT_MOTOR          = "FRONT_LEFT_MOTOR"
    REAR_LEFT_MOTOR           = "REAR_LEFT_MOTOR"
    FRONT_RIGHT_MOTOR         = "FRONT_RIGHT_MOTOR"
    REAR_RIGHT_MOTOR          = "REAR_RIGHT_MOTOR"

    DEF_MOTOR_CHANNELS        = {
        FRONT_LEFT_MOTOR :  (0,  1,  2),
        REAR_LEFT_MOTOR  :  (3,  4,  5),
        FRONT_RIGHT_MOTOR:  (6,  7,  8),
        REAR_RIGHT_MOTOR :  (9, 10, 11),
    }
    DEF_PCA9685_VCC_GPIO_PIN  = 7

    DEF_MIN_VALID_MOTOR_PWM   = 0.2
    DEF_MAX_VALID_MOTOR_PWM   = 1.0

    def __init__(self):
        super(type(self), self).__init__()
        self._GPIO            = None
        self._PCA9685         = None
        self._cam             = []
        self._cam_cache       = {}
        self._cam_grab_thread = None
        self._motor_channels = self.DEF_MOTOR_CHANNELS.copy()

        front_left_motor = (
            config.getint("PCA9685", "front_left_motor_a_channel"  , None),
            config.getint("PCA9685", "front_left_motor_k_channel"  , None),
            config.getint("PCA9685", "front_left_motor_en_channel" , None)
        )
        rear_left_motor = (
            config.getint("PCA9685", "rear_left_motor_a_channel"   , None),
            config.getint("PCA9685", "rear_left_motor_k_channel"   , None),
            config.getint("PCA9685", "rear_left_motor_en_channel"  , None)
        )
        front_right_motor = (
            config.getint("PCA9685", "front_right_motor_a_channel" , None),
            config.getint("PCA9685", "front_right_motor_k_channel" , None),
            config.getint("PCA9685", "front_right_motor_en_channel", None)
        )
        rear_right_motor = (
            config.getint("PCA9685", "rear_right_motor_a_channel"  , None),
            config.getint("PCA9685", "rear_right_motor_k_channel"  , None),
            config.getint("PCA9685", "rear_right_motor_en_channel" , None)
        )

        if all([x is not None for x in front_left_motor]):
            self._motor_channels[self.FRONT_LEFT_MOTOR] = front_left_motor
        if all([x is not None for x in rear_left_motor]):
            self._motor_channels[self.REAR_LEFT_MOTOR] = rear_left_motor
        if all([x is not None for x in front_right_motor]):
            self._motor_channels[self.FRONT_RIGHT_MOTOR] = front_right_motor
        if all([x is not None for x in rear_right_motor]):
            self._motor_channels[self.REAR_RIGHT_MOTOR] = rear_right_motor

        self._pca9685_vcc_gpio_pin        = config.getint("PCA9685", "vcc_gpio_pin", self.DEF_PCA9685_VCC_GPIO_PIN)

        self._default_min_valid_motor_pwm = config.getfloat("MOTOR", "default_min_valid_motor_pwm", self.DEF_MIN_VALID_MOTOR_PWM)
        self._default_max_valid_motor_pwm = config.getfloat("MOTOR", "default_max_valid_motor_pwm", self.DEF_MAX_VALID_MOTOR_PWM)
        front_left_motor_min_pwm          = config.getfloat("MOTOR", "front_left_motor_min_pwm"   , None)
        front_left_motor_max_pwm          = config.getfloat("MOTOR", "front_left_motor_max_pwm"   , None)
        rear_left_motor_min_pwm           = config.getfloat("MOTOR", "rear_left_motor_min_pwm"    , None)
        rear_left_motor_max_pwm           = config.getfloat("MOTOR", "rear_left_motor_max_pwm"    , None)
        front_right_motor_min_pwm         = config.getfloat("MOTOR", "front_right_motor_min_pwm"  , None)
        front_right_motor_max_pwm         = config.getfloat("MOTOR", "front_right_motor_max_pwm"  , None)
        rear_right_motor_min_pwm          = config.getfloat("MOTOR", "rear_right_motor_min_pwm"   , None)
        rear_right_motor_max_pwm          = config.getfloat("MOTOR", "rear_right_motor_max_pwm"   , None)

        self._motor_pwm_range = {
            self.FRONT_LEFT_MOTOR :  [self._default_min_valid_motor_pwm, self._default_max_valid_motor_pwm],
            self.REAR_LEFT_MOTOR  :  [self._default_min_valid_motor_pwm, self._default_max_valid_motor_pwm],
            self.FRONT_RIGHT_MOTOR:  [self._default_min_valid_motor_pwm, self._default_max_valid_motor_pwm],
            self.REAR_RIGHT_MOTOR :  [self._default_min_valid_motor_pwm, self._default_max_valid_motor_pwm],
        }

        if front_left_motor_min_pwm  is not None:
            self._motor_pwm_range[self.FRONT_LEFT_MOTOR][0]  = front_left_motor_min_pwm
        if front_left_motor_max_pwm  is not None:
            self._motor_pwm_range[self.FRONT_LEFT_MOTOR][1]  = front_left_motor_max_pwm
        if rear_left_motor_min_pwm   is not None:
            self._motor_pwm_range[self.REAR_LEFT_MOTOR][0]   = rear_left_motor_min_pwm
        if rear_left_motor_max_pwm   is not None:
            self._motor_pwm_range[self.REAR_LEFT_MOTOR][1]   = rear_left_motor_max_pwm
        if front_right_motor_min_pwm is not None:
            self._motor_pwm_range[self.FRONT_RIGHT_MOTOR][0] = front_right_motor_min_pwm
        if front_right_motor_max_pwm is not None:
            self._motor_pwm_range[self.FRONT_RIGHT_MOTOR][1] = front_right_motor_max_pwm
        if rear_right_motor_min_pwm  is not None:
            self._motor_pwm_range[self.REAR_RIGHT_MOTOR][0]  = rear_right_motor_min_pwm
        if rear_right_motor_max_pwm  is not None:
            self._motor_pwm_range[self.REAR_RIGHT_MOTOR][1]  = rear_right_motor_max_pwm

        self._default_camera_vertical_flip   = config.getbool("CAMERA", "default_camera_vertical_flip"  , False)
        self._default_camera_horizontal_flip = config.getbool("CAMERA", "default_camera_horizontal_flip", False)


    def begin(self, is_detecting = False, ignore_platform_check = False, skip_camera = False):
        if not ignore_platform_check and not hwinfo.is_running_in_pi():
            return False

        try:
            import RPi.GPIO as GPIO
            self._GPIO = GPIO

            self._GPIO.setwarnings(False)
            self._GPIO.setmode(self._GPIO.BOARD)
            self._GPIO.setup(self._pca9685_vcc_gpio_pin, self._GPIO.OUT)
            self._GPIO.output(self._pca9685_vcc_gpio_pin, self._GPIO.HIGH)
            CHECK_PASSED("GPIO Library")
        except:
            if is_detecting:
                debug_exc("TrendCarModel: Unable to initialize PCA9685 PWM control board")
            else:
                error_exc("TrendCarModel: Unable to initialize PCA9685 PWM control board")

            if self._GPIO:
                try:
                    self._GPIO.output(self._pca9685_vcc_gpio_pin, self._GPIO_LOW)
                except:
                    pass
                self._GPIO = None

            CHECK_FAILED("GPIO Library")
            return False

        try:
            from car.pca9685 import PCA9685
            self._PCA9685 = PCA9685()
            CHECK_PASSED("PCA9685 I2C Connection")
        except:
            self._PCA9685 = None
            CHECK_FAILED("PCA9685 I2C Connection")
            return False

        if skip_camera:
            return True

        os.system('sudo modprobe bcm2835-v4l2 >/dev/null 2>&1') # in case picam is used

        while len(self._cam) > 0:
            cam = self._cam.pop(0)
            if cam is not None:
                try:
                    cam.release()
                except:
                    pass
                cam = None

        self._cam_cache = {}

        for ndx in range(config.getint("CAMERA", "max_camera_count", self.DEF_MAX_CAMERA_COUNT)):
            try:
                cam = None

                for i in range(5):
                    try:
                        cam = cv2.VideoCapture(ndx)

                        if cam is not None:
                            break

                        debug("TrendCarModel: Unable to open %s", self.get_camera_name(ndx), ndx)
                    except:
                        debug_exc("TrendCarModel: Unable to open %s", self.get_camera_name(ndx), ndx)

                    time.sleep(0.5)

                if cam is None:
                    break

                cam.set(cv2.CAP_PROP_FRAME_WIDTH , self.get_frame_width(ndx))
                cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.get_frame_height(ndx))
                cam.set(cv2.CAP_PROP_FPS         , self.get_frame_rate(ndx))

                if not cam.isOpened():
                    cam.release()
                    cam = None
                    break

                # assume the last cam is the primary cam
                self.set_frame_width(ndx, cam.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.set_frame_height(ndx, cam.get(cv2.CAP_PROP_FRAME_HEIGHT))

                if self.get_camera_exposure(ndx) <= 0:
                    time.sleep(1.0)
                    os.system('sudo v4l2-ctl -c exposure_auto=3 -d /dev/video%d >/dev/null 2>&1' % (ndx))
                else:
                    time.sleep(1.0)
                    os.system('sudo v4l2-ctl -c exposure_auto=1 -d /dev/video%d >/dev/null 2>&1' % (ndx))
                    time.sleep(1.0)
                    os.system('sudo v4l2-ctl -c exposure_absolute=%d -d /dev/video%d >/dev/null 2>&1' % (self.get_camera_exposure(ndx), ndx))

                self._cam.insert(0, cam)

                debug("TrendCarModel: %s (%dx%d @%dfps) was found.", self.get_camera_name(ndx), self.get_frame_width(ndx), self.get_frame_height(ndx), self.get_frame_rate(ndx))
            except:
                debug_exc("TrendCarModel: Unable to setup %s due to exception", self.get_camera_name(ndx))
                break

        if len(self._cam) == 0:
            if is_detecting:
                debug("TrendCarModel: No cameras were available.")
            else:
                error("TrendCarModel: No cameras were available.")

            CHECK_FAILED("OpenCV Camera")
            return False

        self._cam_grab_thread = threading.Thread(target = self._cam_grabbing_loop, name = "model-cam-grab")
        self._cam_grab_thread.setDaemon(True)
        self._cam_grab_thread.start()
        CHECK_PASSED("OpenCV Camera")
        return True


    def end(self):
        while len(self._cam) > 0:
            cam = self._cam.pop()
            if cam is not None:
                if cam.isOpened():
                    cam.release()
                cam = None

        self._cam_grab_thread = None
        self._cam_cache = {}

        if self._PCA9685 is not None:
            try:
                self._PCA9685.reset()
            except:
                pass
            self._PCA9685 = None

        if self._GPIO is not None:
            try:
                self._GPIO.output(self._pca9685_vcc_gpio_pin, self._GPIO_LOW)
                self._GPIO.cleanup()
            except:
                pass
            self._GPIO = None

        return True


    def _set_motor_pwm(self, motor, pwm):
        try:
            channels = self._motor_channels.get(motor, (None, None, None))

            if len(list(filter(lambda ch: ch is not None, channels))) == 3:
                if pwm >= 0:
                    a_channel, k_channel, en_channel = channels
                else:
                    k_channel, a_channel, en_channel = channels
                    pwm = -pwm

                if pwm > 1.0:
                    pwm = 1.0

                if pwm > 0.0:
                    min_valid_motor_pwm, max_valid_motor_pwm = self._motor_pwm_range.get(motor, [self._default_min_valid_motor_pwm, self._default_max_valid_motor_pwm])
                    pwm = (pwm * (max_valid_motor_pwm - min_valid_motor_pwm)) + min_valid_motor_pwm

                self._PCA9685.channel[a_channel ] = 100.0 * pwm
                self._PCA9685.channel[k_channel ] = 0.0
                self._PCA9685.channel[en_channel] = 100.0 if pwm else 0.0
                return True

            warn("TrendCarModel: Unable to obtain the channels of %s motor", motor)
        except:
            warn_exc("TrendCarModel: Unable to control the channels of %s motor", motor)

        return False


    def control_motors(self, throttle_pwms = None):
        if throttle_pwms is None:
            self._PCA9685.reset()
            return

        if self.ALL_MOTORS in throttle_pwms:
            pwm = throttle_pwms[self.ALL_MOTORS]
            del throttle_pwms[self.ALL_MOTORS]

            for motor in (self.FRONT_LEFT_MOTOR, self.REAR_LEFT_MOTOR, self.FRONT_RIGHT_MOTOR, self.REAR_RIGHT_MOTOR):
                throttle_pwms[motor] = pwm

        for motor in throttle_pwms:
            self._set_motor_pwm(motor, throttle_pwms[motor])


    def vibrate(self, count, interval = 0.5):
        for i in range(count):
            self.control_motors({self.ALL_MOTORS: 0.1})
            time.sleep(0.03)
            self.control_motors({self.ALL_MOTORS: -0.1})
            time.sleep(0.03)
            self.control_motors({self.ALL_MOTORS: 0.0})
            time.sleep(interval)


    def _get_motor_pwms_by_steering_throttle(self, steering, throttle):
        if -0.002 < throttle < 0.002:
            throttle = 0.0

        if -0.005 <= steering <= 0.005:
            steering = 0.0
        elif steering <= -89.995:
            steering = -90.0
        elif steering >= 89.995:
            steering = 90.0

        if throttle == 0.0:
            return (0.0, 0.0, 0.0, 0.0) # stop all wheels

        if -5.0 <= steering <= 5.0:
            return (throttle, throttle, throttle, throttle) # go straight either forward or backward

        if steering >= 90.0:
            return (throttle, throttle, -throttle, -throttle) # spin clockwise

        if steering <= -90.0:
            return (-throttle, -throttle, throttle, throttle) # spin counter-clockwise

        sharp_turning_angle        = config.getfloat("MOTOR", "steering_sharp_turning_angle", 40.0)
        sharp_turning_min_pwm      = config.getfloat("MOTOR", "steering_sharp_turning_min_pwm", 0.67)
        steering_with_low_friction = config.getbool("MOTOR", "steering_with_low_friction", False)


        def _map_proportional_value(from_value, from_lower, from_upper, to_lower, to_upper):
            return to_lower + (1.0 * (from_value - from_lower) / (from_upper - from_lower)) * (to_upper - to_lower)


        def _get_linear_pwm_mapping(steering, throttle):
            if not steering_with_low_friction:
                return (throttle, throttle * (90.0 - abs(steering)) / 90.0)

            steering  = abs(steering)
            direction = 1.0 if throttle >= 0 else -1.0
            throttle  = abs(throttle)

            if steering <= sharp_turning_angle:
                pwm_difference = _map_proportional_value(steering, 0, sharp_turning_angle, 0, 1.0)

                if throttle >= pwm_difference:
                    return (throttle * direction, (throttle - pwm_difference) * direction)

                throttle = _map_proportional_value(steering, 0.0, sharp_turning_angle, 0.0, 1.0) * direction
                return (throttle, 0.0)

            throttle = _map_proportional_value(steering, sharp_turning_angle, 90.0, sharp_turning_min_pwm, 1.0) * direction
            return (throttle, -0.01 * direction)


        throttle_pwm, brake_pwm = _get_linear_pwm_mapping(steering, throttle)

        if 5.0 < steering < 90.0:
            return (throttle_pwm, throttle_pwm, brake_pwm, brake_pwm)

        # -90.0 < steering < -5.0
        return (brake_pwm, brake_pwm, throttle_pwm, throttle_pwm)


    def drive_by_pwms(self, front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration = 0.0):
        if not self._PCA9685:
            return False

        try:
            self.control_motors({
                    self.FRONT_LEFT_MOTOR : front_left_pwm ,
                    self.REAR_LEFT_MOTOR  : rear_left_pwm  ,
                    self.FRONT_RIGHT_MOTOR: front_right_pwm,
                    self.REAR_RIGHT_MOTOR : rear_right_pwm ,
            })
        except:
            self.control_motors()
            warn_exc("TrendCarModel: Unable to drive the motors with steering = %f, throttle = %f, duration = %0.2f", steering, throttle, duration)

        return True


    def drive(self, steering, throttle, duration = 0.0, flipped = False):
        if flipped:
            throttle = -throttle
            steering = -steering

        if config.getbool("MOTOR", "steering_inversed", False):
            steering = -steering

        return self.drive_by_pwms(*self._get_motor_pwms_by_steering_throttle(steering, throttle), duration = duration)


    def _cam_grabbing_loop(self):
        set_thread_name(self._cam_grab_thread.getName())

        try:
            while len(self._cam) > 0:
                for ndx in range(len(self._cam)):
                    self._cam[ndx].grab()

                time.sleep(0.00001)
        except:
            debug_exc("TrendCarModel: exception occurred in cam_grabbing_loop")


    def get_snapshot(self, ndx = None):
        def normalized_frame(ndx, frame):
            vertical_flip   = config.getbool("CAMERA", "camera%d_vertical_flip"   % ndx, self._default_camera_vertical_flip  )
            horizontal_flip = config.getbool("CAMERA", "camera%d_horizontal_flip" % ndx, self._default_camera_horizontal_flip)

            if vertical_flip:
                if horizontal_flip:
                    frame = cv2.flip(frame, 0)
                else:
                    frame = cv2.flip(frame, -1)
            elif horizontal_flip:
                frame = cv2.flip(frame, 1)

            return frame

        now = monotonic()
        camera_cache_max_life = config.getfloat("CAMERA", "camera_cache_max_life", self.DEF_CAMERA_CACHE_MAX_LIFE)

        if ndx is None:
            snapshots = []

            for ndx in range(len(self._cam)):
                interval = min(1.0 / self.get_frame_rate(ndx), camera_cache_max_life)

                if ndx in self._cam_cache and now - self._cam_cache[ndx]["timestamp"] < interval:
                    snapshots.append(self._cam_cache[ndx]["frame"])
                    continue

                try:
                    ret, frame = self._cam[ndx].retrieve()

                    if ret:
                        frame = normalized_frame(ndx, frame)
                        self._cam_cache[ndx] = {"timestamp": now, "frame": frame}
                        snapshots.append(frame)
                        continue
                except cv2.error:
                    pass
                except:
                    warn_exc("TrendCarModel: Unable to retrieve the image frame from camera[%d]", ndx)

                if ndx in self._cam_cache and now - self._cam_cache[ndx]["timestamp"] < camera_cache_max_life:
                    snapshots.append(self._cam_cache[ndx]["frame"])
                else:
                    snapshots.append(None)

            return snapshots

        if ndx >= 0 and ndx < len(self._cam):
            interval = min(1.0 / self.get_frame_rate(ndx), camera_cache_max_life)

            if ndx in self._cam_cache and now - self._cam_cache[ndx]["timestamp"] < interval:
                return self._cam_cache[ndx]["frame"]

            try:
                ret, frame = self._cam[ndx].retrieve()

                if ret:
                    frame = normalized_frame(ndx, frame)
                    self._cam_cache[ndx] = {"timestamp": now, "frame": frame}
                    return frame

            except cv2.error:
                pass
            except:
                warn_exc("TrendCarModel: Unable to retrieve the image frame from camera[%d]", ndx)

            if ndx in self._cam_cache and now - self._cam_cache[ndx]["timestamp"] < camera_cache_max_life:
                return self._cam_cache[ndx]["frame"]
        else:
            warn("TrendCarModel: Unable to retrieve the image frame from camera[%d] because index was out of bound.", ndx)

        return None


    def ready_to_go(self):
        return None


@register_model
class TrendCarSimulatorModel(Model):
    def __init__(self):
        super(type(self), self).__init__()
        self._mutex                 = threading.Lock()
        self._raw_image             = None
        self._frame                 = None
        self._first_connected       = False

        self._is_running            = False
        self._websocket             = None
        self._websocket_recv_thread = None
        self._websocket_send_thread = None
        self._simulators            = []


    def begin(self, is_detecting = False, ignore_platform_check = False):
        if not ignore_platform_check and hwinfo.is_running_in_pi():
            return False

        try:
            from common.SimpleWebSocketServer import WebSocket, SimpleWebSocketServer

            class TrendCarSimulatorAdapter(WebSocket):
                def __init__(self, server, sock, address, user_context = None):
                    super(type(self), self).__init__(server, sock, address, user_context)
                    self._input_seq  = -1
                    self._output_seq = -1


                def _get_json_data(self, msg):
                    try:
                        if not msg or len(msg) == 0:
                            return None

                        start = msg.find("[")
                        if start < 0:
                            return None

                        end = msg.rfind("}]")
                        if end < 0:
                            return None

                        if start >= end:
                            return None

                        import json
                        return json.loads(msg[start: end + 2])

                    except:
                        debug_exc("TrendCarSimulatorModel: exception occurred while parsing json from message: %s", msg)
                        return None


                def _drive(self, steering, throttle):
                    while self._input_seq >= 0 and self._output_seq >= self._input_seq + 1:
                        time.sleep(0.0025)

                    if self._output_seq < 0 or self._input_seq < 0:
                        return

                    self.sendMessage(r"""42["steer",{"steering_angle":"%f","throttle":"%f"}]""" % (steering, throttle), True)
                    self._output_seq += 1


                def handleMessage(self):
                    msg = self.data.decode("iso8859-1")

                    if not msg or len(msg) == 0:
                        return

                    # protocol description: https://github.com/socketio/engine.io-protocol

                    #if msg[0] == "1": #close transport
                    #    return

                    if msg[0] == "2": #ping
                        self.sendMessage("3" + msg[1:], True) #pong
                        return

                    #if msg[0] == "41": #????
                    #   return

                    if msg[:2] == "42": #websocket event
                        res = self._get_json_data(msg)

                        if not res:
                            self.sendMessage(r"""42["manual",{}]""", True)
                            info("TrendCarSimulatorModel: Manual driving mode enabled")
                            return

                        try:
                            if res[0] == "telemetry":
                                with self.getUserContext()._mutex:
                                    self.getUserContext()._frame     = None
                                    self.getUserContext()._raw_image = res[1]["image"]
                                    self._input_seq += 1

                        except:
                            debug_exc("TrendCarSimulatorModel: json data error")

                        return

                    debug("TrendCarSimulatorModel: unhandled message received '%s'", msg)


                def handleConnected(self):
                    debug("TrendCarSimulatorModel: simulator connected")

                    self._input_seq  = 0
                    self._output_seq = 0

                    try:
                        self.getUserContext()._simulators.append(self)

                        import random
                        self.sendMessage(r"""0{"pingInterval":25000,"pingTimeout":60000,"upgrades":[],"sid":"%x"}""" % (random.getrandbits(64)), True)
                        if not self.getUserContext()._first_connected:
                            self.sendMessage(r"""42["restart",{}]""", True)
                            self.getUserContext()._first_connected = True

                        self._drive(0.0, 0.0)
                        self.sendMessage(r"""40""", True)
                    except:
                        debug_exc("error")


                def handleClose(self):
                    try:
                        self.getUserContext()._simulators.remove(self)
                        self._input_seq  = -1
                        self._output_seq = -1

                        debug("TrendCarSimulatorModel: simulator closed")
                    except:
                        debug_exc("error")

            self._websocket       = SimpleWebSocketServer('', 4567, TrendCarSimulatorAdapter, self)
            self._is_running      = True
            self._first_connected = False

            if hwinfo.is_running_in_pi():
                allow_incoming_ipv4_tcp(4567)

            def websocket_receiving_loop():
                set_thread_name("websocket-recv")
                debug("TrendCarSimulatorModel: websocket_receiving_loop started")

                try:
                    while self._is_running:
                        self._websocket.serve_receiving_once()
                except:
                    debug_exc("TrendCarSimulatorModel: exception occurred at websocket_receiving_loop")

                self._is_running = False
                debug("TrendCarSimulatorModel: websocket_receiving_loop exited")

            def websocket_sending_loop():
                set_thread_name("websocket-send")
                debug("TrendCarSimulatorModel: websocket_sending_loop started")

                try:
                    while self._is_running:
                        self._websocket.serve_sending_once()
                except:
                    debug_exc("TrendCarSimulatorModel: exception occurred at websocket_sending_loop")

                self._is_running = False
                debug("TrendCarSimulatorModel: websocket_sending_loop exited")

            self._websocket_recv_thread = threading.Thread(target = websocket_receiving_loop)
            self._websocket_recv_thread.setDaemon(True)
            self._websocket_recv_thread.start()
            self._websocket_send_thread = threading.Thread(target = websocket_sending_loop)
            self._websocket_send_thread.setDaemon(True)
            self._websocket_send_thread.start()
            return True

        except:
            self._is_running      = False
            self._first_connected = False

            if self._websocket is not None:
                try:
                    self._websocket.close()
                except:
                    pass
                self._websocket = None

            self._simulators = []

            if is_detecting:
                debug_exc("TrendCarSimulatorModel: Unable to setup") 
            else:
                warn_exc("TrendCarSimulatorModel: Unable to setup")

        return False


    def end(self):
        self._is_running      = False
        self._first_connected = False

        if self._websocket is not None:
            try:
                self._websocket.close()
            except:
                pass
            self._websocket = None

        self._simulators = []
        return True


    def vibrate(self, count, interval = 0):
        return False


    def drive_by_pwms(self, front_left_pwm, rear_left_pwm, front_right_pwm, rear_right_pwm, duration = 0.0):
        if len(self._simulators) == 0:
            return False

        warn("TrendCarSimulatorModel: drive_by_pwms was not supported by simulator")
        return False


    def drive(self, steering, throttle, duration = 0.0, flipped = False):
        if len(self._simulators) == 0:
            return False

        for simulator in self._simulators:
            simulator._drive(steering, throttle)

        return True


    def get_snapshot(self, ndx = None):
        with self._mutex:
            if self._raw_image is None:
                frame_width  = self.get_frame_width()
                frame_height = self.get_frame_height()
                self._frame  = np.zeros((frame_height, frame_width, 3), np.uint8)
            elif self._frame is None:
                import base64
                from PIL import Image
                from io  import BytesIO
                self._frame = imgutils.rgb2bgr(np.asarray(Image.open(BytesIO(base64.b64decode(self._raw_image)))))

            if ndx is None:
                return [self._frame]

            if ndx == 0:
                return self._frame

        warn("TrendCarSimulatorModel: Unable to retrieve the image frame from camera[%d] because index was out of bound.", ndx)
        return None


    def ready_to_go(self):
        return len(self._simulators) > 0

