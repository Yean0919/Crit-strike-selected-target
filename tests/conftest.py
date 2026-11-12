import cv2
import numpy as np
import pytest


@pytest.fixture
def avatar():
    image = np.full((160, 160, 3), (55, 92, 145), dtype=np.uint8)
    cv2.circle(image, (77, 76), 55, (190, 220, 50), -1)
    cv2.rectangle(image, (37, 42), (64, 68), (30, 30, 60), -1)
    cv2.circle(image, (103, 60), 14, (220, 70, 110), -1)
    cv2.line(image, (50, 113), (113, 89), (70, 20, 230), 10)
    cv2.putText(image, "K", (66, 99), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    return image
