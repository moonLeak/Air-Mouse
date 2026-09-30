import cv2
import mediapipe as mp
import pyautogui
from pynput.mouse import Controller as MouseController, Button
import math
import time
import csv
import os
import numpy as np
from collections import deque
global dominant_hand_label, secondary_hand_label, cam

# 初始化摄像头
cam = 1
cap = cv2.VideoCapture(cam)
WINDOW_NAME = "Air Mouse Camera Preview"

# 自定义主手,自动定义两一只手为次手
dominant_hand_label = "Right"
secondary_hand_label = "Left" if dominant_hand_label == "Right" else "Right"

# 初始化 MouseController
mouse = MouseController()

# 手部移动平滑算法参数
mouse_update_interval = 0.01  # 设置鼠标更新间隔时间，防止频繁更新
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
    
    @staticmethod
    def calculate_triangle_area(point1, point2, point3):
        """
        计算由三个点组成的三角形面积
        :param point1: 第一个点 (x, y)
        :param point2: 第二个点 (x, y)
        :param point3: 第三个点 (x, y)
        :return: 三角形面积
        """
        x1, y1 = point1
        x2, y2 = point2
        x3, y3 = point3

        # 使用叉积公式计算三角形面积
        area = 0.5 * abs(x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        return area

class DominantHand:
    class FourToEight:
        """
        检测拇指(4)和食指(8)的状态，实现点击、捏合和释放逻辑。
        """
        def __init__(self):
            self.is_holding = False  # 是否检测到手指接触
            self.is_pitching = False  # 是否正在进行捏合（长按）操作
            self.click_return_level = None  # 点击时的阈值
            self.release_return_level_up = None  # 释放时的上限阈值
            self.release_return_level_low = None  # 释放时的下限阈值
            self.release_return_level = None  # 综合释放阈值
            self.start_time = None  # 手势开始时间
            self.normalized_distance_window = deque(maxlen=5)  # 滑动窗口，存储最近5帧的归一化距离
            self.dynamic_line_history = deque(maxlen=300)  # 保存动态阈值曲线历史
            self.dynamic_threshold_low_history = deque(maxlen=300)
            self.dynamic_threshold_high_history = deque(maxlen=300)
            self.normalized_4to8_history = deque(maxlen=300)

        def detect_state(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
            """
            检测拇指和食指的接触状态，并返回对应操作（点击、捏合或释放）。
            """
            stability_duration = 0.25  # 稳定时间阈值，单位：秒
            stability_radius = 10  # 鼠标移动触发捏合的最小距离

            # 更新滑动窗口
            self.normalized_distance_window.append(normalized_distance)
            if len(self.normalized_distance_window) < self.normalized_distance_window.maxlen:
                return None  # 如果窗口不足，不进行判定

            # 动态阈值计算
            dynamic_line = np.median(self.normalized_distance_window)
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
                    self.start_time = time.time()
                    self.click_return_level = dynamic_threshold_low
                    self.release_return_level_up = dynamic_line
                    return None
            else:
                elapsed_time = time.time() - self.start_time

                if not self.is_pitching:
                    if elapsed_time <= stability_duration and normalized_distance > self.click_return_level:
                        self.is_holding = False
                        return 'click'  # 短按单击
                    elif (elapsed_time > stability_duration or
                          GeneralCalculation.calculate_distance(mouse_location_now, mouse_location_original) > stability_radius):
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
                        return 'release'  # 释放操作

            return None

        def get_state(self):
            return {
                "is_holding": self.is_holding,
                "is_pitching": self.is_pitching,
                "click_return_level": self.click_return_level,
                "release_return_level": self.release_return_level,
            }

        def perform_action(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
            action = self.detect_state(normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed)
            if action == 'click':
                mouse.click(Button.left)
            elif action == 'pitch':
                mouse.press(Button.left)
            elif action == 'release':
                mouse.release(Button.left)

    class FourToTwelve:
        """
        检测拇指(4)和中指(12)的状态，实现右键点击和滚动逻辑。
        """
        def __init__(self):
            self.is_holding = False
            self.is_pitching = False
            self.click_return_level = None
            self.release_return_level_up = None
            self.release_return_level_low = None
            self.release_return_level = None
            self.start_time = None
            self.normalized_distance_window = deque(maxlen=5)
            self.scroll_state = {"active": False, "speed_x": 0, "speed_y": 0, "initial_x": None, "initial_y": None}

        def detect_state(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
            stability_duration = 0.25
            stability_radius = 30

            self.normalized_distance_window.append(normalized_distance)
            if len(self.normalized_distance_window) < self.normalized_distance_window.maxlen:
                return None

            dynamic_line = np.median(list(self.normalized_distance_window))
            dynamic_threshold_low = dynamic_line - 0.15
            dynamic_threshold_high = dynamic_line + 0.15

            if not self.is_holding:
                if normalized_distance < dynamic_threshold_low:
                    self.is_holding = True
                    self.start_time = time.time()
                    self.click_return_level = dynamic_threshold_low
                    self.release_return_level_up = dynamic_line
                    self.scroll_state["initial_x"] = mouse_location_now[0]
                    self.scroll_state["initial_y"] = mouse_location_now[1]
                    return None
            else:
                elapsed_time = time.time() - self.start_time
                if not self.is_pitching:
                    if elapsed_time <= stability_duration and normalized_distance > self.click_return_level:
                        self.is_holding = False
                        return 'right_click'
                    elif (GeneralCalculation.calculate_distance(mouse_location_now, mouse_location_original) > stability_radius or elapsed_time > stability_duration):
                        self.is_pitching = True
                        self.release_return_level_low = dynamic_line
                        self.release_return_level = (
                            self.release_return_level_low +
                            (self.release_return_level_up - self.release_return_level_low) / 4
                        )
                        self.scroll_state["active"] = True
                        self.scroll_state["initial_y"] = mouse_location_now[1]
                        return 'scroll_start'
                else:
                    if normalized_distance > dynamic_threshold_high or dynamic_line > self.release_return_level:
                        if hand_move_speed > low_speed_threshold:
                            return None
                        self.is_holding = False
                        self.is_pitching = False
                        self.scroll_state["active"] = False
                        return 'release'
            return None

        def perform_action(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
            speedfactor = 0.5
            action = self.detect_state(normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed)

            if action == 'right_click':
                mouse.click(Button.right)
            elif action == 'scroll_start':
                self.scroll_state["active"] = True
                self.scroll_state["initial_x"] = mouse_location_now[0]
                self.scroll_state["initial_y"] = mouse_location_now[1]
            elif action == 'release':
                self.scroll_state["active"] = False

            if self.scroll_state["active"]:
                scroll_delta_y = (self.scroll_state["initial_y"] - mouse_location_now[1]) * speedfactor
                self.scroll_state["speed_y"] = scroll_delta_y
                mouse.scroll(0, -int(scroll_delta_y))
                self.scroll_state["initial_y"] = mouse_location_now[1]

    class Zooming:
        """
        双手缩放操作逻辑：通过两只手的三角形面积变化来检测缩放手势。
        """
        def __init__(self):
            self.is_zooming = False
            self.initial_area = None
            self.current_area = None

        def start_zoom(self, initial_area):
            self.is_zooming = True
            self.initial_area = initial_area

        def update_zoom(self, current_area):
            if not self.is_zooming or self.initial_area is None or self.initial_area == 0:
                return
            self.current_area = current_area
            zoom_ratio = (self.current_area - self.initial_area) / self.initial_area
            if zoom_ratio > 0.1:
                pyautogui.hotkey('command', '+')
            elif zoom_ratio < -0.1:
                pyautogui.hotkey('command', '-')

        def stop_zoom(self):
            self.is_zooming = False
            self.initial_area = None
            self.current_area = None

    class StateManager:
        """
        管理全局状态。
        """
        def __init__(self):
            self.states = {"is_zooming": False, "allow_other_operations": True}

        def set_state(self, key, value):
            self.states[key] = value

        def get_state(self, key):
            return self.states.get(key, None)

    class PerformAction:
        """
        整合各子类，执行相应操作。
        """
        def __init__(self, four_to_eight, four_to_twelve, zooming, state_manager):
            self.four_to_eight = four_to_eight
            self.four_to_twelve = four_to_twelve
            self.zooming = zooming
            self.state_manager = state_manager
            self.mouse_location_original = None

        def execute(self, normalized_distance_4to8, normalized_distance_4to12, triangle_area, hand_landmarks, screen_width, screen_height):
            """
            根据状态执行具体的操作：点击、捏合、滚动或缩放。
            """
            # 如果正在缩放，则暂停其他操作
            if self.state_manager.get_state("is_zooming"):
                if triangle_area is not None:
                    self.zooming.update_zoom(triangle_area)
                return

            mouse_location_now = mouse.position
            # 记录手势开始时的鼠标位置
            if self.mouse_location_original is None:
                self.mouse_location_original = mouse_location_now

            # 检测 4-8 的点击、捏合操作
            self.four_to_eight.perform_action(
                normalized_distance_4to8,
                mouse_location_now,
                self.mouse_location_original,
                hand_move_speed
            )

            # 检测 4-12 的滚动操作
            self.four_to_twelve.perform_action(
                normalized_distance_4to12,
                mouse_location_now,
                self.mouse_location_original,
                hand_move_speed
            )

            # 更新初始位置（手势未激活时）
            if not self.four_to_eight.is_holding and not self.four_to_twelve.is_holding:
                self.mouse_location_original = mouse_location_now

class SecondaryHand:
    class FourToEight:
        def __init__(self):
            # 初始化参数
            self.hand_label = secondary_hand_label
            self.is_holding = False  # 是否检测到手指接触
            self.is_pitching = False  # 是否正在进行捏合（长按）操作
            self.click_return_level = None  # 点击时的阈值
            self.release_return_level_up = None  # 释放时的上限阈值
            self.release_return_level_low = None  # 释放时的下限阈值
            self.release_return_level = None  # 综合释放阈值
            self.start_time = None  # 替代 frame_counter，用于记录手势开始时间
            self.normalized_distance_window = deque(maxlen=5)  # 滑动窗口，存储最近5帧的归一化距离
            self.dynamic_line_history = deque(maxlen=300)  # 保存动态阈值曲线历史
            self.dynamic_threshold_low_history = deque(maxlen=300)
            self.dynamic_threshold_high_history = deque(maxlen=300)
            self.normalized_4to8_history = deque(maxlen=300)

        def detect_finger_contact(self, normalized_distance, hand_move_speed):
            """检测手指接触状态并返回对应操作（点击、拖动或释放）"""
            stability_duration = 0.2  # 稳定时间阈值，单位：秒

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
                    self.start_time = time.time()  # 记录接触开始时间
                    self.click_return_level = dynamic_threshold_low
                    self.release_return_level_up = dynamic_line
                    return None
            else:
                elapsed_time = time.time() - self.start_time  # 计算持续时间
                if not self.is_pitching:
                    if elapsed_time <= stability_duration and normalized_distance > self.click_return_level:
                        self.is_holding = False
                        return 'click'  # 短按单击
                    elif elapsed_time > stability_duration:
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

        def perform_action(self, data, d_reference, hand_move_speed):
                """
                根据检测到的手势执行鼠标操作
                """
                t2, d2 = data[-1]
                normalized_distance = GeneralCalculation.calculate_normalized_distance(d2, d_reference)
                action = self.detect_finger_contact(normalized_distance, hand_move_speed)

                if action == 'click':
                    mouse.click(Button.left)  # 使用 pynput 左键单击
                elif action == 'pitch':
                    mouse.press(Button.left)  # 使用 pynput 按下左键
                elif action == 'release':
                    mouse.release(Button.left)  # 使用 pynput 松开左键

    class FourToTwelve:
        def __init__(self):
            # 初始化参数
            self.hand_label = secondary_hand_label
            self.is_holding = False  # 是否检测到手指接触
            self.is_pitching = False  # 是否正在进行捏合操作
            self.click_return_level = None  # 点击时的阈值
            self.release_return_level_up = None  # 释放时的上限阈值
            self.release_return_level_low = None  # 释放时的下限阈值
            self.release_return_level = None  # 综合释放阈值
            self.start_time = None  # 替代 frame_counter
            self.normalized_distance_window = deque(maxlen=5)  # 滑动窗口，存储最近5帧的归一化距离
            self.dynamic_line_history = deque(maxlen=300)  # 保存动态阈值曲线历史
            self.dynamic_threshold_low_history = deque(maxlen=300)
            self.dynamic_threshold_high_history = deque(maxlen=300)
            self.normalized_4to12_history = deque(maxlen=300)
            self.scroll_state = {"active": False, "speed_x": 0, "speed_y": 0, "initial_x": None, "initial_y": None}

        def detect_finger_contact(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
            """检测手指接触状态并返回对应操作（点击、滚动或释放）"""
            stability_duration = 0.25  # 稳定时间阈值，单位：秒
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
                    self.start_time = time.time()  # 记录接触开始时间
                    self.click_return_level = dynamic_threshold_low
                    self.release_return_level_up = dynamic_line
                    return None
            else:
                elapsed_time = time.time() - self.start_time  # 计算持续时间
                if not self.is_pitching:
                    if elapsed_time <= stability_duration and normalized_distance > self.click_return_level:
                        self.is_holding = False
                        return 'right_click'  # 单击右键
                    
                    elif (GeneralCalculation.calculate_distance(mouse_location_now, mouse_location_original) > stability_radius) or (elapsed_time > stability_duration): #移动超过范围=scroll # 超过两帧=scroll
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

        def perform_action(self, data, d_reference, mouse_location_now, mouse_location_original, hand_move_speed):
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

class Monitor:
    def __init__(self, frame_num_max=300, base_y=300, scale_factor=200, horizontal_scale=2, window_name="Air Mouse - Mediapipe Hands"):
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
        self.window_name = window_name

        # 初始化曲线数据
        self.curve_data = {
            "4to8": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
            "4to12": {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            },
        }

    def update_curve_data(self, key, dynamic_line, threshold_low, threshold_high, normalized):
        """
        更新曲线数据
        :param key: 数据类型的关键字 (4to8 或 4to12)
        :param dynamic_line: 动态线
        :param threshold_low: 低阈值
        :param threshold_high: 高阈值
        :param normalized: 归一化距离
        """
        self.curve_data[key]["dynamic_line"].append(dynamic_line)
        self.curve_data[key]["threshold_low"].append(threshold_low)
        self.curve_data[key]["threshold_high"].append(threshold_high)
        self.curve_data[key]["normalized"].append(normalized)

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
        在图表帧中绘制所有曲线
        :param graph_frame: 图表帧
        """
        height, width, _ = graph_frame.shape
        # 动态调整 base_y 以适应窗口大小
        base_y_4to8 = height // 2  # 顶部 1/4 区域
        base_y_4to12 = height // 1  # 底部 3/4 区域

        # 绘制 4to8 曲线
        self.draw_graph(graph_frame, self.curve_data["4to8"]["dynamic_line"], (105, 105, 105), base_y_4to8)
        self.draw_graph(graph_frame, self.curve_data["4to8"]["threshold_low"], (105, 105, 105), base_y_4to8)
        self.draw_graph(graph_frame, self.curve_data["4to8"]["threshold_high"], (105, 105, 105), base_y_4to8)
        self.draw_graph(graph_frame, self.curve_data["4to8"]["normalized"], (255, 255, 0), base_y_4to8)

        # 绘制 4to12 曲线
        self.draw_graph(graph_frame, self.curve_data["4to12"]["dynamic_line"], (105, 105, 105), base_y_4to12)
        self.draw_graph(graph_frame, self.curve_data["4to12"]["threshold_low"], (105, 105, 105), base_y_4to12)
        self.draw_graph(graph_frame, self.curve_data["4to12"]["threshold_high"], (105, 105, 105), base_y_4to12)
        self.draw_graph(graph_frame, self.curve_data["4to12"]["normalized"], (0, 0, 255), base_y_4to12)

    def display_hands(self, image, hand_landmarks, mp_hands, mp_drawing, label, cx, cy):
            """
            显示手部标签、关键点和画面
            :param image: 当前视频帧
            :param hand_landmarks: Mediapipe 检测到的手部关键点
            :param mp_hands: Mediapipe 手部模型
            :param mp_drawing: Mediapipe 绘图工具
            :param label: 手的标签（Dominant/Secondary）
            :param cx: 手掌根部 x 坐标
            :param cy: 手掌根部 y 坐标
            """
            # 在手掌根部绘制标签
            cv2.putText(image, label, (cx, cy - 20), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0, 255, 0), 2, cv2.LINE_AA)

            # 可视化关键点和连接
            mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 显示画面
            # cv2.imshow(WINDOW_NAME, image)

    def display_camera_feed(self, frame, hand_move_speed, fps):
        """
        显示摄像头画面，并标注手部移动速度、帧率和中指位移距离
        :param frame: 图像帧
        :param hand_move_speed: 手部移动速度
        :param fps: 当前帧率
        :param middle_finger_displacement: 中指位移距离 (像素)
        """
        cv2.putText(frame, f"Speed: {hand_move_speed:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        #cv2.imshow(WINDOW_NAME, frame)

    def log_data(self, time_stamp, action, normalized_4to8, normalized_4to12):
        """
        记录数据到日志
        :param time_stamp: 时间戳
        :param action: 触发的动作
        :param normalized_4to8: 4to8 的归一化数据
        :param normalized_4to12: 4to12 的归一化数据
        """
        self.data_log.append([time_stamp, action, normalized_4to8, normalized_4to12])

    def export_data(self):
        """
        导出数据到下载文件夹中的 CSV 文件
        """
        # 获取当前用户的下载目录
        downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        file_path = os.path.join(downloads_folder, "Monitor_data.csv")
        
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Action", "4to8 Normalized", "4to12 Normalized"])
            writer.writerows(self.data_log)
        print(f"Data exported to {file_path}")

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
        # 提取关键点的 x 和 y 坐标
        joint_indices = [0, 1, 2, 5, 13, 17]  # 手腕和手指根部的关键点
        joint_weights = [1, 1, 2, 8,  8, 5 ]   # 权重分配，手腕的权重更高

        # 使用加权平均计算手掌心的几何中心
        norm_x = sum(hand_landmarks.landmark[i].x * w for i, w in zip(joint_indices, joint_weights)) / sum(joint_weights)
        norm_y = sum(hand_landmarks.landmark[i].y * w for i, w in zip(joint_indices, joint_weights)) / sum(joint_weights)

        # 映射坐标范围并翻转 X 方向
        extended_x = max(0, min(1, (norm_x - 0.5) * self.extend_ratio_x + 0.5))
        extended_y = max(0, min(1, (norm_y - 0.5) * self.extend_ratio_y + 0.5))

        # 翻转 X 坐标方向
        x = int(extended_x * self.screen_width)  # 对 X 坐标翻转
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

class Patching:
    # 用于存储每只手的状态
    hand_states = {}

    @staticmethod
    def filter_duplicate_hands(hand_landmarks, handedness, max_hands=2, static_speed_threshold=20, static_time_threshold=5, screen_width=1920, screen_height=1080):
        """
        动态调整检测名额，剔除无效手（包括静止手和冗余手）。

        :param hand_landmarks: 检测到的所有手部关键点列表
        :param handedness: 每只手的左右标识列表
        :param max_hands: 最多保留的手数量
        :param static_speed_threshold: 判断手是否静止的速度阈值
        :param static_time_threshold: 判断手静止的时间阈值（秒）
        :param screen_width: 屏幕宽度
        :param screen_height: 屏幕高度
        :return: 一个列表，包含过滤后的有效手索引
        """
        # 存储每只手的信息
        hand_info = [
            {
                "label": handedness[i],
                "z": hand_landmarks[i].landmark[0].z,
                "index": i,
                "position": (hand_landmarks[i].landmark[0].x * screen_width,
                             hand_landmarks[i].landmark[0].y * screen_height),
                "speed": 0,
                "static_time": 0
            }
            for i in range(len(hand_landmarks))
        ]

        # 用于存储有效手的索引
        valid_indices = []

        # 分组手势
        hand_labels = [h["label"] for h in hand_info]
        left_count = hand_labels.count("Left")
        right_count = hand_labels.count("Right")

        for hand in hand_info:
            hand_id = f"{hand['label']}_{hand['index']}"  # 唯一标识手的 ID
            current_position = hand["position"]
            current_time = time.time()

            # 检查手是否有重复手
            has_duplicate = (hand["label"] == "Left" and left_count > 1) or \
                            (hand["label"] == "Right" and right_count > 1)

            # 检查历史状态
            if hand_id in Patching.hand_states:
                previous_state = Patching.hand_states[hand_id]
                previous_position = previous_state["position"]
                previous_time = previous_state["time"]

                # 计算速度
                hand["speed"] = GeneralCalculation.calculate_speed(
                    previous_position,
                    current_position,
                    previous_time
                )

                # 判断静止时间
                if hand["speed"] < static_speed_threshold:
                    hand["static_time"] = previous_state.get("static_time", 0) + (current_time - previous_time)
                else:
                    hand["static_time"] = 0  # 重置静止时间
            else:
                hand["static_time"] = 0  # 初始化静止时间

            # 更新手的状态
            Patching.hand_states[hand_id] = {"position": current_position, "time": current_time, "static_time": hand["static_time"]}

            # 判定有效手
            if has_duplicate or hand["static_time"] < static_time_threshold:
                valid_indices.append(hand["index"])

        # 按 Z 值排序，保留最近的手
        valid_hand_info = [hand for hand in hand_info if hand["index"] in valid_indices]
        valid_hand_info.sort(key=lambda x: -x["z"])

        # 按手标签分组，保留每种手中最近的一只
        final_indices = []
        left_hands = [h for h in valid_hand_info if h["label"] == "Left"]
        right_hands = [h for h in valid_hand_info if h["label"] == "Right"]
        if left_hands:
            final_indices.append(left_hands[0]["index"])
        if right_hands:
            final_indices.append(right_hands[0]["index"])

        # 返回有效手的索引
        return final_indices[:max_hands]

def main():
    # 初始化摄像头
    cap = cv2.VideoCapture(cam)
    
    # 初始化监控器
    monitor = Monitor()
    WINDOW_NAME = "Air Mouse Camera Preview"

    # MediaPipe 手部追踪模块配置
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    
    # 初始化屏幕和手部控制器
    screen_width, screen_height = pyautogui.size()
    hand_mouse_controller = HandMouseController(screen_width, screen_height)

    # 初始化主要手和次要手的操作类
    dominant_four_to_eight = DominantHand.FourToEight()
    dominant_four_to_twelve = DominantHand.FourToTwelve()
    dominant_zooming = DominantHand.Zooming()
    state_manager = DominantHand.StateManager()

    # 初始化 PerformAction
    perform_action = DominantHand.PerformAction(dominant_four_to_eight, dominant_four_to_twelve, dominant_zooming, state_manager)

    # 初始化通用变量
    last_update_time = time.time()
    previous_position = None

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as hands:
        while cap.isOpened():
            start_time = time.time()
            hand_move_speed = 0  # 初始化 hand_move_speed，防止未定义
            ret, frame = cap.read()
            if not ret:
                break

            # 翻转图像并转换为 RGB
            image = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
            image.flags.writeable = False

            # 进行手部检测
            results = hands.process(image)

            # 转换回 BGR 图像
            image.flags.writeable = True
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            if results.multi_hand_landmarks:
                # 提取手部关键点和左右手信息
                hand_landmarks = results.multi_hand_landmarks
                handedness = [h.classification[0].label for h in results.multi_handedness]

                for i, hand_landmark in enumerate(hand_landmarks):
                    hand_label = handedness[i]  # 获取当前手的标签（"Left" 或 "Right"）

                    # 定义手掌根部坐标，用于显示信息
                    landmark_0 = hand_landmark.landmark[0]
                    h, w, _ = image.shape
                    cx, cy = int(landmark_0.x * w), int(landmark_0.y * h)

                    # 判断是否是主要手
                    if hand_label == dominant_hand_label:
                        # 计算归一化距离
                        normalized_4to8 = GeneralCalculation.calculate_normalized_distance(
                            GeneralCalculation.calculate_distance(
                                hand_landmark.landmark[4],  # 拇指指尖
                                hand_landmark.landmark[8]   # 食指指尖
                            ),
                            GeneralCalculation.calculate_distance(
                                hand_landmark.landmark[0],  # 手腕
                                hand_landmark.landmark[5]   # 食指根部
                            )
                        )
                        normalized_4to12 = GeneralCalculation.calculate_normalized_distance(
                            GeneralCalculation.calculate_distance(
                                hand_landmark.landmark[4],  # 拇指指尖
                                hand_landmark.landmark[12]  # 中指指尖
                            ),
                            GeneralCalculation.calculate_distance(
                                hand_landmark.landmark[0],  # 手腕
                                hand_landmark.landmark[5]   # 食指根部
                            )
                        )

                        # 计算三角形面积（缩放）
                        triangle_area = GeneralCalculation.calculate_triangle_area(
                            (hand_landmark.landmark[0].x * screen_width, hand_landmark.landmark[0].y * screen_height),
                            (hand_landmark.landmark[5].x * screen_width, hand_landmark.landmark[5].y * screen_height),
                            (hand_landmark.landmark[17].x * screen_width, hand_landmark.landmark[17].y * screen_height)
                        )

                        # 获取鼠标位置并计算速度
                        x, y = hand_mouse_controller.process_hand_movement(hand_landmark)
                        hand_move_speed = hand_mouse_controller.calculate_hand_move_speed((x, y), last_update_time)
                        last_update_time = time.time()

                        # 平滑鼠标位置
                        smooth_x, smooth_y = hand_mouse_controller.smooth_mouse_position(x, y, hand_move_speed)
                        if state_manager.get_state("allow_other_operations"):
                            hand_mouse_controller.move_mouse(smooth_x, smooth_y)

                        # 执行 DominantHand 的操作
                        perform_action.execute(
                            normalized_4to8,
                            normalized_4to12,
                            triangle_area,
                            hand_landmark,  # 当前手的关键点
                            screen_width,
                            screen_height
                        )

                        # 在画面中标注主要手的操作信息
                        monitor.display_hands(image, hand_landmark, mp_hands, mp_drawing, "Dominant", cx, cy)

            # 计算 FPS
            fps = 1 / (time.time() - start_time)

            # 显示摄像头画面
            monitor.display_camera_feed(image, hand_move_speed, fps)
            cv2.imshow(WINDOW_NAME, image)

            # 按下 'q' 键退出程序
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()