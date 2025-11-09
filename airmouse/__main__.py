import os

# 确保在没有手动 export 时也禁用 GPU（避免崩溃）
os.environ.setdefault("MEDIAPIPE_DISABLE_GPU", "1")

from .main import main

if __name__ == "__main__":
    main()
