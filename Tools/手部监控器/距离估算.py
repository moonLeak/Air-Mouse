import cv2
import mediapipe as mp
import numpy as np

# 初始化 Mediapipe
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

# 校准数据
calibrated_pixel_distance = None  # 两个关节点的像素距离 (需要校准)
calibrated_physical_distance = 30.0  # 物理距离 (单位: cm)

def calculate_distance(pixel_distance):
    """
    将像素距离映射为物理距离。
    """
    if calibrated_pixel_distance is None:
        return None
    # 比例换算公式
    return (calibrated_physical_distance * calibrated_pixel_distance) / pixel_distance

def get_pixel_distance(landmark1, landmark2, width, height):
    """
    计算两个 Mediapipe 关键点的像素距离。
    """
    x1, y1 = int(landmark1.x * width), int(landmark1.y * height)
    x2, y2 = int(landmark2.x * width), int(landmark2.y * height)
    return np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

# 打开摄像头
cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("无法读取摄像头")
        break

    # 转换颜色空间为RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 处理图像并获取手部关键点
    result = hands.process(frame_rgb)

    # 获取图像大小
    height, width, _ = frame.shape

    if result.multi_hand_landmarks:
        for hand_landmarks in result.multi_hand_landmarks:
            # 绘制手部关键点和连线
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            # 获取关节点 0 和 5 的像素距离
            landmark_0 = hand_landmarks.landmark[mp_hands.HandLandmark.WRIST]
            landmark_5 = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_MCP]
            pixel_distance = get_pixel_distance(landmark_0, landmark_5, width, height)

            if calibrated_pixel_distance is None:
                # 提示校准
                cv2.putText(frame, "Calibrate: Hold hand at 8cm and press 'c'", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                # 计算物理距离
                physical_distance = calculate_distance(pixel_distance)
                cv2.putText(frame, f"Distance: {physical_distance:.2f} cm", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    # 显示图像
    cv2.imshow("Distance Estimation", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):  # 按 'q' 键退出
        break
    elif key == ord('c') and result.multi_hand_landmarks:
        # 校准：记录像素距离
        calibrated_pixel_distance = pixel_distance
        print(f"Calibrated pixel distance: {calibrated_pixel_distance}")

# 释放资源
cap.release()
cv2.destroyAllWindows()
hands.close()