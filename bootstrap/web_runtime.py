from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from threading import Thread

import uvicorn

from api.server import create_app
from bootstrap.application import build_api_dependencies
from modules.common.config import Settings

logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_DIR / "front" / "frontend"


def start_frontend(host: str, port: int, use_real_api: bool) -> subprocess.Popen[str]:
    package_manager = shutil.which("pnpm") or shutil.which("pnpm.cmd") or shutil.which("npm") or shutil.which("npm.cmd")
    if not package_manager:
        raise RuntimeError("未找到 pnpm 或 npm，请先安装 Node.js。")
    if not (FRONTEND_DIR / "node_modules").exists():
        raise RuntimeError("前端依赖尚未安装，请先在 front/frontend 运行 pnpm install。")

    environment = os.environ.copy()
    environment["VITE_USE_REAL_API"] = "true" if use_real_api else "false"
    environment["VITE_API_BASE_URL"] = "/api"
    command = [package_manager, "run", "dev", "--", "--host", host, "--port", str(port)]
    logger.info("启动前端: http://%s:%s", host, port)
    return subprocess.Popen(command, cwd=FRONTEND_DIR, env=environment, text=True)




def serve_web(host: str | None = None, backend_port: int | None = None, frontend_port: int | None = None, use_real_api: bool | None = None) -> int:
    settings = Settings.from_env()
    host = host or settings.host
    backend_port = backend_port or settings.backend_port
    frontend_port = frontend_port or settings.frontend_port
    use_real_api = settings.use_real_api if use_real_api is None else use_real_api
    if not FRONTEND_DIR.is_dir():
        raise FileNotFoundError(f"前端目录不存在: {FRONTEND_DIR}")

    dependencies = build_api_dependencies(settings)
    try:
        logger.info("正在预热资料问答 Embedding 模型和 Qdrant 客户端……")
        dependencies.start()
        logger.info("资料问答资源预热完成。")
    except Exception:
        dependencies.close()
        logger.exception("资料问答资源预热失败，后端未启动。")
        raise
    backend = uvicorn.Server(
        uvicorn.Config(
            create_app(dependencies),
            host=host,
            port=backend_port,
            log_level="info",
        )
    )
    backend_thread = Thread(target=backend.run, name="api-server", daemon=True)
    backend_thread.start()
    frontend: subprocess.Popen[str] | None = None
    try:
        logger.info("启动后端 API: http://%s:%s", host, backend_port)
        frontend = start_frontend(host, frontend_port, use_real_api)
        logger.info("前后端已启动，按 Ctrl+C 停止。")
        frontend.wait()
        return frontend.returncode or 0
    except KeyboardInterrupt:
        logger.info("正在停止前后端服务……")
        return 0
    finally:
        if frontend is not None and frontend.poll() is None:
            frontend.terminate()
            try:
                frontend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend.kill()
        backend.should_exit = True
        # LLM 请求的默认超时为 120 秒；先等在途请求退出，再关闭
        # checkpoint/DB，避免活跃请求拿到已关闭资源。
        backend_thread.join(timeout=130)
        if backend_thread.is_alive():
            logger.error("后端未在宽限期内退出，正在强制停止。")
            backend.force_exit = True
            backend_thread.join(timeout=10)
        if backend_thread.is_alive():
            logger.error("后端仍有在途请求，为避免关闭活跃资源，交由进程退出时回收。")
        else:
            dependencies.close()
