import cv2
import mediapipe as mp
import pyautogui
import math
import time
import numpy as np
from collections import deque

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

# 鼠标左键功能参数
hold_threshold_4to8 = 0.3  # 时间阈值 (单位：秒)
data = deque(maxlen = 2)  # 存储最近n个点，滚动更新
data.append((0,0)) # 初始化先定义第一个点
is_holding = False  # 是否检测到手指接触
is_pitching = False  # 是否正在进行捏合（长按）操作
click_return_level = None  # 水平线，用于判断是否返回
start_time = time.time()    # 手指接触的开始时间
contact_start_frame = None  # 记录接触开始的帧号
frame_counter = 0  # 全局帧计数器
# 动态阈值相关参数
window_N_4to8 = 5
distance_window = deque(maxlen=window_N_4to8)  # 存储最近 n 帧的归一化距离
normalized_threshold_4to8 = 0.45

# 鼠标右键功能参数
click_threshold_4to12 = 0.05

# 滚动相关参数
scroll_threshold = 0.05  # 滚动阈值
scroll_inertia_decay, scroll_smoothness = 0.95, 0.01  # 滚动惯性参数
# 手部移动平滑算法参数
mouse_update_interval = 0.05  # 设置鼠标更新间隔时间，防止频繁更新
low_speed_threshold = 200  # 低速阈值

# 鼠标状态变量
is_clicking_4to8, is_clicking_4to12 = False, False  # 单击状态
is_scrolling, scroll_speed, initial_y = False, 0, None  # 滚动状态和惯性参数

# 全局变量
hand_move_speed = 0  # 初始化hand_move_speed

# 工具函数
def calculate_distance(point1, point2):
    """计算两点的欧几里得距离"""
    if isinstance(point1, tuple) and isinstance(point2, tuple):
        return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)
    elif hasattr(point1, 'x') and hasattr(point2, 'x'):
        return math.sqrt((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2)
    else:
        raise ValueError("Invalid point type for distance calculation")
    
def calculate_slope(d1, d2, t1, t2):
    slope = (d2 - d1) / (t2 - t1)
    
    return slope

# 定义卡尔曼滤波器类
class KalmanFilter:

    def __init__(self):
        self.Q_factor = 10    #(0.1-10)
        self.R_factor = 0.1   #(0.1-10)
        self.dt = 1  # 时间间隔
        self.A = np.array([[1, self.dt], [0, 1]])  # 状态转移矩阵
        self.H = np.array([[1, 0]])  # 观测矩阵
        self.Q = np.array([[1, 0], [0, 3]]) * self.Q_factor  # 过程噪声协方差
        self.R = np.array([[10]]) * self.R_factor # 观测噪声协方差
        self.P = np.eye(2)  # 初始协方差矩阵
        self.x = np.zeros((2, 1))  # 初始状态向量

    def update(self, z, speed):
        # 根据 speed 动态调整 Q 和 R 因子
        if speed < low_speed_threshold:
            self.Q_factor = 0.05  # 减小过程噪声
            self.R_factor = 20    # 增大观测噪声
            self.x[1, 0] = 0      # 强制速度分量归零
        else:
            # 高速时，Q_factor 和 R_factor 线性变化
            self.Q_factor = np.clip(speed / 200.0, 0.1, 10)  # Q_factor 随 speed 线性变化
            self.R_factor = np.clip(10 / (speed + 1), 0.1, 10)  # R_factor 随 speed 变化
        
        self.Q = np.array([[1, 0], [0, 3]]) * self.Q_factor  # 更新过程噪声协方差
        self.R = np.array([[10]]) * self.R_factor  # 更新观测噪声协方差

        # 预测阶段
        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q

        # 更新阶段
        K = self.P @ self.H.T @ np.linalg.inv(self.H @ self.P @ self.H.T + self.R)
        self.x = self.x + K @ (z - self.H @ self.x)
        self.P = (np.eye(2) - K @ self.H) @ self.P

        return self.x[0, 0]  # 返回位置
# 定义处理手部运动的函数
def calculate_hand_move_speed(previous_position, current_position, last_update_time):
    global hand_move_speed

    if previous_position is None:
        previous_position = current_position
        return 0
    
    # 计算手部相对运动的变化
    distance = calculate_distance(previous_position, current_position)
    time_diff = time.time() - last_update_time
    hand_move_speed = distance / time_diff if time_diff > 0 else 0
    
    return hand_move_speed

def process_hand_movement(hand_landmarks, extend_ratio_x, extend_ratio_y):
    """处理手部运动，返回手部在屏幕上的位置"""
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

    return x, y
# smooth算法
def smooth_mouse_position(x, y, kalman_filter_x, kalman_filter_y, hand_move_speed):
    """使用卡尔曼滤波器平滑坐标"""
    smooth_x = kalman_filter_x.update(x, hand_move_speed)  # 传递当前速度作为speed
    smooth_y = kalman_filter_y.update(y, hand_move_speed)
    return int(smooth_x), int(smooth_y)
# 计算归一化距离
def calculate_normalized_distance(d_finger_tip, d_reference):
    """计算归一化的手指距离"""
    return d_finger_tip / d_reference
# 检测手指状态
def detect_finger_contact(normalized_distance, stability_frames=2):
    """
    检测手指接触状态，并更新动态阈值
    :param normalized_distance: 当前帧的归一化距离
    :param stability_frames: 判断轻触或捏合的稳定帧数
    :return: (contact_status, action)
             contact_status: 当前接触状态（True: 接触, False: 未接触）
             action: 动作类型（'click'、'pitch' 或 None）
    """
    global is_holding, is_pitching, click_return_level, contact_start_frame, frame_counter
    
    # 更新滑动窗口，计算动态阈值
    distance_window.append(normalized_distance)
    if len(distance_window) < distance_window.maxlen:
        print()
        return None  # 窗口不足，不进行判定

    dynamic_line = np.median(list(distance_window))
    dynamic_threshold_low = dynamic_line - 0.1
    dynamic_threshold_high = dynamic_line + 0.1
    
    print(f"  {dynamic_line:.3f}       {dynamic_threshold_low:.3f}     {dynamic_threshold_high:.3f}   " , end=' ')
    
    # 检测是否接触
    if not is_holding:
        if normalized_distance < dynamic_threshold_low:
            is_holding = True
            frame_counter = 0  # 初始化记录器
            click_return_level = dynamic_threshold_low  # 设置水平线
            print(f"{click_return_level:.3f}       is_holding   ")
            return None  # 开始接触
    else:
        frame_counter += 1 #hold后每一帧增加1
        if not is_pitching:
            if frame_counter <= stability_frames and normalized_distance > click_return_level:
                is_holding = False
                print("-> Click detected")
                return 'click'  # 轻触短按
            elif frame_counter > stability_frames:
                is_pitching = True
                print("-> Pitch detected")
                return 'pitch'  # 开始捏合
        else:
            if normalized_distance > dynamic_threshold_high:
                is_holding = False
                is_pitching = False
                print("-> Pitch release")
                return 'release'  # 释放左键

    print()
    # 默认返回
    return None  # 未触发任何事件
    

def perform_left_button(data, d_reference):
    """
    处理食指与拇指距离变化，实现点击与拖动功能
    :param data: [(time, distance), ...] 实时数据序列
    :param d_reference: 手掌宽度或中指关节长度（参考距离）
    """
    global is_holding, is_pitching

    # 从数据中提取时间和距离
    t2, d2 = data[-1]  # 当前帧的数据

    # 计算归一化距离
    normalized_distance = calculate_normalized_distance(d2, d_reference)
    print(f"{t2 - start_time:.3f}   {normalized_distance:.3f}", end=" ")

    # 检测接触状态和动作
    action = detect_finger_contact(normalized_distance)

    # 根据动作执行对应操作
    if action == 'click':
        #pyautogui.click()  # 执行轻触单击
        pyautogui.doubleClick()
    elif action == 'pitch':
        pyautogui.mouseDown()  # 按下左键开始拖动
    elif action == 'release':
        pyautogui.mouseUp()  # 释放左键结束拖动

def perform_right_click(distance, normalized_threshold_4to8, clicking_state):
    """右键单击"""
    if distance < normalized_threshold_4to8 and not clicking_state[0]:
        pyautogui.click(button='right')
        clicking_state[0] = True
    elif distance >= normalized_threshold_4to8:
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
start_time = time.time()    # 程序开始运行的时间
data_points = []  # 存储实时时间和两指距离的列表
previous_position = None    # 开始之前清空鼠标位置
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
            
            wrist = hand_landmarks.landmark[0]
            index_finger_mcp = hand_landmarks.landmark[5]
            thumb_tip = hand_landmarks.landmark[4]
            index_finger_tip = hand_landmarks.landmark[8]
            middle_finger_tip = hand_landmarks.landmark[12]
            ring_finger_tip = hand_landmarks.landmark[16]
            
            # 处理手部运动并计算平滑坐标
            smooth_x, smooth_y = process_hand_movement(
                hand_landmarks,
                extend_ratio_x,
                extend_ratio_y
            )

            # 1处理手部运动 （以下顺序不能调换）
            x, y = process_hand_movement(hand_landmarks, extend_ratio_x, extend_ratio_y)
            # 2获取手部运动的速度
            hand_move_speed = calculate_hand_move_speed(previous_position, (x,y), last_update_time)
            # 3 更新最近计算的时间
            last_update_time = time.time()
            # 4 计算平滑坐标
            smooth_x, smooth_y = smooth_mouse_position(x, y, kalman_filter_x, kalman_filter_y, hand_move_speed)

            # 更新鼠标位置
            pyautogui.moveTo(smooth_x, smooth_y)
            previous_position = (x, y)

            # 指尖距离计算
            distance_4to8 = calculate_distance(thumb_tip, index_finger_tip)
            distance_4to12 = calculate_distance(thumb_tip, middle_finger_tip)
            # 参照距离计算
            distance_0to5 = calculate_distance(wrist, index_finger_mcp)
            
            # 左键操作
            data.append((time.time(), distance_4to8))
            perform_left_button(data , distance_0to5)

            # # 右键操作
            # perform_right_click(distance_4to12, click_threshold_4to12, [is_clicking_4to12])

            # # 滚动操作
            # if calculate_distance(thumb_tip, ring_finger_tip) < scroll_threshold:
            #     if not is_scrolling:
            #         is_scrolling = True
            #         initial_y = ring_finger_tip.y
            #         scroll_speed = 0
            #     else:
            #         perform_scrolling(ring_finger_tip, initial_y, {"active": is_scrolling, "speed": scroll_speed, "initial_y": initial_y}, scroll_smoothness, scroll_inertia_decay)
            # else:
            #     is_scrolling = False    

    #摄像头镜像
    frame = cv2.flip(frame, 1)
    
    # 在屏幕上显示Q_factor、R_factor和speed
    QR_ratio_factor = kalman_filter_x.Q_factor / kalman_filter_x.R_factor
    cv2.putText(frame, f"Speed: {hand_move_speed:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"QR_ratio_factor: {QR_ratio_factor:.2f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
    
    # 显示视频窗口
    cv2.imshow("Air Mouse", frame)

    # 检查退出条件
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()