import cv2
import mediapipe as mp
import numpy as np

# 定义平面计算函数
def calculate_plane(points):
    """
    通过三个点计算平面方程的法向量和常数项
    :param points: 三个点 [(x1, y1, z1), (x2, y2, z2), (x3, y3, z3)]
    :return: 平面方程的系数 (a, b, c, d)
    """
    p1, p2, p3 = points
    v1 = np.array(p2) - np.array(p1)
    v2 = np.array(p3) - np.array(p1)
    normal = np.cross(v1, v2)  # 计算法向量
    a, b, c = normal
    d = -np.dot(normal, p1)  # 平面方程常数项
    return a, b, c, d

def calculate_distance_to_plane(plane, point):
    """
    计算点到平面的距离
    :param plane: 平面方程的系数 (a, b, c, d)
    :param point: 点的坐标 (x, y, z)
    :return: 点到平面的距离
    """
    a, b, c, d = plane
    x, y, z = point
    return abs(a * x + b * y + c * z + d) / np.sqrt(a**2 + b**2 + c**2)

# 初始化 Mediapipe
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# 打开摄像头
cap = cv2.VideoCapture(0)
with mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5, min_tracking_confidence=0.5) as hands:
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

        # 初始化距离显示变量
        tip_to_own_palm = "N/A"
        tip_to_other_palm = "N/A"
        tip_to_tip_plane = "N/A"

        if results.multi_hand_landmarks and len(results.multi_hand_landmarks) >= 2:
            hand_landmarks = results.multi_hand_landmarks
            handedness = [h.classification[0].label for h in results.multi_handedness]

            # 提取左手和右手的关键点
            left_hand = hand_landmarks[handedness.index("Left")] if "Left" in handedness else None
            right_hand = hand_landmarks[handedness.index("Right")] if "Right" in handedness else None

            if right_hand:
                # 右手手掌平面
                right_hand_points = [
                    [right_hand.landmark[0].x, right_hand.landmark[0].y, right_hand.landmark[0].z],
                    [right_hand.landmark[5].x, right_hand.landmark[5].y, right_hand.landmark[5].z],
                    [right_hand.landmark[17].x, right_hand.landmark[17].y, right_hand.landmark[17].z],
                ]
                right_hand_plane = calculate_plane(right_hand_points)

                # 右手食指tip与右手掌平面的相对距离
                right_tip = [right_hand.landmark[8].x, right_hand.landmark[8].y, right_hand.landmark[8].z]
                tip_to_own_palm = calculate_distance_to_plane(right_hand_plane, right_tip)

                # 右手食指tip与左手掌平面的相对距离
                if left_hand:
                    left_hand_points = [
                        [left_hand.landmark[0].x, left_hand.landmark[0].y, left_hand.landmark[0].z],
                        [left_hand.landmark[5].x, left_hand.landmark[5].y, left_hand.landmark[5].z],
                        [left_hand.landmark[17].x, left_hand.landmark[17].y, left_hand.landmark[17].z],
                    ]
                    left_hand_plane = calculate_plane(left_hand_points)
                    tip_to_other_palm = calculate_distance_to_plane(left_hand_plane, right_tip)

                # 右手食指tip与自身tip平面的距离（参考tip平面）
                tip_plane_points = [
                    [right_hand.landmark[8].x, right_hand.landmark[8].y, right_hand.landmark[8].z],
                    [right_hand.landmark[7].x, right_hand.landmark[7].y, right_hand.landmark[7].z],
                    [right_hand.landmark[6].x, right_hand.landmark[6].y, right_hand.landmark[6].z],
                ]
                tip_plane = calculate_plane(tip_plane_points)
                tip_to_tip_plane = calculate_distance_to_plane(tip_plane, right_tip)

        # 显示计算结果
        cv2.putText(image, f"Tip-To-Own-Palm: {tip_to_own_palm if isinstance(tip_to_own_palm, str) else f'{tip_to_own_palm:.4f}'}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(image, f"Tip-To-Other-Palm: {tip_to_other_palm if isinstance(tip_to_other_palm, str) else f'{tip_to_other_palm:.4f}'}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(image, f"Tip-To-Tip-Plane: {tip_to_tip_plane if isinstance(tip_to_tip_plane, str) else f'{tip_to_tip_plane:.4f}'}", 
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # 可视化手部关键点和连接
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # 显示画面
        cv2.imshow("Hand Distance Test", image)
        if cv2.waitKey(1) & 0xFF == 27:  # 按 Esc 退出
            break

cap.release()
cv2.destroyAllWindows()