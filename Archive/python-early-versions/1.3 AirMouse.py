import cv2
import mediapipe as mp
import pyautogui

# 初始化MediaPipe手部追踪模块
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 摄像头初始化
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        continue

    # 获取摄像头帧的宽度和高度
    frame_height, frame_width, _ = frame.shape

    # 将图像转换为RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 处理手部追踪
    results = hands.process(rgb_frame)

    # 如果检测到手部
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # 绘制手部关键点
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 获取中指MCP的坐标
            middle_finger_mcp = hand_landmarks.landmark[9]
            # 原始归一化坐标
            norm_x = middle_finger_mcp.x
            norm_y = middle_finger_mcp.y

            # 将中指MCP的归一化坐标映射到屏幕坐标
            x = int((1 - norm_x) * screen_width)  # 反转x坐标
            y = int(norm_y * screen_height)

            # 鼠标移动
            pyautogui.moveTo(x, y)

    # 显示图像
    cv2.imshow('Air Mouse', frame)

    # 退出条件
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头资源
cap.release()
cv2.destroyAllWindows()