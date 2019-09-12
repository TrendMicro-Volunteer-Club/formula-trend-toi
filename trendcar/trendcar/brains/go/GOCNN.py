import os,sys
import cv2
import numpy as np
from tensorflow.keras.models import load_model 
#
class CNN:
  def msg_print(self, msg):
    sys.stderr.write('[CNN4GO] {}\n'.format(msg))
  #
  def __init__(self, model_path=None):
    if model_path is not None:
      self.load_model(model_path)
  #
  def load_model(self,model_path):
    try:
      self.model = load_model(model_path)
      self.msg_print('Model loaded')
      return True
    except Exception as e:
      self.msg_print('Unable to load model:"{}", reason:{}'.format(\
          model_path, str(e)))
      return False 
  #
  def batch_predict(self,image_samples):
    normalized = np.array(image_samples, dtype=np.float32)/255
    return self.model.predict_proba(normalized)
  #
  def predict(self, image_sample):
    normalized = np.array(image_sample, dtype=np.float32, ndmin=4)/255
    return self.model.predict_proba(normalized)
