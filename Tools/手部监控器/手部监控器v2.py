import cv2
import mediapipe as mp

# 初始化 Mediapipe
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# 自定义主手
dominant_hand = "Left" 
secondary_hand = "Left" if dominant_hand == "Right" else "Right"

# 打开摄像头
cap = cv2.VideoCapture(0)
with mp_hands.Hands(static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5) as hands:

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
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # 获取左右手信息
                hand_label = handedness.classification[0].label  # "Left" 或 "Right"

                # 判断是主手还是次手
                if hand_label == dominant_hand:
                    label = f"{hand_label}-Dominant"
                else:
                    label = f"{hand_label}-Secondary"

                # 获取手掌根部关键点的坐标 (landmark 0)
                landmark_0 = hand_landmarks.landmark[0]
                h, w, _ = image.shape
                cx, cy = int(landmark_0.x * w), int(landmark_0.y * h)

                # 在手掌根部绘制标签
                cv2.putText(image, label, (cx, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 
                            1, (0, 255, 0), 2, cv2.LINE_AA)

                # 可视化关键点和连接
                mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS)

        # 显示画面
        cv2.imshow('Mediapipe Hands', image)
        if cv2.waitKey(1) & 0xFF == 27:  # 按 Esc 退出
            break

cap.release()
cv2.destroyAllWindows()