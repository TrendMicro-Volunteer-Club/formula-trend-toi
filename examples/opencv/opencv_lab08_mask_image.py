import cv2
import numpy as np

img = cv2.imread('image_sample_04.png')
mask = np.zeros(shape=img.shape, dtype=bool)

# 偶數列全部為真
for i in range(0, 240, 2):
    mask[i, :, :] = True

# 符合遮罩的位置全部變白色
img[mask] = 255

cv2.namedWindow('masked')
cv2.imshow('masked', img)
cv2.waitKey()