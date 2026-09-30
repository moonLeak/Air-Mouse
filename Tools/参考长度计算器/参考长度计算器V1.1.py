import cv2
import mediapipe as mp
import numpy as np

# 初始化 MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)

# 推荐的参考点对
reference_pairs = [(9, 13), (13, 17), (5, 9)]

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
    print("正在实时计算参考长度 (按 ESC 键退出程序)...\n")

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
                # 计算参考点对的长度
                reference_lengths = []
                for pair in reference_pairs:
                    dist = calculate_distance(
                        hand_landmarks.landmark[pair[0]],
                        hand_landmarks.landmark[pair[1]]
                    )
                    reference_lengths.append(dist)

                # 计算参考长度的平均值
                average_reference_length = np.mean(reference_lengths)
                print(f"参考长度 (归一化基准): {average_reference_length:.6f}")

        # 显示视频
        cv2.imshow("手部关键点追踪", frame)

        # 按 ESC 键退出
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("\n程序已结束。")