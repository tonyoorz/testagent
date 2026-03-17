#!/usr/bin/env python3
"""
Playwright Cookie 管理器
=======================

这个脚本使用 Playwright 自动打开 Chromium 浏览器，
登录 Octane 并把取得的 cookie 保存到 `cookie.txt`。

与原先的 selenium_cookie_manager.py 不同，
Playwright 可以更容易运行 headless/headful 并在需要时
提示用户手工完成认证。适用于需要企业内网访问的场景。

使用：
    python playwright_cookie_manager.py            # 交互菜单
    python playwright_cookie_manager.py --refresh  # 立即刷新 cookie
    python playwright_cookie_manager.py --check    # 检查 cookie 有效性

依赖：
    pip install playwright requests
    playwright install chromium

登录信息文件示例 (login_info.txt)：
    {"username": "user", "password": "secret"}

"""

import json
import os
import sys
import logging
import time
from datetime import datetime

# optional network helper
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    logging.warning("urllib3 未安装，某些网络警告可能无法被禁用。请运行 `pip install urllib3` 安装。")

try:
    import requests
except ImportError:
    requests = None
    logging.warning("requests 模块不可用，请运行 `pip install requests` 来启用 cookie 验证。")

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# constants
BASE_URL = "https://octane-prod.bmwgroup.net"
LOGIN_INFO_FILE = "login_info.txt"
COOKIE_FILE = "cookie.txt"
LOG_FILE = "playwright_cookie_manager.log"


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


class PlaywrightCookieManager:
    def __init__(self):
        setup_logging()
        self.login_info = None

    def load_login_info(self):
        if not os.path.exists(LOGIN_INFO_FILE):
            logging.error(f"登录信息文件 {LOGIN_INFO_FILE} 不存在")
            return False
        try:
            with open(LOGIN_INFO_FILE, 'r', encoding='utf-8') as f:
                self.login_info = json.load(f)
            if not self.login_info.get('username') or not self.login_info.get('password'):
                logging.error("登录信息中缺少 username 或 password")
                return False
            logging.info("登录信息加载成功")
            return True
        except Exception as e:
            logging.error(f"解析登录信息失败: {e}")
            return False

    def save_cookie(self, cookie_string):
        try:
            # simply overwrite the existing cookie file, no backups
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                    old = f.read().strip()
                # optional: log diff for debugging
                if old and old != cookie_string:
                    old_set = set(old.split('; '))
                    new_set = set(cookie_string.split('; '))
                    added = new_set - old_set
                    removed = old_set - new_set
                    if added:
                        logging.info(f"新增cookie条目: {added}")
                    if removed:
                        logging.info(f"移除cookie条目: {removed}")
            with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                f.write(cookie_string)
            logging.info(f"新 cookie 写入 {COOKIE_FILE}")
            return True
        except Exception as e:
            logging.error(f"cookie 保存失败: {e}")
            return False

    def get_cookie_via_playwright(self, headless=False):
        """使用 Playwright 打开浏览器并登录获取 cookie"""
        if not self.load_login_info():
            return None

        logging.info("启动 Playwright 浏览器...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox"])
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            try:
                page.goto(BASE_URL, timeout=60000)
            except PWTimeout:
                logging.warning("页面打开超时，请确认网络/VPN 是否连通")
            except Exception as e:
                # 例如 DNS 解析失败
                logging.error(f"导航失败: {e}")
                print("✗ 无法访问 Octane，请检查网络和 VPN（需在企业内网下）")
                browser.close()
                return None

            # 如果自动重定向到登录页面，等待输入框出现
            try:
                page.wait_for_selector("input[type='text'], input[type='email'], input[name*='user']", timeout=15000)
            except PWTimeout:
                # 没有检测到登录框，可能已经需要人工登录
                pass

            # 尝试填入用户名并提交
            if self.login_info:
                try:
                    page.fill("input[name='username'], input[type='email'], input[type='text']", self.login_info['username'])
                    logging.info("填入用户名")
                except Exception:
                    pass
                # 提交用户名（按钮或回车）
                try:
                    page.click("button[type=submit], input[type=submit]")
                    logging.info("尝试点击登录按钮 (用户名提交)")
                except Exception:
                    try:
                        # 回车作为兜底
                        page.keyboard.press("Enter")
                    except Exception:
                        pass

                # 等待密码框或认证下拉/下一个按钮出现
                try:
                    page.wait_for_selector("input[name='password'], input[type='password'], select, button:has-text('NEXT')", timeout=20000)
                except PWTimeout:
                    logging.info("等待密码页面/认证方式超时，可能需要手动完成登录")

                # 连续点击所有 NEXT 按钮直到出现密码输入框
                start_time = time.time()
                while True:
                    if time.time() - start_time > 60:
                        logging.warning("多次点击 NEXT 后仍未出现密码输入框")
                        break
                    # 检查密码框是否已出现
                    pw_field = page.query_selector("input[name='password'], input[type='password']")
                    if pw_field:
                        break

                    # 直接点击 NEXT，如果存在
                    clicked = False
                    for sel in [
                        "button:has-text('NEXT')",
                        "button:has-text('Next')",
                        "input[type='submit']:has-text('NEXT')",
                        "input[type='submit']:has-text('Next')",
                        "text=NEXT",
                        "text=Next"
                    ]:
                        try:
                            nxt = page.query_selector(sel)
                            if nxt:
                                nxt.click()
                                logging.info(f"点击 {sel} 按钮")
                                clicked = True
                                time.sleep(1)
                                break
                        except Exception:
                            continue
                    if clicked:
                        continue

                    time.sleep(1)

                # 填入密码并提交
                try:
                    page.fill("input[name='password'], input[type='password']", self.login_info['password'])
                    logging.info("填入密码")
                except Exception:
                    pass
                try:
                    page.click("button[type=submit], input[type=submit]")
                    logging.info("尝试点击提交密码按钮")
                except Exception:
                    pass

            # 等待跳转到主界面或手动完成登录
            try:
                # 等待页面完成加载或跳转，最长60秒
                page.wait_for_load_state('networkidle', timeout=60000)
                # 有时 URL 保持不变，只要出现非登录界面的元素即可
                current = page.url
                if BASE_URL in current and 'login' not in current.lower():
                    logging.info("跳转到登录后页面")
                else:
                    logging.info(f"页面 URL: {current} (含 login 字段)，但已达到 networkidle")
                
            except PWTimeout:
                logging.warning("等待页面加载超时，继续并尝试获取 cookie")

            # 给浏览器一点时间来设置 cookie（无论是否跳转）
            time.sleep(5)

            # 如果需要精确获得头部中的 cookie，可发起一次 API 请求并拦截
            cookie_header = None
            def handle_route(route, request):
                nonlocal cookie_header
                if 'cookie' in request.headers:
                    cookie_header = request.headers['cookie']
                route.continue_()

            # 拦截任意 shared_spaces API 请求
            context.route("**/api/shared_spaces/**", handle_route)
            try:
                # 发一个简单请求以触发拦截
                page.goto(f"{BASE_URL}/api/shared_spaces/1002/workspaces/2001/defects?limit=1", timeout=30000)
            except Exception:
                pass

            cookies = context.cookies()
            if not cookies and not cookie_header:
                logging.error("没有获取到任何 cookie")
                browser.close()
                return None

            # 先尝试使用拦截到的 header
            if cookie_header:
                logging.info(f"拦截到请求头 cookie: {cookie_header}")
                cookie_str = cookie_header
            else:
                # 回退到从 context.cookies 获取
                filtered = [c for c in cookies if 'octane-prod.bmwgroup.net' in c.get('domain','')]
                if filtered:
                    logging.info(f"从 {len(cookies)} 总cookie中筛选出了 {len(filtered)} 个 Octane 相关 cookie")
                    cookies = filtered
                else:
                    logging.info("未筛选到特定域名cookie，使用全部抓取结果")
                for c in cookies:
                    logging.info(f"cookie: {c['name']}={c['value']}")
                cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

            browser.close()
            logging.info(f"最终 cookie 字符串长度 {len(cookie_str)}")
            return cookie_str

    def validate_cookie(self, cookie_string=None):
        if not requests:
            logging.error("缺少 requests 模块，无法验证 cookie")
            return False
        if not cookie_string:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                    cookie_string = f.read().strip()
            else:
                return False
        if not cookie_string:
            return False
        try:
            sess = requests.Session()
            sess.verify = False
            sess.headers.update({
                "User-Agent": "Mozilla/5.0",
            })
            # 拆分并设置到 cookie jar（避免requests自动域匹配问题）
            for pair in cookie_string.split("; "):
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    sess.cookies.set(name.strip(), value.strip(), domain=".octane-prod.bmwgroup.net")
            # 同时保留完整字符串头部，部分服务器仍查看 headers
            sess.headers.update({"Cookie": cookie_string})
            logging.debug(f"session.cookies jar: {sess.cookies.get_dict()}")
            logging.debug(f"session.headers before request: {sess.headers}")
            # 先试 defects 接口
            url1 = f"{BASE_URL}/api/shared_spaces/1002/workspaces/2001/defects"
            logging.info(f"验证访问 {url1} ...")
            r = sess.get(url1, params={"limit": 1}, timeout=30)
            logging.debug(f"req header cookie: {r.request.headers.get('Cookie')}")
            if r.status_code == 200:
                logging.info("cookie 验证通过 (defects)")
                return True
            # 再试 user_settings 接口做进一步检测
            url2 = (f"{BASE_URL}/api/shared_spaces/1002/workspaces/2001/user_settings" 
                    "?fields=id&query=\"(scope_type%3D%27module%27;scope_id%3D%27defects%27;author%3D%7Bid%3D138017%7D)\"")
            r2 = sess.get(url2, timeout=30)
            if r2.status_code == 200:
                logging.info("cookie 验证通过 (user_settings)")
                return True
            logging.warning(f"cookie 验证失败, primary status={r.status_code}, secondary={r2.status_code}")
            return False
        except Exception as e:
            logging.error(f"验证 cookie 时出错: {e}")
            return False

    def refresh_cookie(self):
        """刷新 cookie：打开浏览器、登录、验证并保存"""
        print("=== 开始自动刷新 cookie ===")
        new = self.get_cookie_via_playwright(headless=False)
        if not new:
            print("✗ 获取 cookie 失败")
            return False
        if not self.validate_cookie(new):
            print("✗ 新 cookie 验证失败")
            return False
        if self.save_cookie(new):
            print("✓ cookie 已保存")
            return True
        else:
            print("✗ 保存失败")
            return False

    def check_cookie_status(self):
        print("=== Cookie 状态 ===")
        if not os.path.exists(COOKIE_FILE):
            print("✗ cookie.txt 不存在")
            return False
        stat = os.stat(COOKIE_FILE)
        print(f"路径: {os.path.abspath(COOKIE_FILE)}")
        print(f"大小: {stat.st_size} bytes")
        print(f"修改时间: {datetime.fromtimestamp(stat.st_mtime)}")
        with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
            ck = f.read().strip()
        print(f"当前 Cookie 字符串 (前200字符): {ck[:200]}{'...' if len(ck)>200 else ''}")
        valid = self.validate_cookie(ck)
        print("有效" if valid else "无效")
        return valid

    def main_menu(self):
        while True:
            print("\n1. 检查 cookie 状态")
            print("2. 刷新 cookie")
            print("0. 退出")
            c = input("选择: ").strip()
            if c == '0':
                break
            elif c == '1':
                self.check_cookie_status()
            elif c == '2':
                self.refresh_cookie()
            else:
                print("无效选项")
            input("按回车继续...")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    mgr = PlaywrightCookieManager()
    if args.refresh:
        success = mgr.refresh_cookie()
        sys.exit(0 if success else 1)
    if args.check:
        success = mgr.check_cookie_status()
        sys.exit(0 if success else 1)
    mgr.main_menu()


if __name__ == '__main__':
    main()
