from __future__ import annotations

from types import SimpleNamespace

from bootstrap import web_runtime


def test_frontend_proxy_uses_selected_backend_port(tmp_path, monkeypatch) -> None:
    frontend_dir = tmp_path / "frontend"
    (frontend_dir / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(web_runtime, "FRONTEND_DIR", frontend_dir)
    monkeypatch.setattr(
        web_runtime.shutil,
        "which",
        lambda name: "/usr/bin/pnpm" if name == "pnpm" else None,
    )
    captured = {}

    def fake_popen(command, *, cwd, env, text):
        captured.update(command=command, cwd=cwd, env=env, text=text)
        return SimpleNamespace()

    monkeypatch.setattr(web_runtime.subprocess, "Popen", fake_popen)

    process = web_runtime.start_frontend(
        "0.0.0.0",
        5199,
        True,
        backend_port=8765,
    )

    assert isinstance(process, SimpleNamespace)
    assert captured["cwd"] == frontend_dir
    assert captured["env"]["VITE_API_BASE_URL"] == "/api"
    assert captured["env"]["VITE_BACKEND_URL"] == "http://127.0.0.1:8765"
    assert captured["command"][-4:] == ["--host", "0.0.0.0", "--port", "5199"]
