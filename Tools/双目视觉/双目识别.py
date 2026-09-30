import cv2
import mediapipe as mp
import numpy as np
import pyautogui
import time

# 加载标定参数
params = np.load("camera_params.npz")
mtx1, dist1 = params['mtx1'], params['dist1']
mtx2, dist2 = params['mtx2'], params['dist2']
R, T = params['R'], params['T']

# 初始化MediaPipe的手部追踪模块
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 打开两台摄像头
cap1 = cv2.VideoCapture(0)  # 第一台摄像头（正前方）
cap2 = cv2.VideoCapture(1)  # 第二台摄像头（正右方）

# 等待摄像头初始化
time.sleep(2)

# 计算像素距离
def calculate_distance(landmark1, landmark2, width, height):
    """计算两个关键点之间的像素距离"""
    x1, y1 = int(landmark1.x * width), int(landmark1.y * height)
    x2, y2 = int(landmark2.x * width), int(landmark2.y * height)
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

while True:
    # 获取两台摄像头帧
    ret1, frame1 = cap1.read()
    ret2, frame2 = cap2.read()

    if not ret1 or not ret2:
        print("Error: Unable to capture images from cameras.")
        break

    # 将图像从BGR转为RGB
    rgb_frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
    rgb_frame2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)
    
    # 处理图像并检测手部关键点
    results1 = hands.process(rgb_frame1)
    results2 = hands.process(rgb_frame2)
    
    # 如果检测到手部
    if results1.multi_hand_landmarks:
        for landmarks in results1.multi_hand_landmarks:
            # 计算拇指和食指之间的距离
            thumb_tip = landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            distance1 = calculate_distance(thumb_tip, index_tip, frame1.shape[1], frame1.shape[0])

            # 绘制每个关键点
            for landmark in landmarks.landmark:
                cx, cy = int(landmark.x * frame1.shape[1]), int(landmark.y * frame1.shape[0])
                cv2.circle(frame1, (cx, cy), 5, (0, 255, 0), -1)
            
            # 绘制手部关节连线
            mp_drawing.draw_landmarks(frame1, landmarks, mp_hands.HAND_CONNECTIONS)

    if results2.multi_hand_landmarks:
        for landmarks in results2.multi_hand_landmarks:
            # 计算拇指和食指之间的距离
            thumb_tip = landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            distance2 = calculate_distance(thumb_tip, index_tip, frame2.shape[1], frame2.shape[0])

            # 绘制每个关键点
            for landmark in landmarks.landmark:
                cx, cy = int(landmark.x * frame2.shape[1]), int(landmark.y * frame2.shape[0])
                cv2.circle(frame2, (cx, cy), 5, (0, 255, 0), -1)
            
            # 绘制手部关节连线
            mp_drawing.draw_landmarks(frame2, landmarks, mp_hands.HAND_CONNECTIONS)

    # 双目匹配：计算立体匹配，获取3D坐标（简化处理）
    if results1.multi_hand_landmarks and results2.multi_hand_landmarks:
        # 假设我们只处理第一只手
        landmarks1 = results1.multi_hand_landmarks[0]
        landmarks2 = results2.multi_hand_landmarks[0]
        
        # 将2D关键点映射为3D坐标（简化处理，实际中可以用立体视觉计算）
        # 这里只是展示如何获取两个摄像头的坐标
        thumb_tip1 = landmarks1.landmark[mp_hands.HandLandmark.THUMB_TIP]
        index_tip1 = landmarks1.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
        
        thumb_tip2 = landmarks2.landmark[mp_hands.HandLandmark.THUMB_TIP]
        index_tip2 = landmarks2.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]

        # 计算两个摄像头的2D坐标（简化处理，假设已对齐）
        x1, y1 = int(thumb_tip1.x * frame1.shape[1]), int(thumb_tip1.y * frame1.shape[0])
        x2, y2 = int(thumb_tip2.x * frame2.shape[1]), int(thumb_tip2.y * frame2.shape[0])

        # 双目三角测量算法可以使用`cv2.triangulatePoints`，这里使用一个简化的方法。
        # 计算差异来估算3D坐标
        diff_x = x1 - x2
        diff_y = y1 - y2

        # 计算距离（简单估算）
        depth = np.sqrt(diff_x ** 2 + diff_y ** 2)
        print(f"Depth estimate: {depth} pixels")

    # 镜像显示
    frame1 = cv2.flip(frame1, 1)
    frame2 = cv2.flip(frame2, 1)

    # 显示图像
    cv2.imshow('Hand Tracking - Camera 1', frame1)
    cv2.imshow('Hand Tracking - Camera 2', frame2)
    
    # 按 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头并关闭窗口
cap1.release()
cap2.release()
cv2.destroyAllWindows()