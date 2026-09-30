import cv2
import mediapipe as mp
import numpy as np
import time
import matplotlib.pyplot as plt

# 初始化 MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_drawing = mp.solutions.drawing_utils

# 定义关键点对
keypoint_pairs = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 9), (0, 13),
    (0, 17), (1, 5), (1, 9), (1, 13), (1, 17)
]

# 存储每对关键点对的距离列表
distance_data = {pair: [] for pair in keypoint_pairs}

# 打开摄像头
cap = cv2.VideoCapture(1)
start_time = time.time()

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        continue

    # 镜像翻转并转换颜色
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 使用 MediaPipe 处理帧
    results = hands.process(rgb_frame)
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # 计算所有关键点对的距离
            for pair in keypoint_pairs:
                p1 = hand_landmarks.landmark[pair[0]]
                p2 = hand_landmarks.landmark[pair[1]]
                distance = np.sqrt(
                    (p1.x - p2.x) ** 2 +
                    (p1.y - p2.y) ** 2 +
                    (p1.z - p2.z) ** 2
                )
                distance_data[pair].append(distance)

    # 可视化手部
    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

    # 显示实时视频
    cv2.imshow("Hand Tracking", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()

# 分析每对关键点的 max-min 稳定性
stability_scores = {}
for pair, distances in distance_data.items():
    if len(distances) > 1:
        stability_scores[pair] = max(distances) - min(distances)

# 排序并打印稳定性排名
sorted_stability = sorted(stability_scores.items(), key=lambda x: x[1])
print("\nStability Rankings (from most stable to least stable):")
for rank, (pair, stability) in enumerate(sorted_stability, start=1):
    print(f"{rank}. Pair {pair}: Stability (max-min) = {stability:.6f}")

# 可视化稳定性排名
pairs = [str(pair) for pair, _ in sorted_stability]
scores = [stability for _, stability in sorted_stability]

plt.figure(figsize=(12, 6))
plt.barh(pairs, scores, color='skyblue')
plt.xlabel('Stability (max-min)')
plt.ylabel('Keypoint Pairs')
plt.title('Stability Rankings of Keypoint Pairs')
plt.gca().invert_yaxis()  # 反转 y 轴以从上到下显示稳定性排名
plt.show()