import cv2
import numpy as np

if __name__ == '__main__':
    img = cv2.imread('image_sample_01.png')

    cv2.namedWindow('sample')
    cv2.imshow('sample', img)
    cv2.waitKey()
