import cv2
import mediapipe as mp
import pyautogui

# 初始化 MediaPipe 手部追踪模块
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 屏幕分辨率与扩展比例
screen_width, screen_height = pyautogui.size()
extend_ratio_x = 2
extend_ratio_y = 2

# 初始化平滑历史窗口
history = []
window_size = 3

def smooth_coordinates(history):
    """对历史窗口内的坐标进行平滑处理"""
    if history:
        avg_x = sum(x for x, y in history) / len(history)
        avg_y = sum(y for x, y in history) / len(history)
        return avg_x, avg_y
    return None, None

# 打开摄像头
cap = cv2.VideoCapture(1)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # 降低分辨率并转换为 RGB
    frame_height, frame_width, _ = frame.shape
    frame = cv2.resize(frame, (frame_width // 2, frame_height // 2))
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 检测手部
    results = hands.process(rgb_frame)
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 计算几何中心
            norm_x = sum(hand_landmarks.landmark[i].x for i in [0, 5, 17]) / 3
            norm_y = sum(hand_landmarks.landmark[i].y for i in [0, 5, 17]) / 3

            # 映射并扩展手部坐标
            extended_x = max(0, min(1, (norm_x - 0.5) * extend_ratio_x + 0.5))
            extended_y = max(0, min(1, (norm_y - 0.5) * extend_ratio_y + 0.5))

            # 转换为屏幕坐标
            x = int((1 - extended_x) * screen_width)
            y = int(extended_y * screen_height)

            # 平滑鼠标移动
            history.append((x, y))
            if len(history) > window_size:
                history.pop(0)
            smooth_x, smooth_y = smooth_coordinates(history)

            # 控制鼠标
            if smooth_x is not None and smooth_y is not None:
                pyautogui.moveTo(smooth_x, smooth_y)

    # 镜像显示摄像头画面
    cv2.imshow('Air Mouse', cv2.flip(frame, 1))

    # 按 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()