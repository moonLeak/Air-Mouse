import cv2
import mediapipe as mp
import pyautogui
from pynput.mouse import Controller as MouseController, Button  # type: ignore
import Quartz
import math
import time
import csv
import os
import numpy as np
from collections import deque

# 初始化 MouseController
mouse = MouseController()

# MediaPipe手部追踪模块配置
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.5 , min_tracking_confidence=0.3)
mp_drawing = mp.solutions.drawing_utils

# 摄像头初始化
cap = cv2.VideoCapture(0)
mirror_frame = True  # 是否镜像显示

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 比例映射参数设置
extend_ratio_x, extend_ratio_y = 2.5, 2.5  # 手部范围扩展比例

# 手部移动平滑算法参数
mouse_update_interval = 0.03  # 设置鼠标更新间隔时间，防止频繁更新
low_speed_threshold = 200  # 低速阈值
position_window = deque(maxlen=10)  # 定义滑动窗口，最多存储10个位置

# 所有手指共享参数(Globle)
hand_move_speed = 0  # 初始化hand_move_speed

class GeneralCalculation:
    @staticmethod
    def calculate_distance(point1, point2):
        """
        计算两点的欧几里得距离
        :param point1: 第一个点 (tuple 或具有 x, y 属性的对象)
        :param point2: 第二个点 (tuple 或具有 x, y 属性的对象)
        :return: 欧几里得距离
        """
        if isinstance(point1, tuple) and isinstance(point2, tuple):
            return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)
        elif hasattr(point1, 'x') and hasattr(point2, 'x'):
            return math.sqrt((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2)
        else:
            raise ValueError("Invalid point type for distance calculation")

    @staticmethod
    def calculate_normalized_distance(d_finger_tip, d_reference):
        """
        计算归一化的手指距离
        :param d_finger_tip: 两点之间的实际距离
        :param d_reference: 参考距离
        :return: 归一化距离
        """
        if d_reference == 0:
            raise ValueError("Reference distance cannot be zero.")
        return d_finger_tip / d_reference

    @staticmethod
    def calculate_speed(previous_position, current_position, last_update_time):
        """
        计算两点间的移动速度
        :param previous_position: 上一时刻的位置 (tuple)
        :param current_position: 当前时刻的位置 (tuple)
        :param last_update_time: 上次更新的时间戳
        :return: 计算的速度
        """
        if previous_position is None:
            return 0  # 初始速度为 0

        # 计算两点间距离和时间差
        distance = GeneralCalculation.calculate_distance(previous_position, current_position)
        time_diff = max(time.time() - last_update_time, 1e-6)  # 确保时间差不为零

        return distance / time_diff

    @staticmethod
    def calculate_center(points, weights=None):
        """
        计算点集的加权中心
        :param points: 点的列表 [(x1, y1), (x2, y2), ...]
        :param weights: 对应的权重列表
        :return: 加权中心的坐标 (x, y)
        """
        if not points:
            raise ValueError("Points list cannot be empty.")
        
        if weights is None:
            weights = [1] * len(points)
        
        if len(points) != len(weights):
            raise ValueError("Points and weights must have the same length.")
        
        x_center = sum(p[0] * w for p, w in zip(points, weights)) / sum(weights)
        y_center = sum(p[1] * w for p, w in zip(points, weights)) / sum(weights)
        
        return x_center, y_center

is_zooming_dominant = False # 判断zoom状态的key 主要手
is_zooming_secondary = False # 判断zoom状态的key 次要手

class FourToEight:
    global is_zooming_dominant # 判断zoom状态的key 主要手
    global is_zooming_secondary # 判断zoom状态的key 次要手
    
    def __init__(self):
        # 初始化参数
        self.is_holding = False  # 是否检测到手指接触
        self.is_pitching = False  # 是否正在进行捏合（长按）操作
        self.click_return_level = None  # 点击时的阈值
        self.release_return_level_up = None  # 释放时的上限阈值

        self.release_return_level = None  # 综合释放阈值
        self.frame_counter = 0  # 用于检测稳定的帧数
        self.normalized_distance_window = deque(maxlen=5)  # 滑动窗口，存储最近5帧的归一化距离
        self.dynamic_line_history = deque(maxlen=300)  # 保存动态阈值曲线历史
        self.dynamic_threshold_low_history = deque(maxlen=300)
        self.dynamic_threshold_high_history = deque(maxlen=300)
        self.normalized_4to8_history = deque(maxlen=300)

    def detect_finger_contact(self, normalized_distance, hand_move_speed):
        """检测手指接触状态并返回对应操作（点击、拖动或释放）"""
        stability_frames = 2  # 判断为长按需要持续的时间/帧

        # 更新滑动窗口
        self.normalized_distance_window.append(normalized_distance)
        if len(self.normalized_distance_window) < self.normalized_distance_window.maxlen:
            return None  # 如果窗口不足，不进行判定

        # 动态阈值计算
        dynamic_line = np.median(list(self.normalized_distance_window))
        dynamic_threshold_low = dynamic_line - 0.15
        dynamic_threshold_high = dynamic_line + 0.15

        # 更新曲线历史
        self.dynamic_line_history.append(dynamic_line)
        self.dynamic_threshold_low_history.append(dynamic_threshold_low)
        self.dynamic_threshold_high_history.append(dynamic_threshold_high)
        self.normalized_4to8_history.append(normalized_distance)

        # 检测是否接触
        if not self.is_holding:
            if normalized_distance < dynamic_threshold_low:
                self.is_holding = True
                self.frame_counter = 0
                self.click_return_level = dynamic_threshold_low
                self.release_return_level_up = dynamic_line
                return None
        else:
            self.frame_counter += 1
            if not self.is_pitching:
                if self.frame_counter <= stability_frames and normalized_distance > self.click_return_level:
                    self.is_holding = False
                    return 'click'  # 短按单击
                elif self.frame_counter > stability_frames:
                    self.is_pitching = True
                    self.release_return_level_low = dynamic_line
                    self.release_return_level = (
                        self.release_return_level_low +
                        (self.release_return_level_up - self.release_return_level_low) / 4
                    )
                    return 'pitch'  # 开始捏合
            else:
                if (normalized_distance > dynamic_threshold_high or 
                        dynamic_line > self.release_return_level):
                    if hand_move_speed > low_speed_threshold:  # 高速移动时忽略释放
                        return None
                    self.is_holding = False
                    self.is_pitching = False
                    return 'release'  # 释放左键

        return None  # 默认返回        

    def perform_action_dominant(self, data, d_reference, hand_move_speed):
        """
        对主要手根据检测到的手势执行鼠标操作
        """
        t2, d2 = data[-1]
        normalized_distance = GeneralCalculation.calculate_normalized_distance(d2, d_reference)
        action = self.detect_finger_contact(normalized_distance, hand_move_speed)

        if action == 'click':
            mouse.click(Button.left)  # 使用 pynput 左键单击
        elif action == 'pitch':
            mouse.press(Button.left)  # 使用 pynput 按下左键
            is_zooming_dominant = True  # 激发主要手的 zooming 状态
            return(is_zooming_dominant)
        elif action == 'release':
            mouse.release(Button.left)  # 使用 pynput 松开左键
            is_zooming_dominant = False  # 断开主要手的 zooming 状态
            return(is_zooming_dominant)

    def perform_action_secondary(self, data, d_reference, hand_move_speed):
        """
        对次要手根据检测到的手势执行鼠标操作
        """
        t2, d2 = data[-1]
        normalized_distance = GeneralCalculation.calculate_normalized_distance(d2, d_reference)
        action = self.detect_finger_contact(normalized_distance, hand_move_speed)

        if action == 'click':
            mouse.click(Button.left)  # 使用 pynput 左键单击
        elif action == 'pitch':
            is_zooming_secondary = True  # 激发次要手的 zooming 状态
            return(is_zooming_secondary)
        elif action == 'release':
            is_zooming_secondary = False  # 断开次要手的 zooming 状态
            return(is_zooming_secondary)

class FourToTwelve:
    def __init__(self):
        # 初始化参数
        self.is_holding = False  # 是否检测到手指接触
        self.is_pitching = False  # 是否正在进行捏合操作
        self.click_return_level = None  # 点击时的阈值
        self.release_return_level_up = None  # 释放时的上限阈值
        self.release_return_level_low = None  # 释放时的下限阈值
        self.release_return_level = None  # 综合释放阈值
        self.frame_counter = 0  # 帧计数器
        self.normalized_distance_window = deque(maxlen=5)  # 滑动窗口，存储最近5帧的归一化距离
        self.dynamic_line_history = deque(maxlen=300)  # 保存动态阈值曲线历史
        self.dynamic_threshold_low_history = deque(maxlen=300)
        self.dynamic_threshold_high_history = deque(maxlen=300)
        self.normalized_4to12_history = deque(maxlen=300)
        self.scroll_state = {"active": False, "speed_x": 0, "speed_y": 0, "initial_x": None, "initial_y": None}

    def detect_finger_contact(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
        """检测手指接触状态并返回对应操作（点击、滚动或释放）"""
        stability_frames = 2  # 判断为长按需要持续的时间/帧
        stability_radius = 30  # 鼠标移动触发滚动的最小距离

        # 更新滑动窗口
        self.normalized_distance_window.append(normalized_distance)
        if len(self.normalized_distance_window) < self.normalized_distance_window.maxlen:
            return None  # 如果窗口不足，不进行判定

        # 动态阈值计算
        dynamic_line = np.median(list(self.normalized_distance_window))
        dynamic_threshold_low = dynamic_line - 0.15
        dynamic_threshold_high = dynamic_line + 0.15

        # 更新曲线历史
        self.dynamic_line_history.append(dynamic_line)
        self.dynamic_threshold_low_history.append(dynamic_threshold_low)
        self.dynamic_threshold_high_history.append(dynamic_threshold_high)
        self.normalized_4to12_history.append(normalized_distance)

        # 检测是否接触
        if not self.is_holding:
            if normalized_distance < dynamic_threshold_low:
                self.is_holding = True
                self.frame_counter = 0
                self.click_return_level = dynamic_threshold_low
                self.release_return_level_up = dynamic_line
                return None
        else:
            self.frame_counter += 1
            if not self.is_pitching:
                if self.frame_counter <= stability_frames and normalized_distance > self.click_return_level: #两帧之内分开=click
                    self.is_holding = False
                    return 'right_click'  # 单击右键
                
                elif (GeneralCalculation.calculate_distance(mouse_location_now, mouse_location_original) > stability_radius) or (self.frame_counter > stability_frames): #移动超过范围=scroll # 超过两帧=scroll
                    self.is_pitching = True
                    self.release_return_level_low = dynamic_line
                    self.release_return_level = (self.release_return_level_low + (self.release_return_level_up - self.release_return_level_low) / 4 )
                    self.scroll_state["active"] = True
                    self.scroll_state["initial_y"] = mouse_location_now[1]
                    return 'scroll_start'  # 开始滚动

            else:
                if normalized_distance > dynamic_threshold_high or dynamic_line > self.release_return_level:
                    self.is_holding = False
                    self.is_pitching = False
                    self.scroll_state["active"] = False  # 停止滚动
                    return 'release'  # 释放操作

        return None

    def perform_action_dominant(self, data, d_reference, mouse_location_now, mouse_location_original, hand_move_speed):
        """
        根据检测到的手势执行鼠标操作，并实现滚动和惯性滚动
        """
        # 滚动平滑系数和惯性滚动衰减系数
        smoothness = 0.8
        decay = 0.9
        speedfactor = 0.5  # 速度因子，用于调整滚动速度

        # 获取最新的数据点
        t2, d2 = data[-1]

        # 计算归一化距离
        normalized_distance = GeneralCalculation.calculate_normalized_distance(d2, d_reference)

        # 检测手势操作
        action = self.detect_finger_contact(normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed)

        # 执行相应的手势动作
        if action == 'right_click':
            mouse.click(Button.right)  # 使用 pynput 右键单击
        elif action == 'scroll_start':
            self.scroll_state["active"] = True  # 启动滚动模式
            self.scroll_state["initial_x"] = mouse_location_now[0]  # 记录初始滚动位置 x
            self.scroll_state["initial_y"] = mouse_location_now[1]  # 记录初始滚动位置 y
        elif action == 'release':
            self.scroll_state["active"] = False  # 停止滚动

        # 滚动和惯性滚动逻辑
        if self.scroll_state["active"]:
            # 计算滚动增量
            scroll_delta_x = (self.scroll_state["initial_x"] - mouse_location_now[0]) * speedfactor
            scroll_delta_y = (self.scroll_state["initial_y"] - mouse_location_now[1]) * speedfactor

            # 更新滚动速度
            self.scroll_state["speed_x"] = scroll_delta_x
            self.scroll_state["speed_y"] = scroll_delta_y

            # 同时执行横向和纵向滚动
            mouse.scroll(-int(scroll_delta_x), -int(scroll_delta_y))  # 横向为负，纵向为负

            # 更新当前鼠标位置
            self.scroll_state["initial_x"] = mouse_location_now[0]
            self.scroll_state["initial_y"] = mouse_location_now[1]
        else:
            # 惯性滚动
            if abs(self.scroll_state["speed_x"]) > 1 or abs(self.scroll_state["speed_y"]) > 1:
                # 使用平滑滚动
                mouse.scroll(
                    -int(self.scroll_state["speed_x"] * smoothness),
                    -int(self.scroll_state["speed_y"] * smoothness),
                )
                # 衰减滚动速度
                self.scroll_state["speed_x"] *= decay
                self.scroll_state["speed_y"] *= decay

class CombinatorialOperation:
    def __init__(self, zooming_factor=10):
        """
        初始化组合操作类
        :param zooming_factor: 缩放因子，用于调节缩放量的灵敏度
        """
        self.zooming_factor = zooming_factor

    def simulate_cmd_scroll(self, direction, amount):
        """
        模拟 Cmd + 鼠标滚轮事件
        :param direction: 滚动方向，1 为向上（放大），-1 为向下（缩小）
        :param amount: 滚动量
        """
        key_code_cmd = 0x37  # Command 键的键码

        # 按下 Command 键
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code_cmd, True)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

        # 滚动鼠标
        for _ in range(amount):
            scroll_event = Quartz.CGEventCreateScrollWheelEvent(
                None,
                Quartz.kCGScrollEventUnitLine,
                1,  # 单轴滚动
                direction
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll_event)

        # 释放 Command 键
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code_cmd, False)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def perform_zooming(self, dominant_finger_tip, secondary_finger_tip, previous_distance_zoom):
        """
        实现双手缩放操作
        :param dominant_finger_tip: 主要手的食指尖坐标 (x, y)
        :param secondary_finger_tip: 次要手的食指尖坐标 (x, y)
        :param previous_distance_zoom: 前一帧的双手食指尖距离
        :return: 当前帧的食指尖距离，用于下一帧的缩放计算
        """
        # 计算当前帧双手食指尖的距离
        current_distance = GeneralCalculation.calculate_distance(dominant_finger_tip, secondary_finger_tip)

        # 计算距离变化
        distance_change = current_distance - previous_distance_zoom

        # 映射距离变化为滚轮事件
        scroll_direction = 1 if distance_change > 0 else -1  # 距离增大为放大，减少为缩小
        scroll_amount = abs(int(distance_change * self.zooming_factor))  # 滚动量与缩放因子成正比

        # 模拟 cmd + 滚轮事件
        self.simulate_cmd_scroll(scroll_direction, scroll_amount)

        # 返回当前距离供下一帧计算
        return current_distance
    
class HandMouseController:
    def __init__(self, screen_width, screen_height, extend_ratio_x=2.5, extend_ratio_y=2.5, low_speed_threshold=200):
        """
        初始化 HandMouseController
        :param screen_width: 屏幕宽度
        :param screen_height: 屏幕高度
        :param extend_ratio_x: 手部横向扩展比例
        :param extend_ratio_y: 手部纵向扩展比例
        :param low_speed_threshold: 低速阈值
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.extend_ratio_x = extend_ratio_x
        self.extend_ratio_y = extend_ratio_y
        self.low_speed_threshold = low_speed_threshold

        # 初始化卡尔曼滤波器
        self.kalman_filter_x = self.KalmanFilter(self.low_speed_threshold)
        self.kalman_filter_y = self.KalmanFilter(self.low_speed_threshold)
        self.previous_position = None

    class KalmanFilter:
        def __init__(self, low_speed_threshold):
            self.low_speed_threshold = low_speed_threshold
            self.Q_factor = 10    # 过程噪声因子
            self.R_factor = 0.1   # 观测噪声因子
            self.dt = 1           # 时间间隔
            self.A = np.array([[1, self.dt], [0, 1]])  # 状态转移矩阵
            self.H = np.array([[1, 0]])               # 观测矩阵
            self.Q = np.array([[1, 0], [0, 3]]) * self.Q_factor  # 过程噪声协方差
            self.R = np.array([[10]]) * self.R_factor  # 观测噪声协方差
            self.P = np.eye(2)  # 初始协方差矩阵
            self.x = np.zeros((2, 1))  # 初始状态向量

        def update(self, z, speed):
            # 根据 speed 动态调整 Q 和 R 因子
            if speed < self.low_speed_threshold:
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

            return self.x[0, 0]  # 返回平滑后的位置

    def process_hand_movement(self, hand_landmarks):
        """
        处理手部运动，返回手部在屏幕上的位置
        :param hand_landmarks: MediaPipe 手部关键点
        :return: 映射到屏幕上的坐标 (x, y)
        """
        # 计算手掌心的几何中心（归一化坐标）
        x_values_trimmed = sorted([hand_landmarks.landmark[i].x for i in [0, 1, 2, 5, 9, 13, 17]])[1:-1]
        y_values_trimmed = sorted([hand_landmarks.landmark[i].y for i in [0, 1, 2, 5, 9, 13, 17]])[1:-1]
        weights = [3, 2, 1, 1, 1]  # 加权平均权重
        norm_x = sum(x * w for x, w in zip(x_values_trimmed, weights[1:-1])) / sum(weights[1:-1])
        norm_y = sum(y * w for y, w in zip(y_values_trimmed, weights[1:-1])) / sum(weights[1:-1])

        # 扩展坐标范围
        extended_x = max(0, min(1, (norm_x - 0.5) * self.extend_ratio_x + 0.5))
        extended_y = max(0, min(1, (norm_y - 0.5) * self.extend_ratio_y + 0.5))

        # 映射到屏幕坐标
        x = int((1 - extended_x) * self.screen_width)  # 反转x坐标
        y = int(extended_y * self.screen_height)

        return x, y

    def smooth_mouse_position(self, x, y, hand_move_speed):
        """
        使用卡尔曼滤波器平滑坐标
        :param x: 原始 x 坐标
        :param y: 原始 y 坐标
        :param hand_move_speed: 手部移动速度
        :return: 平滑后的坐标 (smooth_x, smooth_y)
        """
        smooth_x = self.kalman_filter_x.update(x, hand_move_speed)
        smooth_y = self.kalman_filter_y.update(y, hand_move_speed)
        return int(smooth_x), int(smooth_y)

    def calculate_hand_move_speed(self, current_position, last_update_time):
        """
        计算手部移动速度
        :param current_position: 当前帧手部位置
        :param last_update_time: 上一次帧的时间
        :return: 手部移动速度
        """
        if self.previous_position is None:
            self.previous_position = current_position
            return 0

        # 计算手部相对运动的变化
        distance = math.sqrt(
            (current_position[0] - self.previous_position[0]) ** 2 +
            (current_position[1] - self.previous_position[1]) ** 2
        )
        time_diff = max(time.time() - last_update_time, 1e-6)  # 确保 time_diff 不为零
        self.previous_position = current_position

        return distance / time_diff

    def move_mouse(self, smooth_x, smooth_y):
        """
        移动鼠标到指定位置
        :param smooth_x: 平滑后的 x 坐标
        :param smooth_y: 平滑后的 y 坐标
        """
        mouse.position = (smooth_x, smooth_y)

class Monitor:
    def __init__(self, frame_num_max=300, base_y=300, scale_factor=200, horizontal_scale=2):
        """
        初始化监控器
        :param frame_num_max: 保存历史帧数的最大值
        :param base_y: 曲线绘制的零点位置
        :param scale_factor: 曲线纵向缩放比例
        :param horizontal_scale: 曲线横向缩放比例
        """
        self.frame_num_max = frame_num_max
        self.base_y = base_y
        self.scale_factor = scale_factor
        self.horizontal_scale = horizontal_scale
        self.start_time = time.time()
        self.data_log = []  # 存储运行过程中产生的数据
        self.previous_middle_tip = None  # 前一帧的中指位置

        # 初始化曲线数据，支持左右手独立数据存储
        self.curve_data = {
            "Right_4to8": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
            "Right_4to12": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
            "Left_4to8": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
            "Left_4to12": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
        }

    def update_curve_data(self, key, dynamic_line, threshold_low, threshold_high, normalized, hand_label):
        """
        更新曲线数据，支持左右手
        :param key: 数据类型的关键字 (4to8 或 4to12)
        :param dynamic_line: 动态线
        :param threshold_low: 低阈值
        :param threshold_high: 高阈值
        :param normalized: 归一化距离
        :param hand_label: 'Left' 或 'Right'，区分左右手
        """
        full_key = f"{hand_label}_{key}"  # 生成完整的键
        self.curve_data[full_key]["dynamic_line"].append(dynamic_line)
        self.curve_data[full_key]["threshold_low"].append(threshold_low)
        self.curve_data[full_key]["threshold_high"].append(threshold_high)
        self.curve_data[full_key]["normalized"].append(normalized)

    def draw_graph(self, frame, data, color, position_y):
        """
        绘制单条曲线
        :param frame: 图像帧
        :param data: 数据队列
        :param color: 线条颜色 (B, G, R)
        :param position_y: 曲线绘制的零点高度
        """
        for i in range(1, len(data)):
            x1 = (i - 1) * self.horizontal_scale
            y1 = int(position_y - data[i - 1] * self.scale_factor)
            x2 = i * self.horizontal_scale
            y2 = int(position_y - data[i] * self.scale_factor)
            cv2.line(frame, (x1, y1), (x2, y2), color, 2)

    def display_graphs(self, graph_frame):
        """
        在图表帧中绘制所有曲线，支持左右手分开显示
        :param graph_frame: 图表帧
        """
        height, width, _ = graph_frame.shape

        # 动态调整 base_y 以适应窗口大小
        base_y_right_4to8 = height // 4  # 顶部 1/4 区域
        base_y_right_4to12 = height // 2  # 顶部 2/4 区域
        base_y_left_4to8 = 3 * height // 4  # 底部 3/4 区域
        base_y_left_4to12 = height  # 底部区域

        # 绘制右手 4to8 曲线
        self.draw_graph(graph_frame, self.curve_data["Right_4to8"]["dynamic_line"], (105, 105, 105), base_y_right_4to8)
        self.draw_graph(graph_frame, self.curve_data["Right_4to8"]["threshold_low"], (255, 0, 0), base_y_right_4to8)
        self.draw_graph(graph_frame, self.curve_data["Right_4to8"]["threshold_high"], (255, 0, 0), base_y_right_4to8)
        self.draw_graph(graph_frame, self.curve_data["Right_4to8"]["normalized"], (0, 255, 0), base_y_right_4to8)

        # 绘制右手 4to12 曲线
        self.draw_graph(graph_frame, self.curve_data["Right_4to12"]["dynamic_line"], (105, 105, 105), base_y_right_4to12)
        self.draw_graph(graph_frame, self.curve_data["Right_4to12"]["threshold_low"], (255, 0, 0), base_y_right_4to12)
        self.draw_graph(graph_frame, self.curve_data["Right_4to12"]["threshold_high"], (255, 0, 0), base_y_right_4to12)
        self.draw_graph(graph_frame, self.curve_data["Right_4to12"]["normalized"], (0, 255, 0), base_y_right_4to12)

        # 绘制左手 4to8 曲线
        self.draw_graph(graph_frame, self.curve_data["Left_4to8"]["dynamic_line"], (105, 105, 105), base_y_left_4to8)
        self.draw_graph(graph_frame, self.curve_data["Left_4to8"]["threshold_low"], (0, 0, 255), base_y_left_4to8)
        self.draw_graph(graph_frame, self.curve_data["Left_4to8"]["threshold_high"], (0, 0, 255), base_y_left_4to8)
        self.draw_graph(graph_frame, self.curve_data["Left_4to8"]["normalized"], (0, 255, 255), base_y_left_4to8)

        # 绘制左手 4to12 曲线
        self.draw_graph(graph_frame, self.curve_data["Left_4to12"]["dynamic_line"], (105, 105, 105), base_y_left_4to12)
        self.draw_graph(graph_frame, self.curve_data["Left_4to12"]["threshold_low"], (0, 0, 255), base_y_left_4to12)
        self.draw_graph(graph_frame, self.curve_data["Left_4to12"]["threshold_high"], (0, 0, 255), base_y_left_4to12)
        self.draw_graph(graph_frame, self.curve_data["Left_4to12"]["normalized"], (0, 255, 255), base_y_left_4to12)

    def label_hands_on_feed(self, frame, results, handedness):
        """
        在摄像头画面中标注左右手
        :param frame: 摄像头画面
        :param results: MediaPipe 手部检测结果
        :param handedness: 包含左右手标识的列表
        """
        if not results.multi_hand_landmarks or not handedness:
            return  # 如果没有检测到手，直接返回
        
        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            # 获取手的标签 ("Left" 或 "Right")
            label = handedness[idx]

            # 获取手掌中心点的坐标（基于手掌心关键点 0）
            wrist = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            x = int(wrist.x * frame.shape[1])  # 转换为图像坐标
            y = int(wrist.y * frame.shape[0])

            # 在画面中标注手的标签
            cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def display_camera_feed(self, frame, hand_move_speed, fps, middle_finger_displacement):
        """
        显示摄像头画面，并在画面上叠加手部速度、帧率、中指位移等信息
        """
        cv2.putText(frame, f"Speed: {hand_move_speed:.2f} px/s", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        cv2.putText(frame, f"Middle Finger Displacement: {middle_finger_displacement:.2f}", 
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("Camera Feed", frame)


# 初始化必要的类
monitor = Monitor(frame_num_max=300, base_y=300, scale_factor=300, horizontal_scale=2)
hand_mouse_controller = HandMouseController(screen_width, screen_height)
four_to_eight = FourToEight()
four_to_twelve = FourToTwelve()

last_update_time = time.time()  # 上次鼠标位置更新时间
previous_position = None        # 开始之前清空鼠标位置
data_points_4to8 = []           # 存储4to8的实时数据
data_points_4to12 = []          # 存储4to12的实时数据
middle_finger_displacement = 0  # 初始化中指位移距离
previous_distance_zoom = 0  # 初始化前一帧的双手食指尖距离(zooming)

def process_dominant_hand(
    hand_landmarks,
    data_points_4to8,
    data_points_4to12,
    reference_distance_4to8,
    reference_distance_4to12,
    previous_position,
    hand_move_speed,
    last_update_time,  # 添加参数
    hand_mouse_controller,
):
    """
    处理主要手的操作
    """
    # 平滑鼠标位置并移动鼠标
    x, y = HandMouseController.process_hand_movement(hand_landmarks)
    hand_move_speed = HandMouseController.calculate_hand_move_speed((x, y), last_update_time)
    last_update_time = time.time()  # 更新 last_update_time

    smooth_x, smooth_y = HandMouseController.smooth_mouse_position(x, y, hand_move_speed)
    HandMouseController.move_mouse(smooth_x, smooth_y)
    previous_position = (x, y)

    # 4to8判定
    if len(data_points_4to8) > 0:
        FourToEight.perform_action_dominant(data_points_4to8, reference_distance_4to8, hand_move_speed)

    # 4to12判定
    if len(data_points_4to12) > 0:
        FourToTwelve.perform_action_dominant(
            data_points_4to12, reference_distance_4to12, previous_position, previous_position, hand_move_speed
        )

    return hand_move_speed, previous_position  # 返回更新的值

def process_secondary_hand(
    hand_landmarks,
    data_points_4to8,
    data_points_4to12,
    reference_distance_4to8,
    reference_distance_4to12,
    hand_move_speed,
):
    """
    处理次要手的操作
    """
    # 4to8判定
    if len(data_points_4to8) > 0:
        four_to_eight.perform_action_secondary(data_points_4to8, reference_distance_4to8, hand_move_speed)

    # 4to12判定
    if len(data_points_4to12) > 0:
        four_to_twelve.perform_action_secondary(data_points_4to12, reference_distance_4to12, hand_move_speed)

# 初始化 Monitor
monitor = Monitor(frame_num_max=300, base_y=300, scale_factor=200, horizontal_scale=3)

# 规定主要手和次要手
dominant_hand = "Right"
secondary_hand = "Left" if dominant_hand == "Right" else "Right"


while cap.isOpened():
    start_time = time.time()
    ret, frame = cap.read()
    if not ret:
        continue

    # 转换分辨率和颜色
    frame = cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2))
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 使用 MediaPipe 处理图像
    results = hands.process(rgb_frame)

    if results.multi_handedness:
        handedness = [
            ("Left" if hand.classification[0].label == "Right" else "Right") if mirror_frame
            else hand.classification[0].label
            for hand in results.multi_handedness
        ]

        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            label = handedness[idx]  # 获取当前手的标识 ('Left' or 'Right')

            # 获取拇指、食指、中指的关键点位置
            thumb_tip = hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
            index_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
            middle_finger_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]

            # 计算两对手指的距离
            distance_thumb_index = GeneralCalculation.calculate_distance(thumb_tip, index_finger_tip)
            distance_thumb_middle = GeneralCalculation.calculate_distance(thumb_tip, middle_finger_tip)

            # 参考距离计算
            reference_distance_4to8 = GeneralCalculation.calculate_distance(
                hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_IP],
                hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_DIP],
            )
            reference_distance_4to12 = GeneralCalculation.calculate_distance(
                hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_IP],
                hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_DIP],
            )

            # 归一化距离
            normalized_4to8 = GeneralCalculation.calculate_normalized_distance(
                distance_thumb_index, reference_distance_4to8
            )
            normalized_4to12 = GeneralCalculation.calculate_normalized_distance(
                distance_thumb_middle, reference_distance_4to12
            )

            # 数据点更新
            if distance_thumb_index > 0:
                data_points_4to8.append((time.time(), distance_thumb_index))
            if distance_thumb_middle > 0:
                data_points_4to12.append((time.time(), distance_thumb_middle))

            # 处理主要手的操作
            if label == dominant_hand:
                hand_move_speed, previous_position = process_dominant_hand(
                    hand_landmarks,
                    data_points_4to8,
                    data_points_4to12,
                    reference_distance_4to8,
                    reference_distance_4to12,
                    previous_position,
                    hand_move_speed,
                )
                # 更新 Monitor 曲线数据
                monitor.update_curve_data(
                    f"4to8",
                    four_to_eight.dynamic_line_history[-1] if four_to_eight.dynamic_line_history else 0,
                    four_to_eight.dynamic_threshold_low_history[-1] if four_to_eight.dynamic_threshold_low_history else 0,
                    four_to_eight.dynamic_threshold_high_history[-1] if four_to_eight.dynamic_threshold_high_history else 0,
                    normalized_4to8,
                    dominant_hand,)
                monitor.update_curve_data(
                    f"4to12",
                    four_to_twelve.dynamic_line_history[-1] if four_to_twelve.dynamic_line_history else 0,
                    four_to_twelve.dynamic_threshold_low_history[-1] if four_to_twelve.dynamic_threshold_low_history else 0,
                    four_to_twelve.dynamic_threshold_high_history[-1] if four_to_twelve.dynamic_threshold_high_history else 0,
                    normalized_4to12,
                    dominant_hand,)

            # 处理次要手的操作
            elif label == secondary_hand:
                process_secondary_hand(
                    hand_landmarks,
                    data_points_4to8,
                    data_points_4to12,
                    reference_distance_4to8,
                    reference_distance_4to12,
                    hand_move_speed,
                )
                # 更新 Monitor 曲线数据
                monitor.update_curve_data(
                    f"4to8",
                    four_to_eight.dynamic_line_history[-1] if four_to_eight.dynamic_line_history else 0,
                    four_to_eight.dynamic_threshold_low_history[-1] if four_to_eight.dynamic_threshold_low_history else 0,
                    four_to_eight.dynamic_threshold_high_history[-1] if four_to_eight.dynamic_threshold_high_history else 0,
                    normalized_4to8,
                    secondary_hand,)
                monitor.update_curve_data(
                    f"4to12",
                    four_to_twelve.dynamic_line_history[-1] if four_to_twelve.dynamic_line_history else 0,
                    four_to_twelve.dynamic_threshold_low_history[-1] if four_to_twelve.dynamic_threshold_low_history else 0,
                    four_to_twelve.dynamic_threshold_high_history[-1] if four_to_twelve.dynamic_threshold_high_history else 0,
                    normalized_4to12,
                    secondary_hand,)
                
                

    # # Zooming 判定逻辑
    # if is_zooming_dominant and is_zooming_secondary:
    #     # 获取主要手和次要手的食指尖坐标
    #     dominant_finger_tip = (index_finger_tip.x * frame.shape[1], index_finger_tip.y * frame.shape[0])
    #     secondary_finger_tip = (middle_finger_tip.x * frame.shape[1], middle_finger_tip.y * frame.shape[0])

    #     # 调用 Zooming 方法
    #     previous_distance_zoom = CombinatorialOperation.perform_zooming(
    #         dominant_finger_tip, secondary_finger_tip, previous_distance_zoom
    #     )

    # 如果没有检测到手，清空列表
    else:
        handedness = []
        data_points_4to8.clear()
        data_points_4to12.clear()


    # 调用 Monitor 方法在画面上标注左右手
    monitor.label_hands_on_feed(frame, results, handedness)
    
    # 摄像头镜像
    frame = cv2.flip(frame, 1)

    # 显示摄像头画面
    fps = 1 / (time.time() - start_time)  # 使用一次循环的时间计算帧率
    monitor.display_camera_feed(frame, hand_move_speed, fps, middle_finger_displacement)

    # 绘制图表
    graph_frame = np.zeros((800, 1200, 3), dtype=np.uint8)  # 调整高度为 800px
    monitor.display_graphs(graph_frame)
    cv2.imshow("Graph Monitor", graph_frame)

    # 检查退出条件
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()