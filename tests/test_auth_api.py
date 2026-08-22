"""认证模块 + 学习资源接口的端到端测试。

真起 FastAPI（TestClient），不桩掉路由层，也不需要 langgraph / qdrant / embedding，
因为这两个模块都不依赖它们。在项目根目录执行：

    python3.11 tests/test_auth_api.py

用户表写在临时文件里，不会污染 data/auth/users.json。
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from modules.common import errors as common_errors
from modules.auth.api import build_router as build_auth_router
from modules.auth.module import AuthModule
from modules.learning_resources.api import build_router as build_resource_router
from modules.learning_resources.module import LearningResourceModule

TMP_USERS = Path(tempfile.mkdtemp(prefix="auth-test-")) / "users.json"


def make_app():
    app = FastAPI()

    @app.exception_handler(common_errors.AppError)
    async def app_error_handler(_request: Request, exc: common_errors.AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message or exc.code, "retryable": exc.retryable},
        )

    auth_module = AuthModule(store_path=TMP_USERS, token_secret="test-secret", expose_code=True)
    app.include_router(build_auth_router(auth_module))
    app.include_router(
        build_resource_router(
            LearningResourceModule(ROOT / "data" / "learning_resources" / "resources.json")
        )
    )
    return app


client = TestClient(make_app(), raise_server_exceptions=False)
ok = 0


def check(label, condition, extra=""):
    global ok
    assert condition, f"FAIL: {label} {extra}"
    ok += 1
    print(f"  ok  {label}")


print("== 认证 ==")

# 演示账号已随模块初始化写入
r = client.post("/api/auth/login", json={"account": "demo@study.local", "password": "demo1234"})
check("体验账号可登录", r.status_code == 200, r.text)
demo = r.json()
check("返回 camelCase user", demo["user"]["userId"] == "demo_user", demo)
check("返回 token", isinstance(demo["token"], str) and "." in demo["token"])
demo_token = demo["token"]

# 大小写不敏感
r = client.post("/api/auth/login", json={"account": "DEMO@Study.Local", "password": "demo1234"})
check("邮箱大小写不敏感", r.status_code == 200, r.text)

# 错误密码
r = client.post("/api/auth/login", json={"account": "demo@study.local", "password": "wrong"})
check("错误密码 401", r.status_code == 401, r.text)
check("错误码 INVALID_CREDENTIALS", r.json()["code"] == "INVALID_CREDENTIALS", r.text)
check("失败不返回 404（否则前端会误判接口未实现）", r.status_code != 404)

# 不存在的账号：同样的错误码，不暴露账号是否注册
r = client.post("/api/auth/login", json={"account": "nobody@study.local", "password": "whatever"})
check("未注册账号返回同样的错误码", r.json()["code"] == "INVALID_CREDENTIALS", r.text)

# 注册
r = client.post("/api/auth/register", json={"nickname": "小明", "account": "ming@study.local", "password": "abcd1234"})
check("注册成功", r.status_code == 200, r.text)
token = r.json()["token"]
check("注册返回昵称", r.json()["user"]["nickname"] == "小明", r.text)

r = client.post("/api/auth/register", json={"nickname": "重复", "account": "ming@study.local", "password": "abcd1234"})
check("重复注册 409", r.status_code == 409 and r.json()["code"] == "ACCOUNT_EXISTS", r.text)

r = client.post("/api/auth/register", json={"nickname": "弱", "account": "weak@study.local", "password": "123"})
check("弱密码被拒", r.status_code == 400 and r.json()["code"] == "WEAK_PASSWORD", r.text)

# 密码不落明文
raw = TMP_USERS.read_text(encoding="utf-8")
check("用户表里没有明文密码", "abcd1234" not in raw and "demo1234" not in raw)
check("用户表里有盐", "password_salt" in raw)

# me
r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
check("/me 返回当前用户", r.status_code == 200 and r.json()["account"] == "ming@study.local", r.text)

r = client.get("/api/auth/me")
check("无令牌 401", r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED", r.text)

r = client.get("/api/auth/me", headers={"Authorization": "Bearer forged.signature"})
check("伪造令牌 401", r.status_code == 401, r.text)

# 篡改 payload
body, _, sig = token.rpartition(".")
r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body}x.{sig}"})
check("篡改 payload 被签名挡住", r.status_code == 401, r.text)

# 验证码登录
r = client.post("/api/auth/send-code", json={"account": "ming@study.local", "scene": "login"})
check("发送验证码", r.status_code == 200 and r.json()["sent"] is True, r.text)
dev_code = r.json()["devCode"]
check("开发模式直接返回验证码", isinstance(dev_code, str) and len(dev_code) == 6, r.text)
check("delivery 标注为 console", r.json()["delivery"] == "console", r.text)

r = client.post("/api/auth/login-code", json={"account": "ming@study.local", "code": "000000"})
check("错误验证码被拒", r.status_code == 400 and r.json()["code"] == "INVALID_CODE", r.text)

r = client.post("/api/auth/login-code", json={"account": "ming@study.local", "code": dev_code})
check("正确验证码可登录", r.status_code == 200, r.text)

r = client.post("/api/auth/login-code", json={"account": "ming@study.local", "code": dev_code})
check("验证码一次性失效", r.status_code == 400, r.text)

# 改资料
r = client.patch("/api/auth/profile", json={"nickname": "小明同学"}, headers={"Authorization": f"Bearer {token}"})
check("改昵称", r.status_code == 200 and r.json()["nickname"] == "小明同学", r.text)
r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
check("昵称已持久化", r.json()["nickname"] == "小明同学", r.text)

# 改密码
r = client.patch("/api/auth/password", json={"currentPassword": "nope", "newPassword": "newpass123"},
                 headers={"Authorization": f"Bearer {token}"})
check("原密码错误被拒", r.status_code == 401, r.text)

r = client.patch("/api/auth/password", json={"currentPassword": "abcd1234", "newPassword": "newpass123"},
                 headers={"Authorization": f"Bearer {token}"})
check("改密码 204", r.status_code == 204, r.text)

r = client.post("/api/auth/login", json={"account": "ming@study.local", "password": "newpass123"})
check("新密码可登录", r.status_code == 200, r.text)
r = client.post("/api/auth/login", json={"account": "ming@study.local", "password": "abcd1234"})
check("旧密码失效", r.status_code == 401, r.text)

# 登出
r = client.post("/api/auth/logout")
check("登出 204", r.status_code == 204, r.text)

# 体验账号不被覆盖：重建模块后昵称/密码仍然可用
client2 = TestClient(make_app(), raise_server_exceptions=False)
r = client2.post("/api/auth/login", json={"account": "demo@study.local", "password": "demo1234"})
check("重启后体验账号仍可登录且未被重复创建", r.status_code == 200 and r.json()["user"]["userId"] == "demo_user", r.text)
users = TMP_USERS.read_text(encoding="utf-8")
check("体验账号只有一条记录", users.count('"demo@study.local"') == 1)

print("== 学习资源 ==")
r = client.get("/api/learning-resources")
check("全量目录 200", r.status_code == 200, r.text)
items = r.json()["items"]
check("返回知识点条目", len(items) > 0, len(items))
total = sum(len(i["resources"]) for i in items)
print(f"       共 {len(items)} 个知识点 / {total} 条资源")
check("每条资源字段齐全", all(
    {"title", "platform", "url", "language", "kind", "note"} <= set(res)
    for i in items for res in i["resources"]))
check("URL 全部是 http(s)", all(res["url"].startswith("http") for i in items for res in i["resources"]))

first = items[0]["knowledgePointId"]
r = client.get(f"/api/learning-resources?knowledgePointIds={first}")
check("按单个知识点查询", r.status_code == 200 and len(r.json()["items"]) == 1, r.text)

r = client.get(f"/api/learning-resources?knowledgePointIds={first},{items[1]['knowledgePointId']}")
check("批量查询", len(r.json()["items"]) == 2, r.text)

r = client.get("/api/learning-resources?knowledgePointIds=kp-does-not-exist")
data = r.json()["items"]
check("未收录知识点返回空列表而不是报错", r.status_code == 200 and (not data or data[0]["resources"] == []), r.text)

print(f"\n全部通过：{ok} 项断言")
