import pyautogui
import time

def perform_zoom(zoom_ratio):
    """
    根据缩放比例执行放大或缩小操作
    :param zoom_ratio: 缩放比例，大于1放大，小于1缩小
    """
    if zoom_ratio > 1.0:
        steps = int((zoom_ratio - 1.0) * 10)  # 放大步数
        for _ in range(steps):
            pyautogui.hotkey('ctrl', '+')
            time.sleep(0.1)  # 每次操作间隔，模拟人类操作
    elif zoom_ratio < 1.0:
        steps = int((1.0 - zoom_ratio) * 10)  # 缩小步数
        for _ in range(steps):
            pyautogui.hotkey('ctrl', '-')
            time.sleep(0.1)

# 测试用例
if __name__ == "__main__":
    print("测试开始，按Ctrl+C退出")
    
    # 模拟不同的缩放比例
    zoom_ratios = [1.5, 1.2, 0.8, 0.5]  # 放大和缩小比例
    for zoom in zoom_ratios:
        print(f"执行缩放: 比例 {zoom}")
        perform_zoom(zoom)
        time.sleep(2)  # 每次缩放后暂停观察效果+=+