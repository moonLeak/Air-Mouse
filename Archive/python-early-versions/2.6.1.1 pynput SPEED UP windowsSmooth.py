import cv2
import mediapipe as mp
import pyautogui
from pynput.mouse import Controller as MouseController, Button  # type: ignore
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
cap = cv2.VideoCapture(1)

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 比例映射参数设置
extend_ratio_x, extend_ratio_y = 2.5, 2.5  # 手部范围扩展比例

# 手部移动平滑算法参数
# 手部移动平滑算法参数
mouse_update_interval = 0.03  # 设置鼠标更新间隔时间
low_speed_threshold = 200  # 低速阈值
position_window = deque(maxlen=10)  # 定义滑动窗口，最多存储 10 个位置
window_size = 3  # 动态窗口初始大小

# 所有手指共享参数(Globle)
hand_move_speed = 0  # 初始化hand_move_speed

class GeneralCalculation:
    @staticmethod
    def calculate_distance(point1, point2):
        """
        计算两点的欧几里得距离
        """
        return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)

    @staticmethod
    def calculate_speed(previous_position, current_position, last_update_time):
        """
        计算两点间的移动速度
        """
        if previous_position is None:
            return 0  # 初始速度为 0

        # 计算两点间距离和时间差
        distance = GeneralCalculation.calculate_distance(previous_position, current_position)
        time_diff = max(time.time() - last_update_time, 1e-6)  # 确保时间差不为零
        return distance / time_diff

    @staticmethod
    def adjust_window_size(speed, current_window_size, min_size=3, max_size=10, threshold=200):
        """
        根据速度动态调整平滑窗口大小
        """
        if speed > threshold:  # 高速时减小窗口大小
            return max(min_size, current_window_size - 1)
        else:  # 低速时增大窗口大小
            return min(max_size, current_window_size + 1)

    @staticmethod
    def smooth_position(history, x, y, window_size):
        """
        使用加权平均法平滑坐标
        """
        history.append((x, y))
        if len(history) > window_size:
            history.popleft()

        smooth_x = sum(pos[0] for pos in history) / len(history)
        smooth_y = sum(pos[1] for pos in history) / len(history)

        return smooth_x, smooth_y

class FourToEight:
    def __init__(self):
        # 初始化参数
        self.is_holding = False  # 是否检测到手指接触
        self.is_pitching = False  # 是否正在进行捏合（长按）操作
        self.click_return_level = None  # 点击时的阈值
        self.release_return_level_up = None  # 释放时的上限阈值
        self.release_return_level_low = None  # 释放时的下限阈值
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
        dynamic_threshold_low = dynamic_line - 0.1
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
        self.scroll_state = {"active": False, "speed": 0, "initial_y": None}  # 滚动状态

    def calculate_normalized_distance(self, d_finger_tip, d_reference):
        """计算归一化的手指距离"""
        return d_finger_tip / d_reference

    def detect_finger_contact(self, normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed):
        """检测手指接触状态并返回对应操作（点击、滚动或释放）"""
        stability_frames = 1  # 判断为长按需要持续的时间/帧
        stability_radius = 10  # 鼠标移动触发滚动的最小距离

        # 更新滑动窗口
        self.normalized_distance_window.append(normalized_distance)
        if len(self.normalized_distance_window) < self.normalized_distance_window.maxlen:
            return None  # 如果窗口不足，不进行判定

        # 动态阈值计算
        dynamic_line = np.median(list(self.normalized_distance_window))
        dynamic_threshold_low = dynamic_line - 0.1
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
                if self.frame_counter <= stability_frames and normalized_distance > self.click_return_level:
                    self.is_holding = False
                    return 'right_click'  # 单击右键
                elif self.frame_counter > stability_frames:
                    self.is_pitching = True
                    self.release_return_level_low = dynamic_line
                    self.release_return_level = (
                        self.release_return_level_low +
                        (self.release_return_level_up - self.release_return_level_low) / 4
                    )
                    # 判断滚动
                    if self.calculate_distance(mouse_location_now, mouse_location_original) > stability_radius:
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

    def calculate_distance(self, point1, point2):
        """计算两点的欧几里得距离"""
        return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)

    def perform_action(self, data, d_reference, mouse_location_now, mouse_location_original, hand_move_speed):
            """
            根据检测到的手势执行鼠标操作
            """
            t2, d2 = data[-1]
            normalized_distance = GeneralCalculation.calculate_normalized_distance(d2, d_reference)
            action = self.detect_finger_contact(normalized_distance, mouse_location_now, mouse_location_original, hand_move_speed)

            if action == 'right_click':
                mouse.click(Button.right)  # 使用 pynput 右键单击
            elif action == 'scroll_start':
                self.scroll_state["active"] = True
            elif action == 'release':
                self.scroll_state["active"] = False  # 停止滚动

    def perform_scrolling(self, initial_y, current_y, smoothness, decay):
        """
        使用 pynput 实现滚动和惯性滚动
        """
        if self.scroll_state["active"]:
            # 计算滚动增量
            scroll_delta = (initial_y - current_y) * 100
            self.scroll_state["speed"] = scroll_delta
            mouse.scroll(0, -int(scroll_delta))  # 使用 pynput 执行滚动
            self.scroll_state["initial_y"] = current_y
        else:
            # 惯性滚动
            if abs(self.scroll_state["speed"]) > 1:
                mouse.scroll(0, -int(self.scroll_state["speed"] * smoothness))  # 平滑滚动
                self.scroll_state["speed"] *= decay  # 逐渐减小滚动速度

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

    def display_camera_feed(self, frame, hand_move_speed, fps):
        """
        显示摄像头画面，并标注手部移动速度和帧率
        :param frame: 图像帧
        :param hand_move_speed: 手部移动速度
        :param fps: 当前帧率
        """
        cv2.putText(frame, f"Speed: {hand_move_speed:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.imshow("Camera Feed", frame)

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
    def __init__(self, screen_width, screen_height, extend_ratio_x=2.5, extend_ratio_y=2.5):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.extend_ratio_x = extend_ratio_x
        self.extend_ratio_y = extend_ratio_y
        self.previous_position = None
        self.position_history = deque(maxlen=10)
        self.window_size = 3  # 初始窗口大小

    def process_hand_movement(self, hand_landmarks):
        """
        映射手部坐标到屏幕坐标
        """
        x_values_trimmed = sorted([hand_landmarks.landmark[i].x for i in [0, 1, 2, 5, 9, 13, 17]])[1:-1]
        y_values_trimmed = sorted([hand_landmarks.landmark[i].y for i in [0, 1, 2, 5, 9, 13, 17]])[1:-1]
        weights = [3, 2, 1, 1, 1]
        norm_x = sum(x * w for x, w in zip(x_values_trimmed, weights[1:-1])) / sum(weights[1:-1])
        norm_y = sum(y * w for y, w in zip(y_values_trimmed, weights[1:-1])) / sum(weights[1:-1])

        extended_x = max(0, min(1, (norm_x - 0.5) * self.extend_ratio_x + 0.5))
        extended_y = max(0, min(1, (norm_y - 0.5) * self.extend_ratio_y + 0.5))

        x = int((1 - extended_x) * self.screen_width)  # 反转 x 坐标
        y = int(extended_y * self.screen_height)
        return x, y

    def smooth_mouse_position(self, x, y, hand_move_speed):
        """
        动态调整窗口大小并平滑手部坐标
        """
        # 动态调整窗口大小
        self.window_size = GeneralCalculation.adjust_window_size(
            speed=hand_move_speed,
            current_window_size=self.window_size,
            min_size=3,
            max_size=10,
            threshold=low_speed_threshold
        )

        # 平滑坐标
        smooth_x, smooth_y = GeneralCalculation.smooth_position(self.position_history, x, y, self.window_size)
        return int(smooth_x), int(smooth_y)

    def calculate_hand_move_speed(self, current_position, last_update_time):
        """
        计算手部移动速度
        """
        speed = GeneralCalculation.calculate_speed(self.previous_position, current_position, last_update_time)
        self.previous_position = current_position
        return speed

    def move_mouse(self, smooth_x, smooth_y):
        """
        移动鼠标
        """
        mouse.position = (smooth_x, smooth_y)

# 初始化必要的类
monitor = Monitor(frame_num_max=300, base_y=300, scale_factor=300, horizontal_scale=2)
hand_mouse_controller = HandMouseController(screen_width, screen_height)

four_to_eight = FourToEight()
four_to_twelve = FourToTwelve()

last_update_time = time.time()  # 上次鼠标位置更新时间
previous_position = None        # 开始之前清空鼠标位置
data_points_4to8 = []           # 存储4to8的实时数据
data_points_4to12 = []          # 存储4to12的实时数据

# 初始化 Monitor
monitor = Monitor(frame_num_max=300, base_y=300, scale_factor=200, horizontal_scale=3)

while cap.isOpened():
    start_time = time.time()
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
            # 映射手部到屏幕坐标
            x, y = hand_mouse_controller.process_hand_movement(hand_landmarks)

            # 计算手部移动速度
            hand_move_speed = hand_mouse_controller.calculate_hand_move_speed((x, y), last_update_time)
            last_update_time = time.time()

            # 平滑鼠标位置并移动鼠标
            smooth_x, smooth_y = hand_mouse_controller.smooth_mouse_position(x, y, hand_move_speed)
            hand_mouse_controller.move_mouse(smooth_x, smooth_y)

            # 计算手指距离
            thumb_tip = hand_landmarks.landmark[4]
            index_finger_tip = hand_landmarks.landmark[8]
            middle_finger_tip = hand_landmarks.landmark[12]
            distance_4to8 = GeneralCalculation.calculate_distance(thumb_tip, index_finger_tip)
            reference_distance_4to8 = GeneralCalculation.calculate_distance(
                hand_landmarks.landmark[3], hand_landmarks.landmark[7]
            )
            distance_4to12 = GeneralCalculation.calculate_distance(thumb_tip, middle_finger_tip)
            reference_distance_4to12 = GeneralCalculation.calculate_distance(
                hand_landmarks.landmark[3], hand_landmarks.landmark[11]
            )

            # 归一化距离计算
            normalized_4to8 = GeneralCalculation.calculate_normalized_distance(distance_4to8, reference_distance_4to8)
            normalized_4to12 = GeneralCalculation.calculate_normalized_distance(distance_4to12, reference_distance_4to12)

            # 更新动作
            data_points_4to8.append((time.time(), distance_4to8))
            four_to_eight.perform_action(data_points_4to8, reference_distance_4to8, hand_move_speed)

            data_points_4to12.append((time.time(), distance_4to12))
            four_to_twelve.perform_action(data_points_4to12, reference_distance_4to12, (smooth_x, smooth_y), previous_position, hand_move_speed)

            # 更新曲线数据
            monitor.update_curve_data(
                "4to8",
                four_to_eight.dynamic_line_history[-1] if four_to_eight.dynamic_line_history else 0,
                four_to_eight.dynamic_threshold_low_history[-1] if four_to_eight.dynamic_threshold_low_history else 0,
                four_to_eight.dynamic_threshold_high_history[-1] if four_to_eight.dynamic_threshold_high_history else 0,
                normalized_4to8
            )
            monitor.update_curve_data(
                "4to12",
                four_to_twelve.dynamic_line_history[-1] if four_to_twelve.dynamic_line_history else 0,
                four_to_twelve.dynamic_threshold_low_history[-1] if four_to_twelve.dynamic_threshold_low_history else 0,
                four_to_twelve.dynamic_threshold_high_history[-1] if four_to_twelve.dynamic_threshold_high_history else 0,
                normalized_4to12
            )

            # 记录数据
            action = "action_placeholder"  # 替换为实际动作
            monitor.log_data(time.time(), action, normalized_4to8, normalized_4to12)



    # 摄像头镜像
    frame = cv2.flip(frame, 1)

    # 显示摄像头画面
    fps = 1 / (time.time() - start_time) # 使用一次循环的时间计算帧率
    monitor.display_camera_feed(frame, hand_move_speed, fps)

    # 绘制图表
    graph_frame = np.zeros((800, 1200, 3), dtype=np.uint8)  # 调整高度为 800px
    monitor.display_graphs(graph_frame)
    cv2.imshow("Graph Monitor", graph_frame)

    # 检查退出条件
    if cv2.waitKey(1) & 0xFF == 27:
        break

# 程序结束后询问是否导出数据
# if input("Export data? (y/n): ").lower() == "y":
#     monitor.export_data()

cap.release()
cv2.destroyAllWindows()