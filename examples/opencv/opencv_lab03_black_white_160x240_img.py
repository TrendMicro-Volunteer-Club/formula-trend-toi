import cv2
import numpy as np

if __name__ == '__main__':
    img = np.ones(shape=(160, 240, 3), dtype='uint8')*255

    img[80:, :, :,] = (0, 0, 0)

    cv2.namedWindow('sample')
    cv2.imshow('sample', img)
    cv2.waitKey()
