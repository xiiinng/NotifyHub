"""端到端冒烟验证：注册 -> 登录 -> 模板 -> 通知 -> Celery 处理 -> 用户隔离。

用法：
    python scripts/smoke_test.py --base-url http://localhost:8000
    python scripts/smoke_test.py --base-url http://localhost:3000 --include-failure

注意：服务端需要设置 ALLOW_FAILURE_SIMULATION=true 才能演示失败重试。
"""

import argparse
import json
import time
import uuid
import urllib.error
import urllib.request


class SmokeFailure(AssertionError):
    pass


class Client:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read().decode()
            return error.code, json.loads(raw) if raw else {}

    def expect(self, method, path, status, body=None):
        code, payload = self.request(method, path, body)
        if code != status:
            raise SmokeFailure(f"{method} {path} 期望 {status}，实际 {code}: {payload}")
        return payload


def wait_terminal(client: Client, notification_id: int, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.expect("GET", f"/api/v1/notifications/{notification_id}", 200)
        if payload["status"] in ("success", "failed"):
            return payload
        time.sleep(0.5)
    raise SmokeFailure(f"通知 {notification_id} 在 {timeout}s 内未完成")


def register_and_login(base_url: str, prefix: str) -> Client:
    client = Client(base_url)
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "Passw0rd123"
    client.expect(
        "POST",
        "/api/v1/auth/register",
        201,
        {"username": prefix, "email": email, "password": password},
    )
    token = client.expect(
        "POST", "/api/v1/auth/login", 200, {"email": email, "password": password}
    )
    client.token = token["access_token"]
    return client


def run(base_url: str, include_failure: bool) -> None:
    print(f"[1/8] 健康检查 {base_url}")
    anonymous = Client(base_url)
    anonymous.expect("GET", "/health", 200)

    print("[2/8] 未登录访问 /auth/me 应返回 401")
    anonymous.expect("GET", "/api/v1/auth/me", 401)

    print("[3/8] 注册并登录用户 A")
    alice = register_and_login(base_url, "alice")
    profile = alice.expect("GET", "/api/v1/auth/me", 200)
    assert profile["email"].startswith("alice_"), profile

    print("[4/8] 创建模板并使用模板发送通知")
    template = alice.expect(
        "POST",
        "/api/v1/templates",
        201,
        {"name": f"welcome-{uuid.uuid4().hex[:6]}", "title": "欢迎", "content": "模板快照内容"},
    )
    notification = alice.expect(
        "POST", "/api/v1/notifications", 201, {"template_id": template["id"]}
    )
    result = wait_terminal(alice, notification["id"])
    if result["status"] != "success":
        raise SmokeFailure(f"模板通知应成功，实际 {result}")
    if result["title"] != "欢迎" or result["content"] != "模板快照内容":
        raise SmokeFailure("通知内容快照不正确")

    print("[5/8] 手动发送通知")
    manual = alice.expect(
        "POST",
        "/api/v1/notifications",
        201,
        {"title": "手动通知", "content": "手动内容"},
    )
    manual_result = wait_terminal(alice, manual["id"])
    if manual_result["status"] != "success":
        raise SmokeFailure(f"手动通知应成功，实际 {manual_result}")

    if include_failure:
        print("[6/8] 演示失败重试（需要服务端 ALLOW_FAILURE_SIMULATION=true）")
        failing = alice.expect(
            "POST",
            "/api/v1/notifications",
            201,
            {"title": "失败演示", "content": "boom [FAIL]"},
        )
        failed = wait_terminal(alice, failing["id"], timeout=120)
        if failed["status"] != "failed":
            raise SmokeFailure(f"失败演示最终应为 failed，实际 {failed}")
        print(f"      最终状态={failed['status']} retry_count={failed['retry_count']}")
    else:
        print("[6/8] 跳过失败演示（可加 --include-failure）")

    print("[7/8] 用户 B 无法访问用户 A 的数据")
    bob = register_and_login(base_url, "bob")
    bob.expect("GET", f"/api/v1/notifications/{notification['id']}", 404)
    bob.expect("GET", f"/api/v1/templates/{template['id']}", 404)
    bob.expect(
        "POST", "/api/v1/notifications", 404, {"template_id": template["id"]}
    )
    bob_list = bob.expect("GET", "/api/v1/notifications?page=1&page_size=10", 200)
    if bob_list["total"] != 0:
        raise SmokeFailure(f"用户 B 不应看到通知，实际 {bob_list['total']}")

    print("[8/8] 分页与状态筛选")
    alice_page = alice.expect(
        "GET", "/api/v1/notifications?page=1&page_size=1&status=success", 200
    )
    if alice_page["total"] < 2 or len(alice_page["items"]) != 1:
        raise SmokeFailure(f"分页结果不正确: {alice_page}")

    print("\n全部冒烟检查通过 ✅")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="后端或前端地址"
    )
    parser.add_argument(
        "--include-failure", action="store_true", help="额外验证失败重试链路"
    )
    args = parser.parse_args()

    try:
        run(args.base_url, args.include_failure)
    except SmokeFailure as error:
        raise SystemExit(f"\n冒烟检查失败 ❌ {error}")


if __name__ == "__main__":
    main()
