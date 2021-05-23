import cv2
import numpy as np
import pygame


class VideoWriter:
    def __init__(self, output, width, height, fps):
        self.width = width
        self.height = height
        fourcc = cv2.VideoWriter_fourcc(*'DIVX')  # Be sure to use lower case
        self.out = cv2.VideoWriter(output, fourcc, fps, (width, height))

    def export_frame(self, surface):
        frame = pygame.image.tostring(surface, "RGB")
        array = np.frombuffer(frame, dtype=np.uint8)
        array.shape = (self.height, self.width, 3)
        cvt = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
        self.out.write(cvt)

    def close(self):
        self.out.release()