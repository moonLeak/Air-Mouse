import cv2
import mediapipe as mp
import pyautogui
import math
import time
import statistics
import numpy as np

# MediaPipe手部追踪模块配置
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.3)
mp_drawing = mp.solutions.drawing_utils

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 摄像头初始化
cap = cv2.VideoCapture(1)

# 参数设置
extend_ratio_x, extend_ratio_y = 2.5, 2.5  # 手部范围扩展比例
click_threshold_4to8, click_threshold_4to12 = 0.05, 0.05  # 单击阈值
scroll_threshold = 0.05  # 滚动阈值
scroll_inertia_decay, scroll_smoothness = 0.95, 0.01  # 滚动惯性参数
window_size = 3  # 初始平滑窗口大小
hand_moving_speed_therhold = 200 #window_size改变的临界值
mouse_update_interval = 0.05  # 设置鼠标更新间隔时间，防止频繁更新

# 鼠标状态变量
is_clicking_4to8, is_clicking_4to12 = False, False  # 单击状态
is_scrolling, scroll_speed, initial_y = False, 0, None  # 滚动状态和惯性参数
history = []  # 存储平滑移动的历史坐标

# 工具函数
def calculate_distance(point1, point2):
    """计算两点的欧几里得距离"""
    if isinstance(point1, tuple) and isinstance(point2, tuple):
        return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)
    elif hasattr(point1, 'x') and hasattr(point2, 'x'):
        return math.sqrt((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2)
    else:
        raise ValueError("Invalid point type for distance calculation")
    
# 定义卡尔曼滤波器类
class KalmanFilter:
    def __init__(self):
        self.dt = 1.0  # 时间间隔
        self.A = np.array([[1, self.dt], [0, 1]])  # 状态转移矩阵
        self.H = np.array([[1, 0]])  # 观测矩阵
        self.Q = np.array([[1, 0], [0, 3]])  # 过程噪声协方差
        self.R = np.array([[10]])  # 观测噪声协方差
        self.P = np.eye(2)  # 初始协方差矩阵
        self.x = np.zeros((2, 1))  # 初始状态向量

    def update(self, z):
        # 预测阶段
        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q

        # 更新阶段
        K = self.P @ self.H.T @ np.linalg.inv(self.H @ self.P @ self.H.T + self.R)
        self.x = self.x + K @ (z - self.H @ self.x)
        self.P = (np.eye(2) - K @ self.H) @ self.P

        return self.x[0, 0]  # 返回位置

# 定义处理手部运动的函数
def process_hand_movement(hand_landmarks, kalman_filter_x, kalman_filter_y, extend_ratio_x, extend_ratio_y):
    # 计算手掌心的几何中心（归一化坐标）
    x_values_trimmed = sorted([hand_landmarks.landmark[i].x for i in [0, 5, 9, 13, 17]])[1:-1]
    y_values_trimmed = sorted([hand_landmarks.landmark[i].y for i in [0, 5, 9, 13, 17]])[1:-1]
    weights = [3, 2, 1, 1, 1]  # 加权平均权重
    norm_x = sum(x * w for x, w in zip(x_values_trimmed, weights[1:-1])) / sum(weights[1:-1])
    norm_y = sum(y * w for y, w in zip(y_values_trimmed, weights[1:-1])) / sum(weights[1:-1])

    # 扩展坐标范围
    extended_x = max(0, min(1, (norm_x - 0.5) * extend_ratio_x + 0.5))
    extended_y = max(0, min(1, (norm_y - 0.5) * extend_ratio_y + 0.5))

    # 映射到屏幕坐标
    x = int((1 - extended_x) * screen_width)  # 反转x坐标
    y = int(extended_y * screen_height)

    # 使用卡尔曼滤波器平滑坐标
    smooth_x = kalman_filter_x.update(x)
    smooth_y = kalman_filter_y.update(y)

    return int(smooth_x), int(smooth_y)

def perform_left_click(distance, threshold, clicking_state):
    """左键单击和拖动"""
    if distance < threshold:
        if not clicking_state[0]:
            pyautogui.click()
            clicking_state[0] = True
    else:
        if clicking_state[0]:
            clicking_state[0] = False

def perform_right_click(distance, threshold, clicking_state):
    """右键单击"""
    if distance < threshold and not clicking_state[0]:
        pyautogui.click(button='right')
        clicking_state[0] = True
    elif distance >= threshold:
        clicking_state[0] = False

def perform_scrolling(ring_finger_tip, initial_y, scroll_state, smoothness, decay):
    """滚动和惯性滚动"""
    if scroll_state["active"]:
        current_y = ring_finger_tip.y
        scroll_delta = (initial_y - current_y) * 100
        scroll_state["speed"] = scroll_delta
        pyautogui.scroll(-int(scroll_delta))
        scroll_state["initial_y"] = current_y
    else:
        if abs(scroll_state["speed"]) > 1:
            pyautogui.scroll(-int(scroll_state["speed"] * smoothness))
            scroll_state["speed"] *= decay

# 主循环
last_update_time = time.time()  # 上次鼠标位置更新时间
previous_position = None  # 开始之前清空鼠标位置
kalman_filter_x = KalmanFilter()
kalman_filter_y = KalmanFilter()

# 主循环
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        continue

    # 转换分辨率和颜色
    frame = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 使用MediaPipe处理图像
    results = hands.process(rgb_frame)
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            
            thumb_tip = hand_landmarks.landmark[4]
            index_finger_tip = hand_landmarks.landmark[8]
            middle_finger_tip = hand_landmarks.landmark[12]
            ring_finger_tip = hand_landmarks.landmark[16]
            
            # 处理手部运动并计算平滑坐标
            smooth_x, smooth_y = process_hand_movement(
                hand_landmarks,
                kalman_filter_x,
                kalman_filter_y,
                extend_ratio_x,
                extend_ratio_y
            )

            # 更新鼠标位置
            pyautogui.moveTo(smooth_x, smooth_y)
            previous_position = (smooth_x, smooth_y)
            
            # 指尖距离计算
            distance_4to8 = calculate_distance(thumb_tip, index_finger_tip)
            distance_4to12 = calculate_distance(thumb_tip, middle_finger_tip)

            # 左键操作
            perform_left_click(distance_4to8, click_threshold_4to8, [is_clicking_4to8])

            # 右键操作
            perform_right_click(distance_4to12, click_threshold_4to12, [is_clicking_4to12])

            # 滚动操作
            if calculate_distance(thumb_tip, ring_finger_tip) < scroll_threshold:
                if not is_scrolling:
                    is_scrolling = True
                    initial_y = ring_finger_tip.y
                    scroll_speed = 0
                else:
                    perform_scrolling(ring_finger_tip, initial_y, {"active": is_scrolling, "speed": scroll_speed, "initial_y": initial_y}, scroll_smoothness, scroll_inertia_decay)
            else:
                is_scrolling = False

    frame = cv2.flip(frame, 1)
    cv2.imshow("Air Mouse", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()