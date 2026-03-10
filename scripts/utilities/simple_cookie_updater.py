#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版 Octane Cookie 更新器
只使用Python标准库和requests，定期更新cookie
"""

import json
import time
import requests
import logging
import os
import threading
from datetime import datetime, timedelta
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 尝试导入 sso_session
try:
    from sso_session import bmw_sso_session
    SSO_AVAILABLE = True
except ImportError:
    SSO_AVAILABLE = False

# 配置
BASE_URL = "https://octane-prod.bmwgroup.net"
API_BASE_URL = f"{BASE_URL}/api/shared_spaces/1002/workspaces/2001"
EP_USER = "workspace_users"
COOKIE_FILE = "cookie.txt"
LOGIN_FILE = "login_info.txt"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleCookieUpdater:
    def __init__(self, check_interval_minutes=30):
        self.check_interval_minutes = check_interval_minutes
        self.running = False
        
    def get_login_credentials(self):
        """获取登录凭据"""
        try:
            if not os.path.exists(LOGIN_FILE):
                logger.error(f"登录文件 '{LOGIN_FILE}' 未找到")
                return None, None
                
            with open(LOGIN_FILE, "r", encoding="utf-8") as f:
                # 首先尝试JSON格式
                try:
                    login_data = json.load(f)
                    if isinstance(login_data, dict):
                        username = login_data.get("username")
                        password = login_data.get("password")
                        if username and password:
                            logger.info(f"成功从JSON格式文件读取用户 '{username}' 的登录凭据")
                            return username, password
                        else:
                            logger.error("JSON文件中缺少username或password字段")
                            return None, None
                except json.JSONDecodeError:
                    # 如果不是JSON格式，回退到行格式
                    f.seek(0)  # 重置文件指针
                    lines = f.readlines()
                    if len(lines) >= 2:
                        username = lines[0].strip()
                        password = lines[1].strip()
                        logger.info(f"成功从行格式文件读取用户 '{username}' 的登录凭据")
                        return username, password
                    else:
                        logger.error("登录文件格式不正确")
                        return None, None
                        
        except Exception as e:
            logger.error(f"读取登录文件时出错: {e}")
            return None, None
    
    def get_new_cookie(self):
        """获取新的cookie"""
        if not SSO_AVAILABLE:
            logger.error("SSO模块不可用")
            return None
            
        username, password = self.get_login_credentials()
        if not username or not password:
            return None
            
        try:
            logger.info("正在通过SSO获取新cookie...")
            session = requests.Session()
            session.verify = False
            
            auth_session = bmw_sso_session(BASE_URL, username, password, session=session)
            if not auth_session:
                logger.error("SSO认证失败")
                return None
                
            cookie_dict = auth_session.cookies.get_dict()
            if not cookie_dict:
                logger.error("未获取到cookie")
                return None
                
            cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            logger.info("成功获取新cookie")
            return cookie_string
            
        except Exception as e:
            logger.error(f"获取cookie时出错: {e}")
            return None
    
    def test_cookie(self, cookie_string):
        """测试cookie有效性"""
        try:
            session = requests.Session()
            session.verify = False
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "cookie": cookie_string
            })
            
            test_url = f"{API_BASE_URL}/{EP_USER}"
            resp = session.get(test_url, params={"limit": 1, "fields": "id"}, timeout=15)
            
            return resp.status_code == 200
            
        except Exception as e:
            logger.error(f"测试cookie时出错: {e}")
            return False
    
    def save_cookie(self, cookie_string):
        """保存cookie到文件"""
        try:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(cookie_string)
            logger.info(f"Cookie已保存到 '{COOKIE_FILE}'")
            return True
        except Exception as e:
            logger.error(f"保存cookie失败: {e}")
            return False
    
    def load_cookie(self):
        """从文件加载cookie"""
        try:
            if not os.path.exists(COOKIE_FILE):
                return None
                
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                cookie = f.read().strip()
                
            return cookie if cookie else None
            
        except Exception as e:
            logger.error(f"读取cookie失败: {e}")
            return None
    
    def update_cookie_if_needed(self):
        """检查并更新cookie"""
        logger.info("检查cookie状态...")
        
        # 加载现有cookie
        current_cookie = self.load_cookie()
        
        # 如果没有cookie或cookie无效，获取新的
        if not current_cookie or not self.test_cookie(current_cookie):
            logger.info("需要更新cookie")
            new_cookie = self.get_new_cookie()
            if new_cookie and self.save_cookie(new_cookie):
                logger.info("Cookie更新成功")
                return True
            else:
                logger.error("Cookie更新失败")
                return False
        else:
            logger.info("Cookie仍然有效")
            return True
    
    def run_daemon(self):
        """运行守护进程"""
        self.running = True
        logger.info(f"启动Cookie自动更新器，每{self.check_interval_minutes}分钟检查一次")
        
        # 初始检查
        self.update_cookie_if_needed()
        
        try:
            while self.running:
                time.sleep(self.check_interval_minutes * 60)  # 转换为秒
                if self.running:  # 再次检查，防止在睡眠期间被停止
                    self.update_cookie_if_needed()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止...")
        finally:
            self.running = False
            logger.info("Cookie更新器已停止")
    
    def stop(self):
        """停止守护进程"""
        self.running = False

def main():
    """主函数"""
    print("简化版 Octane Cookie 自动更新器")
    print("=" * 40)
    
    if not SSO_AVAILABLE:
        print("错误: 未找到 sso_session 模块")
        return
        
    print("1. 立即更新cookie")
    print("2. 启动自动更新守护进程 (默认30分钟检查一次)")
    print("3. 自定义间隔启动守护进程")
    
    choice = input("请选择 (1-3): ").strip()
    
    if choice == "1":
        updater = SimpleCookieUpdater()
        print("正在更新cookie...")
        if updater.update_cookie_if_needed():
            print("Cookie更新完成！")
        else:
            print("Cookie更新失败！")
            
    elif choice == "2":
        updater = SimpleCookieUpdater()
        print("启动自动更新守护进程...")
        print("按 Ctrl+C 停止")
        updater.run_daemon()
        
    elif choice == "3":
        try:
            interval = int(input("请输入检查间隔（分钟）: "))
            if interval <= 0:
                print("间隔必须大于0")
                return
            updater = SimpleCookieUpdater(interval)
            print(f"启动自动更新守护进程（每{interval}分钟检查一次）...")
            print("按 Ctrl+C 停止")
            updater.run_daemon()
        except ValueError:
            print("请输入有效数字")
    else:
        print("无效选择")

if __name__ == "__main__":
    main()