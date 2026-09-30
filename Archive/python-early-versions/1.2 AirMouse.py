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
     # 捕获帧并降低分辨率
    ret, frame = cap.read()
    if not ret:
        continue

    # 获取原始分辨率
    frame_height, frame_width, _ = frame.shape

    # 降低分辨率（宽高减半）
    frame = cv2.resize(frame, (frame_width // 2, frame_height // 2))

    # 转换颜色
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 使用 MediaPipe 处理
    results = hands.process(rgb_frame)

    # 如果检测到手部
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:

            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 获取手指关节的坐标
            middle_finger_mcp = hand_landmarks.landmark[9]
            wrist = hand_landmarks.landmark[0]
            index_finger_tip = hand_landmarks.landmark[8]

            # 原始归一化坐标
            target_finger = index_finger_tip
            norm_x = target_finger.x
            norm_y = target_finger.y

            # 将中指MCP的归一化坐标映射到屏幕坐标
            x = int((1 - norm_x) * screen_width)  # 反转x坐标
            y = int(norm_y * screen_height)

            # 鼠标移动
            pyautogui.moveTo(x, y)
            
    # 镜像显示
    frame = cv2.flip(frame, 1)
    # 显示图像
    cv2.imshow('Air Mouse', frame)

    # 退出条件
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头资源
cap.release()
cv2.destroyAllWindows()