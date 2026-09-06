from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from threading import Thread

import uvicorn

from api.server import create_app
from bootstrap.application import build_api_dependencies
from modules.common.config import Settings

logger = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_DIR / "front" / "frontend"


def wait_for_backend(host: str, port: int, timeout_seconds: float = 10) -> None:
    """Wait for Uvicorn's socket before allowing the browser to issue requests."""

    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((probe_host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"后端 API 未在 {timeout_seconds:g} 秒内启动：{probe_host}:{port}")


def start_frontend(host: str, port: int, use_real_api: bool, api_base_url: str) -> subprocess.Popen[str]:
    if not (FRONTEND_DIR / "node_modules").exists():
        raise RuntimeError("前端依赖尚未安装，请先在 front/frontend 运行 pnpm install。")
    node = shutil.which("node") or shutil.which("node.exe")
    vite_entry = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    vite_compatibility = FRONTEND_DIR / "scripts" / "vite-windows-safe-realpath.cjs"
    if not node:
        raise RuntimeError("未找到 Node.js，请先安装 Node.js。")
    if not vite_entry.is_file():
        raise RuntimeError("未找到本地 Vite，请先在 front/frontend 运行 pnpm install。")

    environment = os.environ.copy()
    environment["VITE_USE_REAL_API"] = "true" if use_real_api else "false"
    # Vite is a standalone development server here, not a reverse proxy. Point
    # it at Uvicorn; material-QA itself carries the /api/rag route prefix.
    # Keep browser requests same-origin (5173 -> /api).  Vite proxies them to
    # Uvicorn, avoiding the intermittent cross-port/CORS fetch failure that
    # occurred after restarts when the browser called 8001 directly.
    environment["VITE_API_BASE_URL"] = "/api"
    environment["VITE_BACKEND_API_TARGET"] = api_base_url
    command = [node, "--require", str(vite_compatibility), str(vite_entry), "--host", host, "--port", str(port)]
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
        # 后端线程的 bind 与前端首屏请求存在竞态；先探测端口就绪再打开浏览器。
        wait_for_backend(host, backend_port)
        logger.info("启动后端 API: http://%s:%s", host, backend_port)
        api_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        frontend = start_frontend(host, frontend_port, use_real_api, f"http://{api_host}:{backend_port}")
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
        backend_thread.join(timeout=5)
        dependencies.close()
