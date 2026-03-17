#!/usr/bin/env python3
"""
测试特定Master ID的可访问性
用于诊断Master缺陷下载失败的问题
"""

import requests
import json
import logging
import os
import sys
import urllib3
import re

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 尝试导入SSO模块
try:
    from sso_session import bmw_sso_session
    SSO_AVAILABLE = True
except ImportError:
    SSO_AVAILABLE = False

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 常量定义
BASE_URL = "https://octane-prod.bmwgroup.net"
API_SHARED_SPACES_URL = f"{BASE_URL}/api/shared_spaces/1002"
API_BASE_URL = f"{API_SHARED_SPACES_URL}/workspaces/2001"
EP_DEFECT = "defects"

# 基本字段用于测试
TEST_FIELDS = "id,name,creation_time,last_modified,phase,severity,owner,parent_child_udf"

def clean_master_id(master_id):
    """清理Master ID格式"""
    if not master_id:
        return None
    
    master_id_str = str(master_id).strip()
    
    # 清理包含"Defect"前缀的ID
    if master_id_str.lower().startswith('defect'):
        numbers = re.findall(r'\d+', master_id_str)
        if numbers:
            cleaned_id = numbers[0]
            logging.info(f"清理ID格式: '{master_id_str}' -> '{cleaned_id}'")
            return cleaned_id
        else:
            logging.warning(f"无法从 '{master_id_str}' 中提取有效数字ID")
            return None
    
    # 移除可能的空格和特殊字符
    master_id_str = re.sub(r'[^\w-]', '', master_id_str)
    
    if not master_id_str:
        return None
    
    return master_id_str

def get_session():
    """获取认证会话"""
    session = requests.Session()
    session.verify = False
    
    # 首先尝试cookie文件
    cookie_file = "cookie.txt"
    if os.path.exists(cookie_file):
        logging.info("使用cookie文件认证")
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookie_val = f.read().strip()
        
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "cookie": cookie_val
        })
        return session
    
    # 如果没有cookie文件，尝试SSO
    if SSO_AVAILABLE:
        login_file = "login_info.txt"
        if os.path.exists(login_file):
            logging.info("使用SSO认证")
            try:
                with open(login_file, "r", encoding="utf-8") as f:
                    # 首先尝试JSON格式
                    try:
                        login_data = json.load(f)
                        if isinstance(login_data, dict):
                            username = login_data.get("username")
                            password = login_data.get("password")
                            if username and password:
                                logging.info(f"成功从JSON格式文件读取用户 '{username}' 的登录凭据")
                            else:
                                logging.error("JSON文件中缺少username或password字段")
                                return None
                        else:
                            logging.error("JSON文件格式不正确，应为字典对象")
                            return None
                    except json.JSONDecodeError:
                        # 如果不是JSON格式，回退到行格式
                        f.seek(0)  # 重置文件指针
                        lines = f.readlines()
                        if len(lines) >= 2:
                            username = lines[0].strip()
                            password = lines[1].strip()
                            logging.info(f"成功从行格式文件读取用户 '{username}' 的登录凭据")
                        else:
                            logging.error("登录文件格式不正确")
                            return None
                    
                    if username and password:
                        auth_session = bmw_sso_session(BASE_URL, username, password, session=session)
                        if auth_session:
                            return auth_session
            except Exception as e:
                logging.error(f"SSO认证失败: {e}")
    
    logging.error("无法获取认证会话，请确保有cookie.txt或login_info.txt文件")
    return None

def test_single_master_id(session, master_id):
    """测试单个Master ID的可访问性"""
    # 清理ID格式
    cleaned_id = clean_master_id(master_id)
    if not cleaned_id:
        logging.error(f"无效的Master ID格式: {master_id}")
        return False
    
    logging.info(f"测试Master ID: {cleaned_id} (原始: {master_id})")
    
    # 构建查询
    query = f'"(id=\'{cleaned_id}\')"'
    request_url = f"{API_BASE_URL}/{EP_DEFECT}"
    
    params = {
        "fields": TEST_FIELDS,
        "query": query,
        "limit": 1,
        "offset": 0
    }
    
    try:
        resp = session.get(request_url, params=params, timeout=30, verify=False)
        logging.info(f"HTTP状态码: {resp.status_code}")
        logging.debug(f"请求URL: {resp.url}")
        
        if resp.status_code == 200:
            data = resp.json()
            total_count = data.get("total_count", 0)
            defects = data.get("data", [])
            
            logging.info(f"API返回总数: {total_count}")
            logging.info(f"实际返回数据条数: {len(defects)}")
            
            if defects:
                defect = defects[0]
                logging.info(f"找到缺陷:")
                logging.info(f"  ID: {defect.get('id')}")
                logging.info(f"  名称: {defect.get('name')}")
                logging.info(f"  阶段: {defect.get('phase', {}).get('name', 'N/A')}")
                logging.info(f"  严重性: {defect.get('severity', {}).get('name', 'N/A')}")
                logging.info(f"  负责人: {defect.get('owner', {}).get('name', 'N/A')}")
                logging.info(f"  创建时间: {defect.get('creation_time')}")
                
                # 检查parent_child_udf
                parent_child_info = defect.get('parent_child_udf', {})
                if parent_child_info:
                    logging.info(f"  Parent/Child类型: {parent_child_info.get('name', 'N/A')}")
                
                return True
            else:
                logging.warning(f"Master ID {cleaned_id} 未找到任何数据")
                return False
        elif resp.status_code == 401:
            logging.error("认证失败 (401)")
            return False
        elif resp.status_code == 403:
            logging.error("权限不足 (403)")
            return False
        elif resp.status_code == 404:
            logging.error("资源未找到 (404)")
            return False
        elif resp.status_code == 500:
            logging.error(f"服务器内部错误 (500)")
            logging.error(f"响应内容: {resp.text[:500]}")
            return False
        else:
            logging.error(f"请求失败: {resp.status_code}")
            logging.error(f"响应内容: {resp.text[:500]}")
            return False
            
    except Exception as e:
        logging.error(f"请求异常: {e}")
        return False

def test_multiple_master_ids(session, master_ids):
    """批量测试多个Master ID"""
    # 清理所有ID
    cleaned_ids = []
    for mid in master_ids:
        cleaned = clean_master_id(mid)
        if cleaned:
            cleaned_ids.append(cleaned)
        else:
            logging.warning(f"跳过无效ID: {mid}")
    
    if not cleaned_ids:
        logging.error("没有有效的Master ID可供测试")
        return set(), set(master_ids)
    
    logging.info(f"批量测试 {len(cleaned_ids)} 个Master ID")
    
    # 构建OR查询
    id_conditions = [f"id='{master_id}'" for master_id in cleaned_ids]
    id_query = "||".join(id_conditions)
    query = f'"({id_query})"'
    
    request_url = f"{API_BASE_URL}/{EP_DEFECT}"
    params = {
        "fields": TEST_FIELDS,
        "query": query,
        "limit": 100,
        "offset": 0
    }
    
    try:
        resp = session.get(request_url, params=params, timeout=30, verify=False)
        logging.info(f"批量查询HTTP状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            total_count = data.get("total_count", 0)
            defects = data.get("data", [])
            
            logging.info(f"批量查询API返回总数: {total_count}")
            logging.info(f"批量查询实际返回数据条数: {len(defects)}")
            
            found_ids = {str(defect.get('id')) for defect in defects}
            missing_ids = set(cleaned_ids) - found_ids
            
            logging.info(f"找到的ID: {sorted(found_ids)}")
            if missing_ids:
                logging.warning(f"未找到的ID: {sorted(missing_ids)}")
            
            return found_ids, missing_ids
        else:
            logging.error(f"批量查询失败: {resp.status_code}")
            if resp.status_code == 500:
                logging.error(f"服务器错误响应: {resp.text[:500]}")
            return set(), set(cleaned_ids)
            
    except Exception as e:
        logging.error(f"批量查询异常: {e}")
        return set(), set(cleaned_ids)

def main():
    if len(sys.argv) < 2:
        print("用法: python test_master_id.py <master_id1> [master_id2] [master_id3] ...")
        print("示例: python test_master_id.py 2233570")
        print("示例: python test_master_id.py 2233570 1431600 'Defect 2205365'")
        sys.exit(1)
    
    master_ids = sys.argv[1:]
    logging.info(f"开始测试Master ID: {master_ids}")
    
    # 获取会话
    session = get_session()
    if not session:
        logging.error("无法创建会话")
        sys.exit(1)
    
    # 测试认证
    test_url = f"{API_BASE_URL}/workspace_users"
    try:
        test_resp = session.get(test_url, params={"limit": 1, "fields": "id"}, timeout=15, verify=False)
        if test_resp.status_code != 200:
            logging.error(f"认证测试失败: {test_resp.status_code}")
            sys.exit(1)
        logging.info("认证测试成功")
    except Exception as e:
        logging.error(f"认证测试异常: {e}")
        sys.exit(1)
    
    # 如果只有一个ID，进行详细测试
    if len(master_ids) == 1:
        test_single_master_id(session, master_ids[0])
    else:
        # 多个ID，先批量测试，再对失败的进行单独测试
        found_ids, missing_ids = test_multiple_master_ids(session, master_ids)
        
        if missing_ids:
            logging.info(f"对 {len(missing_ids)} 个未找到的ID进行单独测试...")
            for missing_id in sorted(missing_ids):
                test_single_master_id(session, missing_id)

if __name__ == "__main__":
    main() 