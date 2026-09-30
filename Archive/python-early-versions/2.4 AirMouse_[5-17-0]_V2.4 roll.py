import cv2
import mediapipe as mp
import pyautogui
import math  # 用于计算距离
import time

# 初始化MediaPipe手部追踪模块
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 获取屏幕分辨率
screen_width, screen_height = pyautogui.size()

# 摄像头初始化
cap = cv2.VideoCapture(1)

# 定义扩展比例（扩大手部范围的映射区域）
extend_ratio_x = 3  # 水平方向扩展比例
extend_ratio_y = 3  # 垂直方向扩展比例

# 初始化平滑坐标的历史窗口
history = []
window_size = 3  # 平滑帧

# 左键右键相关变量
click_threshold_4to8 = 0.05  # 食指和拇指tip距离小于该值时触发点击
is_clicking_4to8 = False  # 当前鼠标是否处于按下状态
click_threshold_4to12 = 0.05  # 食指和中指tip距离小于该值时触发点击
is_clicking_4to12 = False  # 当前鼠标是否处于按下状态

# 滚动相关变量
scroll_threshold = 0.05  # 拇指和无名指tip距离小于该值时触发滚动
is_scrolling = False  # 当前是否处于滚动模式
initial_y = None  # 初始化纵坐标
last_y = None  # 记录上一帧的ring_finger的y坐标
scroll_speed = 0  # 当前滚动速度
last_scroll_time = 0  # 上次滚动时间
scroll_acceleration = 0  # 滚动加速度
scroll_inertia_decay = 0.95  # 惯性滚动的衰减因子
scroll_speed_text = "scroll_speed: N/A"
scroll_smoothness = 0.01  # 控制滚动的平滑度（更小的值会更平滑）

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

    # 距离显示变量初始化
    distance_4to8_text = "Distance: N/A"
    distance_4to12_text = "Distance: N/A"
    distance_4to16_text = "Distance: N/A"
    distance_4to20_text = "Distance: N/A"
    distance_8to12_text = "Distance: N/A"

    # 如果检测到手部
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            
            # 获取关节位置
            thumb_tip = hand_landmarks.landmark[4]          # 拇指
            index_finger_tip = hand_landmarks.landmark[8]   # 食指
            middle_finger_tip = hand_landmarks.landmark[12] # 中指
            ring_finger_tip = hand_landmarks.landmark[16]  # 食指PIP关节
            pinky_tip = hand_landmarks.landmark[20]         # 小指tip
            
            # 计算指尖之间的欧几里得距离
            distance_4to8 = math.sqrt((index_finger_tip.x - thumb_tip.x) ** 2 + 
                                 (index_finger_tip.y - thumb_tip.y) ** 2)
            distance_4to12 = math.sqrt((middle_finger_tip.x - thumb_tip.x) ** 2 + 
                                 (middle_finger_tip.y - thumb_tip.y) ** 2)
            distance_4to16 = math.sqrt((ring_finger_tip.x - thumb_tip.x) ** 2 +
                                 (ring_finger_tip.y - thumb_tip.y) ** 2)
            distance_4to20 = math.sqrt((pinky_tip.x - thumb_tip.x) ** 2 +
                                 (pinky_tip.y - thumb_tip.y) ** 2)
            distance_8to12 = math.sqrt((index_finger_tip.x - middle_finger_tip.x) ** 2 +
                                 (index_finger_tip.y - middle_finger_tip.y) ** 2)

            # 更新距离文本
            distance_4to8_text = f"{distance_4to8:.4f}"
            distance_4to12_text = f"{distance_4to12:.4f}"
            distance_4to16_text = f"{distance_4to16:.4f}"
            distance_4to20_text = f"{distance_4to20:.4f}"
            distance_8to12_text = f"{distance_8to12:.4f}"

            # 判断距离是否小于阈值
            # 左键单击和拖动（4to8）
            if distance_4to8 < click_threshold_4to8:
                if not is_clicking_4to8:  # 如果未触发单击
                    pyautogui.mouseDown()  # 按下左键
                    is_clicking_4to8 = True
            else:
                if is_clicking_4to8:  # 如果处于按下状态
                    pyautogui.mouseUp()  # 释放左键
                    is_clicking_4to8 = False  # 重置单击状态

            # 右键单击（4to12）
            if distance_4to12 < click_threshold_4to12:
                if not is_clicking_4to12:  # 如果未触发单击
                    pyautogui.click(button='right')  # 单击右键
                    is_clicking_4to12 = True
            else:
                is_clicking_4to12 = False  # 重置单击状态
                
            # 滚动逻辑
            if distance_4to16 < scroll_threshold:
                if not is_scrolling:
                    # 进入滚动模式，记录初始纵坐标
                    is_scrolling = True
                    initial_y = ring_finger_tip.y
                    scroll_speed = 0  # 重置滚动速度
                    last_scroll_time = time.time()  # 记录开始滚动的时间
                else:
                    # 获取当前纵坐标并计算滚动速度
                    current_y = ring_finger_tip.y
                    scroll_delta = (initial_y - current_y) * 100  # 放大滚动量
                    scroll_speed = scroll_delta  # 实时更新滚动速度
                    pyautogui.scroll(-int(scroll_delta)) #自然滚动，因此加了‘-’改变方向
                    initial_y = current_y  # 更新初始值
                    
                    # 计算滚动速度（速度 = 位移 / 时间）
                    current_time = time.time()
                    time_diff = current_time - last_scroll_time
                    if time_diff > 0:
                        scroll_speed = scroll_delta / time_diff  # 计算滚动速度       
            else:
                # 切换到惯性滚动模式
                is_scrolling = False

                # 惯性滚动处理
                if abs(scroll_speed) > 1:  # 如果速度大于1，则继续滚动
                    pyautogui.scroll(-int(scroll_speed * scroll_smoothness))
                    scroll_speed *= scroll_inertia_decay  # 按照衰减因子逐步减少速度
                    
            # 显示滚动速度
            if is_scrolling:
                scroll_speed_text = f"Speed: {scroll_speed:.2f}"
            else:
                scroll_speed_text = "Speed: none"

            # 计算几何中心
            norm_x = sum([hand_landmarks.landmark[i].x for i in [0, 5, 17]]) / 3
            norm_y = sum([hand_landmarks.landmark[i].y for i in [0, 5, 17]]) / 3
            
            # 扩展手部活动范围
            extended_x = max(0, min(1, (norm_x - 0.5) * extend_ratio_x + 0.5))
            extended_y = max(0, min(1, (norm_y - 0.5) * extend_ratio_y + 0.5))

            # 将归一化坐标映射到屏幕坐标
            x = int((1 - extended_x) * screen_width)  # 反转x坐标
            y = int(extended_y * screen_height)

            # 平滑处理鼠标移动
            history.append((x, y))
            if len(history) > window_size:
                history.pop(0)
            smooth_x, smooth_y = calculate_smooth_coordinates(history, window_size)

            # 如果不是滚动模式，则更新鼠标位置
            if not is_scrolling and smooth_x is not None and smooth_y is not None:
                pyautogui.moveTo(smooth_x, smooth_y)

                
    # 镜像摄像机
    frame = cv2.flip(frame, 1)
    
    # 根据是否按下左键或右键，更新显示的文本
    if is_clicking_4to8:
        distance_4to8_text = f"{distance_4to8:.2f} CLICK"
    elif is_clicking_4to8:
        distance_4to12_text = f"{distance_4to8:.2f} CLICK" 
    
    # 在帧的左下角绘制所有距离文本
    cv2.putText(frame, f"distance_1 = {distance_4to8_text}", (10, frame.shape[0] - 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"distance_2 = {distance_4to12_text}", (10, frame.shape[0] - 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"distance_3 = {distance_4to16_text}", (10, frame.shape[0] - 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"distance_4 = {distance_4to20_text}", (10, frame.shape[0] - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(frame, f"distance_5 = {distance_8to12_text}", (10, frame.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    
    # 在帧的左上角绘制滚动速度文本
    cv2.putText(frame, scroll_speed_text, (10, 30),  # Adjusted position here
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)

    # 显示图像
    cv2.imshow('Air Mouse', frame)

    # 退出条件
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放摄像头资源
cap.release()
cv2.destroyAllWindows()