import cv2
import mediapipe as mp
import pyautogui
import time
import os

# 初始化MediaPipe的手部追踪模块
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 打开摄像头
cap = cv2.VideoCapture(0)

# 定义一个阈值来判断手指是否捏合
THUMB_INDEX_THRESHOLD = 40  # 捏合阈值（像素）

def calculate_distance(landmark1, landmark2, width, height):
    """计算两个关键点之间的像素距离"""
    x1, y1 = int(landmark1.x * width), int(landmark1.y * height)
    x2, y2 = int(landmark2.x * width), int(landmark2.y * height)
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

while True:
    # 获取摄像头帧
    ret, frame = cap.read()
    if not ret:
        print("Error: Failed to capture image.")
        break
    
    # 获取帧的宽度和高度
    height, width, _ = frame.shape

    # 将图像从BGR转为RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 处理图像并检测手部关键点
    results = hands.process(rgb_frame)
    
    # 如果检测到手部
    if results.multi_hand_landmarks:
        for landmarks in results.multi_hand_landmarks:
            # 计算拇指和食指之间的距离
            thumb_tip = landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            distance = calculate_distance(thumb_tip, index_tip, width, height)

            # 绘制每个关键点
            for landmark in landmarks.landmark:
                cx, cy = int(landmark.x * width), int(landmark.y * height)
                cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
            
            # 绘制手部关节连线
            mp_drawing.draw_landmarks(frame, landmarks, mp_hands.HAND_CONNECTIONS)

    # 镜像显示
    frame = cv2.flip(frame, 1)

    # 显示图像
    cv2.imshow('Hand Tracking - Mirror', frame)
    
    # 按 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头并关闭窗口
cap.release()
cv2.destroyAllWindows()