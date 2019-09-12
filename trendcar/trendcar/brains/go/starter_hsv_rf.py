import os
import cv2
import numpy as np
from collections import deque
from sys import version
from time import time
from pickle import load
#
#
class detect_go:
  #
  def generate_hsv_hist_fea(self,hsv_img, hsv_hist_bins = [18,8,10]):
    hist_hsv = map(lambda x: cv2.calcHist([hsv_img],[x[0]],None,[x[1]],[0,256]),enumerate(hsv_hist_bins))
    return np.vstack(hist_hsv)
  #
  def get_roi_mask(self, f, cut_upper=True):
    shape = f.shape
    if cut_upper:
      upper_f = f.astype(np.uint8)[:shape[0]*1//2,:]
    else: upper_f = f.astype(np.uint8).copy()
    _tmp_hsv = cv2.cvtColor(upper_f.astype(np.uint8), cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(_tmp_hsv, np.array([0, 70, 100]), np.array([15, 255, 255]))
    mask2 = cv2.inRange(_tmp_hsv, np.array([170, 70, 100]), np.array([180, 255, 255]))
    mask_sum = cv2.add(mask1,mask2)
    roi = cv2.bitwise_and(upper_f,upper_f, mask= mask_sum)
    return mask_sum, roi, _tmp_hsv
  #
  def msg_print(self, msg):
    print('[Go Detection] {}'.format(msg))
  #
  def detect(self,img):

    # Make sure the incoming image is good.
    if img is None: return False, []
    if img.shape[0] == 0 or img.shape[1] == 0: return False, []
    self.img_queue.append(img)

    # If image queue are not full then force skipping current frame.
    if len(self.img_queue)<self.MINIMUM_IMAGE_QUEUE_SIZE:
      return False, []

    # Averaging images
    f = self.img_queue[0].astype(np.float32)
    for i,x in enumerate(list(self.img_queue)[1:]):
      f += x.astype(np.float32)
    f/=len(self.img_queue)
    f = f.astype(np.uint8)

    # Frame differencing
    _h, _w, _c = f.shape
    _diff = np.abs(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)[:int(_h*1/2)].astype(np.float32) - \
                   cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)[:int(_h*1/2)].astype(np.float32)).astype(np.uint8)
    _diff_d = np.sum(_diff)/float(_diff.shape[0]*_diff.shape[1]*256)
    
    # 5% of pixel intensity are greater than before
    if _diff_d > 0.05:  
      self.img_queue.clear()
      return False, [] 

    # Get Red color space
    mask, roi, hsv_space = self.get_roi_mask(f, True)
    img_patches, img_rect = [], []
    _h,_w,_c = roi.shape
    for wi, window in enumerate(self.window_size):
      for h in range(0, _h - window[0], self.stride[wi][0]):
        for w in range(0, _w - window[1], self.stride[wi][1]):
          _bottom, _right = h+window[0], w+window[1]
          mask_patch = mask[h:_bottom, w:_right]
          shape = mask_patch.shape
          if shape[0]==0 or shape[1]==0: continue
          img_patch = hsv_space[h:_bottom, w:_right]
          _roi_ratio = np.count_nonzero(mask_patch)/float(shape[0]*shape[1])
          if _roi_ratio > self.roi_ratio[0] and _roi_ratio < self.roi_ratio[1]:
            if img_patch.shape[0] == window[0] and img_patch.shape[1] == window[1]:
              img_patches.append(img_patch)
              img_rect.append((h,_bottom,w,_right))    
    # 
    margin = 2
    dbl_margin = margin * 2
    real_candidates = []
    try:
      if len(img_patches)!=0:
        features = np.vstack(map(lambda x: self.generate_hsv_hist_fea(x).transpose(), img_patches))
        pred_prob = self.clf.predict_proba(features)

        positive_candidates = [list(filter(lambda x: x[1][0]>=0.9 ,enumerate(pred_prob)))]
        positive_position = list(map(lambda x: img_rect[x[0]],filter(lambda x: x[1][0]>=0.9 ,enumerate(pred_prob))))

        # 2nd verification for positive candidates
        real_candidates = []
        for (idx, prob) in positive_candidates[0]:
          _target = cv2.cvtColor(cv2.cvtColor(img_patches[idx], cv2.COLOR_HSV2RGB), cv2.COLOR_RGB2GRAY)
          _h, _w = _target.shape
          mask_area = (_h - dbl_margin) * (_w - dbl_margin)
          boundary_area = _h*_w - mask_area
          _target[margin:_h-margin, margin: _w-margin] = 255
          _boundaries_num = _target[_target < 40].size
          if _boundaries_num/float(boundary_area) >= 0.40:
            real_candidates.append(img_rect[idx])
        #
      else: return False, img_rect
    except Exception as e:
      self.msg_print('Fail to do model inference, reason: {}'.format(str(e)))
      return False, img_rect
    #
    self.detection_cnt.append(len(real_candidates))
    #
    _acc = np.sum(self.detection_cnt)
    if _acc > self.MINIMUM_ACCU_NUM_OF_DETECTION:
      self.msg_print('Detect GO num#{}'.format(_acc))
      return True, real_candidates
    return False, img_rect
  #
  def __init__(self, \
               model_path = './go_models/1.0.8_hsv_hist_rf_32.pkl',\
               min_image_cnt = 2,\
               min_detection_cnt = 15,\
               min_detection_mul = 0.5):
    #
    try:
      self.msg_print('Loading "GO" model...')
      filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), model_path)
      try:
        with open(filepath,'rb') as fp:
          self.clf = load(fp)
      except UnicodeDecodeError:
        with open(filepath,'rb') as fp:
          self.clf = load(fp, encoding='latin1')
      self.msg_print('Done')
    except Exception as e:
      self.msg_print('Fail to load "go" model... Initialization failed')
      self.msg_print('Error message: {}'.format(str(e)))
      self.clf = None
    #
    #
    self.window_size = [(20,40)] # (Height, Width)
    self.stride = [(3,3)]            # Sliding Window stride
    self.roi_ratio = (0.1, 0.6)                 # ROI Ratio
    self.detection_cnt = deque([], min_image_cnt)  # List of detection count.
    self.detected_rect = deque([], min_image_cnt)  # 
    self.MINIMUM_IMAGE_QUEUE_SIZE = min_image_cnt  # Minimum number of images required 
    self.img_queue = deque([], self.MINIMUM_IMAGE_QUEUE_SIZE)
    self.MINIMUM_ACCU_NUM_OF_DETECTION = min_image_cnt*min_detection_mul # Number of multiplier to calculate the minimum count of detection
    
#
