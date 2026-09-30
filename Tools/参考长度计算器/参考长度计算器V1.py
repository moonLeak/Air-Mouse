
import mediapipe as mp
import numpy as np
from collections import defaultdict

# 初始化 MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)

# 定义候选关键点对
candidates = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 9), (0, 13),
    (0, 17), (1, 5), (1, 9), (1, 13), (1, 17)
]

# 距离历史数据和帧间变化量
distance_history = defaultdict(list)
variation_std = {}

# 距离计算函数
def calculate_distance(point1, point2):
    return np.sqrt(
        (point1.x - point2.x) ** 2 +
        (point1.y - point2.y) ** 2 +
        (point1.z - point2.z) ** 2
    )

# 摄像头初始化
cap = cv2.VideoCapture(1)

try:
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            continue

        # 转换为 RGB 图像
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # 获取手部关键点
        result = hands.process(frame_rgb)

        if result.multi_hand_landmarks:
            for hand_landmarks in result.multi_hand_landmarks:
                # 计算每对候选点的距离
                for pair in candidates:
                    dist = calculate_distance(
                        hand_landmarks.landmark[pair[0]],
                        hand_landmarks.landmark[pair[1]]
                    )
                    # 记录历史数据
                    if distance_history[pair]:
                        variation = abs(dist - distance_history[pair][-1])
                    else:
                        variation = 0
                    distance_history[pair].append(dist)

                # 计算每对候选点的帧间变化量标准差
                for pair in candidates:
                    if len(distance_history[pair]) > 1:
                        variation_std[pair] = np.std(np.diff(distance_history[pair]))

                # 排序并显示最稳定的点对
                sorted_variation = sorted(variation_std.items(), key=lambda x: x[1])
                print("\n=== Stability Ranking ===")
                for rank, (pair, std_dev) in enumerate(sorted_variation, start=1):
                    print(f"{rank}. Pair {pair[0]}-{pair[1]}: StdDev = {std_dev:.6f}")

        # 显示视频
        cv2.imshow("Hand Tracking", frame)

        # 按 ESC 退出
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()

    # 最终结果
    print("\n=== Final Stability Ranking ===")
    for rank, (pair, std_dev) in enumerate(sorted(variation_std.items(), key=lambda x: x[1]), start=1):
        print(f"{rank}. Pair {pair[0]}-{pair[1]}: StdDev = {std_dev:.6f}")
