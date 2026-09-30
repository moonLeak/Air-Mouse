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

# 初始化平滑坐标的历史窗口
history = []
window_size = 3  # 滑动窗口大小

def calculate_smooth_coordinates(history, window_size):
    """根据滑动窗口对坐标进行平滑处理 """
    if len(history) > 0:
        avg_x = sum(x for x, y in history) / len(history)
        avg_y = sum(y for x, y in history) / len(history)
        return avg_x, avg_y
    return None, None

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

            # 获取用于计算几何中心的关节
            wrist = hand_landmarks.landmark[0]
            index_mcp = hand_landmarks.landmark[5]
            pinky_mcp = hand_landmarks.landmark[17]

            # 计算几何中心
            norm_x = (wrist.x + index_mcp.x + pinky_mcp.x) / 3
            norm_y = (wrist.y + index_mcp.y + pinky_mcp.y) / 3

            # 将归一化坐标映射到屏幕坐标
            x = int((1 - norm_x) * screen_width)  # 反转x坐标
            y = int(norm_y * screen_height)

            # 添加到滑动窗口
            history.append((x, y))
            if len(history) > window_size:
                history.pop(0)

            # 平滑处理坐标
            smooth_x, smooth_y = calculate_smooth_coordinates(history, window_size)

            # 鼠标移动
            if smooth_x is not None and smooth_y is not None:
                pyautogui.moveTo(smooth_x, smooth_y)

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