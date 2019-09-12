import cv2
import numpy as np
from starter_cnn import detect_go
#
idetect = detect_go(cnn_model_path = './go_models/go_cnn_64_v12_lite.h5',\
                    min_image_cnt = 5, \
                    min_detection_mul=1)
#
try:
  cam.release()
except: pass
#
cam = cv2.VideoCapture(1)
cam.set(cv2.CAP_PROP_FRAME_WIDTH , 320)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
cam.set(cv2.CAP_PROP_FPS         , 30)
#
def get_roi_mask(f, cut_upper=True):
  shape = f.shape
  if cut_upper:
    upper_f = f.astype(np.uint8)[:shape[0]*2//5,:]
  else: upper_f = f.astype(np.uint8).copy()
  _tmp_hsv = cv2.cvtColor(upper_f.astype(np.uint8), cv2.COLOR_BGR2HSV)
  mask1 = cv2.inRange(_tmp_hsv, np.array([0, 70, 100]), np.array([10, 255, 255]))
  mask2 = cv2.inRange(_tmp_hsv, np.array([170, 70, 100]), np.array([180, 255, 255]))
  mask_sum = cv2.add(mask1,mask2)
  roi = cv2.bitwise_and(upper_f,upper_f, mask= mask_sum)
  return mask_sum, roi
#
while True:
  try:
    ret, frame = cam.read()
  except: continue
  #
  d, rect = idetect.detect(frame)
  #
  mask, roi = get_roi_mask(frame)
  cv2.imshow('Frame_Origin', frame)
  #try:
  combined = np.concatenate((cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR), roi), axis=1)
  cv2.imshow('Mask', combined)
  #except: pass
  if d is True:
    print 'Go detected!'
    for top,bot,left,right in rect:
      cv2.rectangle(frame, (left, top), (right, bot), (255,0,0), 2)
  #
  cv2.imshow('Frame', frame)
  key  = cv2.waitKey(1)
  if key == ord('q'): break
#
