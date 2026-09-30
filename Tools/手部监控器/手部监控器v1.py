import cv2
import mediapipe as mp
import time
import math

# 初始化 MediaPipe 手部追踪模块
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands()
7

# 设置自定义阈值（单位：像素）
distance_thresholds = {
    'thumb': 50,  # 拇指
    'index': 50,  # 食指
    'middle': 50, # 中指
    'ring': 50,   # 无名指
    'pinky': 50   # 小指
}

# 上一次拇指与食指接触的时间
last_touch_time = None

# 计算两点之间的欧几里得距离
def calculate_distance(point1, point2):
    return math.sqrt((point2[0] - point1[0]) ** 2 + (point2[1] - point1[1]) ** 2)

# 检测拇指与食指的接触
def check_thumb_index_touch(thumb_tip, index_tip):
    global last_touch_time
    distance = calculate_distance(thumb_tip, index_tip)
    if distance < distance_thresholds['thumb'] and last_touch_time is None:
        last_touch_time = time.time()  # 记录接触时间
    return distance

# 显示接触时间
def display_touch_time(frame, last_touch_time):
    if last_touch_time:
        elapsed_time = time.time() - last_touch_time
        cv2.putText(frame, f"Last touch time: {elapsed_time:.2f}s", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    else:
        cv2.putText(frame, "No touch detected", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

# 主循环
cap = cv2.VideoCapture(0)

while True:
    success, frame = cap.read()
    if not success:
        break

    # 镜像翻转
    frame = cv2.flip(frame, 1)

    # 转换为 RGB 格式并传入 Hand Detection 模型
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(frame_rgb)

    # 如果检测到手
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # 绘制手部关键点
            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 获取指尖位置
            thumb_tip = (hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP].x * frame.shape[1],
                         hand_landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP].y * frame.shape[0])

            index_tip = (hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP].x * frame.shape[1],
                         hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP].y * frame.shape[0])

            middle_tip = (hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].x * frame.shape[1],
                          hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP].y * frame.shape[0])

            ring_tip = (hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP].x * frame.shape[1],
                        hand_landmarks.landmark[mp_hands.HandLandmark.RING_FINGER_TIP].y * frame.shape[0])

            pinky_tip = (hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP].x * frame.shape[1],
                         hand_landmarks.landmark[mp_hands.HandLandmark.PINKY_TIP].y * frame.shape[0])

            # 计算并显示指尖之间的距离
            thumb_index_distance = calculate_distance(thumb_tip, index_tip)
            index_middle_distance = calculate_distance(index_tip, middle_tip)
            middle_ring_distance = calculate_distance(middle_tip, ring_tip)
            ring_pinky_distance = calculate_distance(ring_tip, pinky_tip)

            cv2.putText(frame, f"Thumb-Index distance: {thumb_index_distance:.2f}px", (20, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
            cv2.putText(frame, f"Index-Middle distance: {index_middle_distance:.2f}px", (20, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"Middle-Ring distance: {middle_ring_distance:.2f}px", (20, 250),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            cv2.putText(frame, f"Ring-Pinky distance: {ring_pinky_distance:.2f}px", (20, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

            # 检查拇指与食指的接触
            thumb_index_distance = check_thumb_index_touch(thumb_tip, index_tip)

            # 显示接触时间
            display_touch_time(frame, last_touch_time)

    # 显示图像
    cv2.imshow("Hand Tracking", frame)

    # 按 'esc' 键退出
    if cv2.waitKey(1) & 0xFF == 27:
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()