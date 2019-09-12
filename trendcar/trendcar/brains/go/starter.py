from __future__ import print_function
from __future__ import division

import cv2
import numpy as np
from .GOCNN import CNN
from collections import deque
from sys import version
#
if version > '3':
    from functools import reduce
#
class detect_go:
  def get_roi_mask(self, f, cut_upper=True):
    shape = f.shape
    if cut_upper:
      upper_f = f.astype(np.uint8)[:shape[0]*2//5,:]
    else: upper_f = f.astype(np.uint8).copy()
    _tmp_hsv = cv2.cvtColor(upper_f.astype(np.uint8), cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(_tmp_hsv, np.array([10, 70, 50]), np.array([20, 255, 255]))
    mask2 = cv2.inRange(_tmp_hsv, np.array([170, 70, 50]), np.array([180, 255, 255]))
    mask_sum = cv2.add(mask1,mask2)
    roi = cv2.bitwise_and(upper_f,upper_f, mask= mask_sum)
    return mask_sum, roi
  #
  def msg_print(self, msg):
    print('[Go Detection] {}'.format(msg))
  #
  def detect(self,img):


    # Make sure the incoming image is good.
    if img is None: return False, []
    if img.shape[0] == 0 or img.shape[1] == 0: return False, []
    self.img_queue.append(img)

    # Averaging images
    f = self.img_queue[0].astype(np.float32)
    for i,x in enumerate(list(self.img_queue)[1:]):
      f += x.astype(np.float32)
    f/=len(self.img_queue)
    f = f.astype(np.uint8)

    # Get Red color space
    mask, roi = self.get_roi_mask(f, True)
    img_patches, img_rect = [], []
    _h,_w,_c = roi.shape
    for wi, window in enumerate(self.window_size):
      for h in range(0, _h - window[0], self.stride[wi][0]):
        for w in range(0, _w - window[1], self.stride[wi][1]):
          _bottom, _right = h+window[0], w+window[1]
          mask_patch = mask[h:_bottom, w:_right]
          shape = mask_patch.shape
          if shape[0]==0 or shape[1]==0: continue
          img_patch = f[h:_bottom, w:_right]
          _roi_ratio = np.count_nonzero(mask_patch)/reduce(lambda x,y: x*y,shape,1.0)
          if _roi_ratio > self.roi_ratio[0] and _roi_ratio < self.roi_ratio[1]:
            if img_patch.shape[0] == window[0] and img_patch.shape[1] == window[1]:
              img_patches.append(img_patch)
              img_rect.append((h,_bottom,w,_right))    
    # 
    try:
      if len(img_patches)!=0:
        pred_prob = self.cnn.batch_predict(img_patches)
        positive_candidates = [list(filter(lambda x: x[1][1]>0.95 ,enumerate(pred_prob)))]
        positive_position = list(map(lambda x: img_rect[x[0]],filter(lambda x: x[1][1]>0.95 ,enumerate(pred_prob))))
      else: return False, img_rect
    except Exception as e:
      self.msg_print('Fail to do CNN prediction, reason: {}'.format(str(e)))
      return False, img_rect
    #
    self.detection_cnt.append(len(positive_candidates[0]))
    #
    _acc = np.sum(self.detection_cnt)
    if _acc > self.MINIMUM_ACCU_NUM_OF_DETECTION:
      self.msg_print('Detect GO num#{}'.format(_acc))
      return True, positive_position
    return False, img_rect
  #
  def __init__(self, \
               cnn_model_path = './go_models/go_cnn_32.h5',\
               min_image_cnt = 5,\
               min_detection_cnt = 10,\
               min_detection_mul = 2):
    #
    try:
      self.cnn = CNN()
      self.msg_print('Loading "GO" CNN model...')
      self.cnn.load_model(cnn_model_path)
      self.msg_print('Done')
    except Exception as e:
      self.msg_print('Fail to load CNN model... Initialization failed')
      self.msg_print('Error message: {}'.format(str(e)))
      self.clf = None
    #
    #
    self.window_size = [(20,40)] # (Height, Width)
    self.stride = [(5,5)]            # Sliding Window stride
    self.roi_ratio = (0.05, 0.5)                 # ROI Ratio
    self.detection_cnt = deque([], min_image_cnt)  # List of detection count.
    self.MINIMUM_IMAGE_QUEUE_SIZE = min_image_cnt  # Minimum number of images required 
    self.img_queue = deque([], self.MINIMUM_IMAGE_QUEUE_SIZE)
    self.MINIMUM_ACCU_NUM_OF_DETECTION = min_image_cnt*min_detection_mul # Number of multiplier to calculate the minimum count of detection
    
#
