import os
import base64
import logging
import shutil
import argparse

from datetime import datetime
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

import socketio
import eventlet
import eventlet.wsgi
from flask import Flask

class ImageProcessor(object):
    @staticmethod
    def show_image(img, name="image", scale=1.0):
        if scale and scale != 1.0:
            img = cv2.resize(img, newsize, interpolation=cv2.INTER_CUBIC)

        cv2.namedWindow(name, cv2.WINDOW_AUTOSIZE)
        cv2.imshow(name, img)
        cv2.waitKey(1)

    @staticmethod
    def save_image(folder, img, prefix="img", suffix=""):
        
        filename = "%s-%s%s.jpg" % (prefix, datetime.now().strftime('%Y%m%d-%H%M%S-%f'), suffix)
        cv2.imwrite(os.path.join(folder, filename), img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

    @staticmethod
    def rgb2bgr(img):
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    @staticmethod
    def rad2deg(radius):
        return radius / np.pi * 180.0

    @staticmethod
    def deg2rad(degree):
        return degree / 180.0 * np.pi

class AutoDrive(object):
    DEFAULT_SPEED = 0

    debug = True

    def __init__(self, car, record_folder=None):
        self._record_folder = record_folder
        self._car = car
        self._car.register(self)

    def on_dashboard(self, src_img, last_steering_angle, speed, throttle, info):
        steering_angle = 0
        throttle = AutoDrive.DEFAULT_SPEED
        if self.debug:
            ImageProcessor.show_image(src_img, "source")

        if self._record_folder:
            suffix = "-deg%0.3f" % (ImageProcessor.rad2deg(steering_angle))
            ImageProcessor.save_image(self._record_folder, src_img, prefix="cam", suffix=suffix)

        self._car.control(steering_angle, throttle)

class Car(object):
    MAX_STEERING_ANGLE = 40.0

    def __init__(self, control_function):
        self._driver = None
        self._control_function = control_function

    def register(self, driver):
        self._driver = driver

    def on_dashboard(self, dashboard):
        last_steering_angle = np.pi/2 - float(dashboard["steering_angle"]) / 180.0 * np.pi
        throttle = float(dashboard["throttle"])
        brake = float(dashboard["brakes"])
        speed = float(dashboard["speed"])
        img = ImageProcessor.rgb2bgr(np.asarray(Image.open(BytesIO(base64.b64decode(dashboard["image"])))))
        del dashboard["image"]

        elapsed = float(dashboard["time"])
        info = {
            "lap"    : int(dashboard["lap"]) if "lap" in dashboard else 0,
            "elapsed": elapsed,
            "status" : int(dashboard["status"]) if "status" in dashboard else 0,
        }
        print('{} [INFO] lap={}, elapsed={}, throttle={}, speed={}, steering_angle={}'.format(
            datetime.now().strftime('%Y-%m-%d %H:%I:%S.%f'), info['lap'], info['elapsed'], throttle, speed, last_steering_angle
        ))

        self._driver.on_dashboard(img, last_steering_angle, speed, throttle, info)

    def control(self, steering_angle, throttle):
        steering_angle = min(max(ImageProcessor.rad2deg(steering_angle), -Car.MAX_STEERING_ANGLE), Car.MAX_STEERING_ANGLE)
        self._control_function(steering_angle, throttle)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='AutoDriveBot')
    parser.add_argument(
        'record',
        type=str,
        nargs='?',
        default='',
        help='Path to image folder to record the images.'
    )
    args = parser.parse_args()

    if args.record:
        if not os.path.exists(args.record):
            os.makedirs(args.record)
        logit("Start recording images to %s..." % args.record)

    sio = socketio.Server()
    def send_control(steering_angle, throttle):    	  
        sio.emit(
            "steer",
            data={
                'steering_angle': str(steering_angle),
                'throttle': str(throttle)
            },
            skip_sid=True)
                   
    def send_restart():
        sio.emit(
            "restart",
            data={},
            skip_sid=True)

    car = Car(control_function = send_control)
    drive = AutoDrive(car, args.record)

    @sio.on('telemetry')
    def telemetry(sid, dashboard):
        if dashboard:
            car.on_dashboard(dashboard)
        else:
            sio.emit('manual', data={}, skip_sid=True)

    @sio.on('connect')
    def connect(sid, environ):
        send_restart()
        car.control(0, 0)

    app = socketio.Middleware(sio, Flask(__name__))
    eventlet.wsgi.server(eventlet.listen(('', 4567)), app)

