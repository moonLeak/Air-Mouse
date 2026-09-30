import cv2
import mediapipe as mp
import pyautogui
import math
import time
import statistics

# MediaPipe手部追踪模块配置
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5, min_tracking_confidence=0.3)
mp_drawing = mp.solutions.drawing_utils

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 摄像头初始化
cap = cv2.VideoCapture(1)

# 参数设置
extend_ratio_x, extend_ratio_y = 3, 3  # 手部范围扩展比例
click_threshold_4to8, click_threshold_4to12 = 0.05, 0.05  # 单击阈值
scroll_threshold = 0.05  # 滚动阈值
scroll_inertia_decay, scroll_smoothness = 0.95, 0.01  # 滚动惯性参数
window_size = 1  # 初始平滑窗口大小
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

def process_hand_movement(hand_landmarks, history, extend_ratio_x, extend_ratio_y, window_size, previous_position, mouse_update_interval):
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

    # 添加到历史记录
    history.append((x, y))
    if len(history) > 10:
        history.pop(0)

    # 使用指数加权移动平均（Exponential Moving Average）来平滑坐标
    smooth_x, smooth_y = x, y
    if len(history) > 0:
        smooth_x = sum(coord[0] for coord in history) / len(history)
        smooth_y = sum(coord[1] for coord in history) / len(history)

    # 根据速度调整window_size
    if previous_position:
        distance = calculate_distance(previous_position, (smooth_x, smooth_y))
        speed = distance / mouse_update_interval

        # 使用if-else逻辑调整window_size
        if speed > 200:  # 速度大于200时，减小window_size
            window_size = max(1, window_size - 1)  # 最小值为1
        else:  # 速度小于等于200时，增大window_size
            window_size = min(10, window_size + 1)  # 最大值为10

        # 在终端显示当前的window_size和速度
        print(f"Current window_size: {window_size}  Speed: {speed}")
    return smooth_x, smooth_y, window_size

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
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        continue

    # 转换分辨率和颜色
    frame = cv2.resize(frame, (frame.shape[1] // 3, frame.shape[0] // 3))
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
            smooth_x, smooth_y, window_size = process_hand_movement(
                hand_landmarks,
                history,
                extend_ratio_x,
                extend_ratio_y,
                window_size,
                previous_position,
                mouse_update_interval
            )

            # 更新前一次鼠标位置
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