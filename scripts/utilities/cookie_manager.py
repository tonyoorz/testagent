#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Octane Cookie 自动管理器
功能：
1. 自动通过SSO登录获取cookie
2. 定期检查cookie有效性
3. 自动更新过期的cookie
4. 保存到cookie.txt文件
"""

import json
import time
import requests
import logging
import os
import threading
from datetime import datetime, timedelta
import urllib3
import schedule

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 尝试导入 sso_session
try:
    from sso_session import bmw_sso_session
    SSO_AVAILABLE = True
except ImportError:
    SSO_AVAILABLE = False
    print("警告: sso_session 模块未找到，程序无法工作")

# 配置
BASE_URL = "https://octane-prod.bmwgroup.net"
API_BASE_URL = f"{BASE_URL}/api/shared_spaces/1002/workspaces/2001"
EP_USER = "workspace_users"
COOKIE_FILE = "cookie.txt"
LOGIN_FILE = "login_info.txt"
LOG_FILE = "cookie_manager.log"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CookieManager:
    def __init__(self):
        self.current_cookie = None
        self.last_update_time = None
        self.check_interval_minutes = 30  # 每30分钟检查一次
        self.cookie_lifetime_hours = 8     # 假设cookie有效期8小时
        self.running = False
        
    def load_login_credentials(self):
        """从文件加载登录凭据"""
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
                        logger.error(f"登录文件 '{LOGIN_FILE}' 格式不正确，需要用户名和密码各占一行")
                        return None, None
        except Exception as e:
            logger.error(f"读取登录文件时出错: {e}")
            return None, None
    
    def get_new_cookie_via_sso(self):
        """通过SSO登录获取新的cookie"""
        if not SSO_AVAILABLE:
            logger.error("SSO模块不可用，无法获取cookie")
            return None
            
        username, password = self.load_login_credentials()
        if not username or not password:
            logger.error("无法读取登录凭据")
            return None
            
        try:
            logger.info(f"尝试通过SSO为用户 '{username}' 获取新cookie...")
            
            # 创建新的session
            session = requests.Session()
            session.verify = False
            
            # 使用SSO进行认证
            auth_session = bmw_sso_session(BASE_URL, username, password, session=session)
            if not auth_session:
                logger.error("SSO认证失败")
                return None
                
            # 从session中提取cookie
            cookie_dict = auth_session.cookies.get_dict()
            if not cookie_dict:
                logger.error("认证成功但未获取到cookie")
                return None
                
            # 将cookie字典转换为字符串格式
            cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            
            logger.info("成功通过SSO获取新cookie")
            return cookie_string
            
        except Exception as e:
            logger.error(f"通过SSO获取cookie时出错: {e}")
            return None
    
    def test_cookie_validity(self, cookie_string):
        """测试cookie是否有效"""
        try:
            session = requests.Session()
            session.verify = False
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_string
            })
            
            # 使用简单的API调用测试认证
            test_url = f"{API_BASE_URL}/{EP_USER}"
            resp = session.get(test_url, params={"limit": 1, "fields": "id"}, timeout=15)
            
            if resp.status_code == 200:
                logger.info("Cookie验证成功")
                return True
            else:
                logger.warning(f"Cookie验证失败，状态码: {resp.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"测试cookie有效性时出错: {e}")
            return False
    
    def load_existing_cookie(self):
        """从文件加载现有cookie"""
        try:
            if not os.path.exists(COOKIE_FILE):
                logger.info(f"Cookie文件 '{COOKIE_FILE}' 不存在")
                return None
                
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                cookie = f.read().strip()
                
            if not cookie:
                logger.info(f"Cookie文件 '{COOKIE_FILE}' 为空")
                return None
                
            logger.info(f"成功从 '{COOKIE_FILE}' 读取现有cookie")
            return cookie
            
        except Exception as e:
            logger.error(f"读取cookie文件时出错: {e}")
            return None
    
    def save_cookie(self, cookie_string):
        """保存cookie到文件"""
        try:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(cookie_string)
            logger.info(f"Cookie已保存到 '{COOKIE_FILE}'")
            return True
        except Exception as e:
            logger.error(f"保存cookie到文件时出错: {e}")
            return False
    
    def update_cookie(self, force=False):
        """更新cookie"""
        logger.info("开始检查cookie状态...")
        
        # 如果强制更新，直接获取新cookie
        if force:
            logger.info("强制更新cookie...")
            new_cookie = self.get_new_cookie_via_sso()
            if new_cookie:
                if self.save_cookie(new_cookie):
                    self.current_cookie = new_cookie
                    self.last_update_time = datetime.now()
                    logger.info("强制更新cookie成功")
                    return True
            logger.error("强制更新cookie失败")
            return False
        
        # 检查现有cookie
        current_cookie = self.load_existing_cookie()
        
        # 如果没有cookie或cookie无效，获取新的
        if not current_cookie or not self.test_cookie_validity(current_cookie):
            logger.info("当前cookie无效，正在获取新cookie...")
            new_cookie = self.get_new_cookie_via_sso()
            if new_cookie:
                if self.save_cookie(new_cookie):
                    self.current_cookie = new_cookie
                    self.last_update_time = datetime.now()
                    logger.info("Cookie更新成功")
                    return True
            logger.error("Cookie更新失败")
            return False
        else:
            logger.info("当前cookie仍然有效")
            self.current_cookie = current_cookie
            if not self.last_update_time:
                self.last_update_time = datetime.now()
            return True
    
    def scheduled_check(self):
        """定时检查和更新cookie"""
        logger.info("执行定时cookie检查...")
        self.update_cookie()
    
    def is_cookie_near_expiry(self):
        """检查cookie是否接近过期"""
        if not self.last_update_time:
            return True
            
        time_since_update = datetime.now() - self.last_update_time
        hours_since_update = time_since_update.total_seconds() / 3600
        
        # 如果距离上次更新时间超过设定的生命周期的80%，认为接近过期
        if hours_since_update > (self.cookie_lifetime_hours * 0.8):
            logger.info(f"Cookie距离上次更新已过 {hours_since_update:.1f} 小时，可能需要更新")
            return True
        return False
    
    def start_daemon(self):
        """启动守护进程"""
        if self.running:
            logger.warning("Cookie管理器已在运行")
            return
            
        self.running = True
        logger.info("启动Cookie自动管理器...")
        
        # 初始检查和更新
        logger.info("执行初始cookie检查...")
        if not self.update_cookie():
            logger.error("初始cookie获取失败，但守护进程将继续运行...")
        
        # 设置定时任务
        schedule.every(self.check_interval_minutes).minutes.do(self.scheduled_check)
        
        logger.info(f"Cookie自动管理器已启动，将每 {self.check_interval_minutes} 分钟检查一次")
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次是否有待执行的任务
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止...")
            self.stop_daemon()
        except Exception as e:
            logger.error(f"守护进程运行时出错: {e}")
            self.stop_daemon()
    
    def stop_daemon(self):
        """停止守护进程"""
        self.running = False
        logger.info("Cookie管理器已停止")

def main():
    """主函数"""
    print("Octane Cookie 自动管理器")
    print("=" * 50)
    
    if not SSO_AVAILABLE:
        print("错误: 未找到 sso_session 模块，请确保该模块可用")
        return
    
    manager = CookieManager()
    
    while True:
        print("\n请选择操作:")
        print("1. 立即更新cookie")
        print("2. 检查当前cookie状态")
        print("3. 启动自动管理守护进程")
        print("4. 修改检查间隔")
        print("5. 退出")
        
        choice = input("请输入选择 (1-5): ").strip()
        
        if choice == "1":
            print("正在强制更新cookie...")
            if manager.update_cookie(force=True):
                print("Cookie更新成功！")
            else:
                print("Cookie更新失败！")
                
        elif choice == "2":
            print("正在检查cookie状态...")
            cookie = manager.load_existing_cookie()
            if cookie:
                if manager.test_cookie_validity(cookie):
                    print("Cookie存在且有效")
                    # 显示cookie的部分内容（隐藏敏感信息）
                    preview = cookie[:50] + "..." if len(cookie) > 50 else cookie
                    print(f"Cookie预览: {preview}")
                else:
                    print("Cookie存在但已失效")
            else:
                print("未找到cookie文件")
                
        elif choice == "3":
            print(f"启动自动管理守护进程 (每{manager.check_interval_minutes}分钟检查一次)")
            print("按 Ctrl+C 停止...")
            try:
                manager.start_daemon()
            except KeyboardInterrupt:
                print("\n守护进程已停止")
                
        elif choice == "4":
            try:
                new_interval = int(input(f"请输入新的检查间隔（分钟，当前: {manager.check_interval_minutes}）: ").strip())
                if new_interval > 0:
                    manager.check_interval_minutes = new_interval
                    print(f"检查间隔已更新为 {new_interval} 分钟")
                else:
                    print("间隔必须大于0")
            except ValueError:
                print("请输入有效的数字")
                
        elif choice == "5":
            print("退出程序")
            break
            
        else:
            print("无效选择，请重试")

if __name__ == "__main__":
    main()