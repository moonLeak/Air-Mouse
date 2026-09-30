import cv2
import numpy as np

# 棋盘格尺寸
chessboard_size = (9, 6)  # 9x6的棋盘格

# 打开摄像头1（默认摄像头）
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("无法打开摄像头")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("无法读取摄像头图像")
        break

    # 转为灰度图
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # 查找棋盘格角点
    ret, corners = cv2.findChessboardCorners(gray, chessboard_size)

    if ret:
        # 如果找到角点，绘制它们
        cv2.drawChessboardCorners(frame, chessboard_size, corners, ret)

    # 显示结果
    cv2.imshow('Chessboard Detection', frame)

    # 按 'q' 键退出
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 释放资源
cap.release()
cv2.destroyAllWindows()