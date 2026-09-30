import cv2
import subprocess
import threading

def start_camera_stream(camera_id, port):
    """
    通过 ADB 控制安卓手机启动摄像头，并推送到指定的端口。
    """
    adb_command = f"adb shell am start -a android.media.action.VIDEO_CAMERA --ei android.intent.extra.CAMERA_FACING {camera_id}"
    subprocess.run(adb_command, shell=True)
    # 推送流到 RTSP 服务 (需要配合手机端流媒体工具)

def display_rtsp_stream(rtsp_url, window_name):
    """
    用 OpenCV 显示 RTSP 流。
    """
    cap = cv2.VideoCapture(rtsp_url)
    while True:
        ret, frame = cap.read()
        if ret:
            cv2.imshow(window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    # 启动两个摄像头
    camera_threads = [
        threading.Thread(target=start_camera_stream, args=(0, 4747)),  # 主摄像头
        threading.Thread(target=start_camera_stream, args=(1, 4748)),  # 副摄像头
    ]
    
    for t in camera_threads:
        t.start()
    
    # 显示两个 RTSP 流
    rtsp_streams = [
        threading.Thread(target=display_rtsp_stream, args=("rtsp://localhost:4747", "Camera 1")),
        threading.Thread(target=display_rtsp_stream, args=("rtsp://localhost:4748", "Camera 2")),
    ]
    
    for t in rtsp_streams:
        t.start()

    for t in camera_threads + rtsp_streams:
        t.join()