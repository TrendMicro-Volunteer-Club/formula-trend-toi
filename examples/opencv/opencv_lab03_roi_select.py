import cv2
import numpy as np

if __name__ == '__main__':
    img = cv2.imread('image_sample_05.png')
    img_roi = img[120:, :, :]

    cv2.namedWindow('sample')
    cv2.imshow('sample', img_roi)
    cv2.waitKey()
