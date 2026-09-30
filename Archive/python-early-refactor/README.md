# Air Mouse Project

## 项目结构
- `archive/`：历史版本与参考脚本的归档。
- `src/airmouse/`：当前主程序源码，入口为 `main.py`。
- `tests/`：预留的测试目录（空）。
- `.venv/`：本地虚拟环境目录（不提交到版本库）。
- `requirements.txt`：第三方依赖清单。

## 本地环境搭建
1. **创建并激活虚拟环境**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. **安装第三方依赖**
   ```bash
   pip install -r requirements.txt
   ```
3. **（可选）验证语法**
   ```bash
   python -m compileall src/airmouse
   ```

## 运行方式
- 激活虚拟环境后执行：
  ```bash
  python -m airmouse
  ```
- 程序会打开摄像头并开始捕捉手势。按 `Esc` 退出。

## 后续建议
- 将常量抽离到独立的 `config` 模块，方便调参。
- 在 `tests/` 中使用 `pytest` 编写关键算法的单元测试。
- 使用 `git` 管理代码历史，保留精简后的主分支。
