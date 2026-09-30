import cv2
import mediapipe as mp
import numpy as np

# 定义平面计算函数
def calculate_plane(points):
    p1, p2, p3 = points
    v1 = np.array(p2) - np.array(p1)
    v2 = np.array(p3) - np.array(p1)
    normal = np.cross(v1, v2)  # 计算法向量
    a, b, c = normal
    d = -np.dot(normal, p1)  # 平面方程常数项
    return a, b, c, d

def calculate_distance_to_camera(hand_landmark):
    """
    计算手的距离（以手掌根 landmark[0] 为参考）
    """
    return hand_landmark.landmark[0].z  # 直接返回 Z 值作为距离

# 初始化 Mediapipe
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# 打开摄像头
cap = cv2.VideoCapture(0)
with mp_hands.Hands(static_image_mode=False, max_num_hands=4, min_detection_confidence=0.5, min_tracking_confidence=0.5) as hands:
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # 翻转图像并转换为 RGB
        image = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
        image.flags.writeable = False

        # 进行手部检测
        results = hands.process(image)

        # 转换回 BGR 图像以供显示
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks
            handedness = [h.classification[0].label for h in results.multi_handedness]

            # 用于存储各手的 Z 值和索引
            hand_info = [
                {"label": handedness[i], "z": calculate_distance_to_camera(hand_landmarks[i]), "index": i}
                for i in range(len(hand_landmarks))
            ]

            # 检测重复手
            labels = [h["label"] for h in hand_info]
            duplicate_labels = {label for label in labels if labels.count(label) > 1}

            # 保留最近的手，停止识别较远的重复手
            valid_indices = set(range(len(hand_landmarks)))
            for label in duplicate_labels:
                same_label_hands = [h for h in hand_info if h["label"] == label]
                same_label_hands.sort(key=lambda x: -x["z"])  # 按 Z 值排序，越小越近, "-"用于调转远近关系
                for h in same_label_hands[1:]:  # 保留最近的一只手，其余标记为无效
                    valid_indices.discard(h["index"])

            # 只绘制有效手
            for i in valid_indices:
                mp_drawing.draw_landmarks(image, hand_landmarks[i], mp_hands.HAND_CONNECTIONS)

            # 显示调试信息
            for i, hand in enumerate(hand_info):
                status = "Valid" if i in valid_indices else "Ignored"
                cv2.putText(image, f"Hand {i + 1}: {hand['label']}, Z: {hand['z']:.4f}, {status}",
                            (10, 30 + i * 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 显示画面
        cv2.imshow("Hand Distance Test", image)
        if cv2.waitKey(1) & 0xFF == 27:  # 按 Esc 退出
            break

cap.release()
cv2.destroyAllWindows()