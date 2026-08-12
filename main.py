import asyncio
import logging
from argparse import ArgumentParser, Namespace

from bootstrap.demo_runtime import run_diagnosis_demo
from bootstrap.web_runtime import serve_web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> Namespace:
    parser = ArgumentParser(description="Study Companion 前后端启动入口")
    parser.add_argument("--demo", action="store_true", help="运行诊断工作流示例")
    parser.add_argument("--host", default="127.0.0.1", help="服务监听地址")
    parser.add_argument("--backend-port", type=int, default=8000, help="Python API 端口")
    parser.add_argument("--frontend-port", type=int, default=5173, help="Vite 前端端口")
    parser.add_argument("--mock-api", action="store_true", help="前端使用 Mock API")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.demo:
            asyncio.run(run_diagnosis_demo())
            return 0
        return serve_web(args.host, args.backend_port, args.frontend_port, not args.mock_api)
    except Exception:
        logger.exception("study companion terminated because startup or workflow failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
