import json
import time
import urllib.parse
import requests
import logging
import pandas as pd
from datetime import datetime, timedelta # Added timedelta
import os
import argparse
import urllib3 # For disabling warnings
import concurrent.futures # Added for history
from tqdm import tqdm # Added for history
import re
import asyncio
import aiohttp
from functools import partial
from threading import Lock
import hashlib

# Helper ------------------------------------------------------------------

def normalize_iso_date(date_str):
    """Return a YYYY-MM-DD string with zero-padded month/day.

    Accepts ISO-like inputs such as '2024-12-3' or '2024-2-1' and
    normalizes them. Raises ValueError for invalid formats.

    If ``date_str`` is falsy, returns None.
    """
    if not date_str:
        return None
    try:
        # fromisoformat handles most valid ISO strings but insists on zero padding
        dt = datetime.fromisoformat(date_str)
    except Exception:
        # try manual parsing of numbers separated by '-'
        parts = date_str.split('-')
        if len(parts) != 3:
            raise
        y, m, d = parts
        dt = datetime(int(y), int(m), int(d))
    return dt.strftime("%Y-%m-%d")

# -------------------------------------------------------------------------

# 尝试导入 sso_session，如果失败则告知用户
try:
    from sso_session import bmw_sso_session
    SSO_AVAILABLE = True
except ImportError:
    SSO_AVAILABLE = False
    # 定义一个占位函数，以便在 SSO 不可用时代码结构仍然有效
    def bmw_sso_session(*args, **kwargs):
        logging.error("sso_session 模块未找到，无法使用 SSO 认证。")
        return None

# --- 基本配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 常量定义
BASE_URL = "https://octane-prod.bmwgroup.net"
API_SHARED_SPACES_URL = f"{BASE_URL}/api/shared_spaces/1002"
API_BASE_URL = f"{API_SHARED_SPACES_URL}/workspaces/2001"
DEFAULT_LIMIT_PER_PAGE = 5000  # 🚀 超级优化：5倍分页大小，大幅减少请求次数

# DEFAULT_COOKIE = "GUEST_LANGUAGE_ID=en_US; i18next=english; rxVisitor=1744613931631B6MLA5NP6DPA5LIVUM9BJ21MS3QBPFUP; XSRF_COOKIE=4men8boi1mfdn4oiaarg4br81a; lbwen=01; dtCookie=v_4_srv_3_sn_5NK42I4QNH2GA03S7UH3N7O9F2DJ6BQ1_app-3A2579a82aa388e4a2_1_app-3A3a336dbc3f55ee1c_1_ol_0_perc_100000_mul_1_rcs-3Acss_0; dtSa=-; HPECLIENTTYPE=HPE_MQM_UI; rxvt=1747636806312|1747635006312; dtPC=3$433186436_809h-vHLBHPQFRRTICDHAIRNVFWWCMKDKWADVM-0e0; wen=EjyW7v3baRCU8zNfsmPCriXC-Kg.*AAJTSQACMDEAAlNLABxhZU1ZMldTOVRSQ2QzMGgyYWFBNFkzMEhYVGM9AAR0eXBlAANDVFMAAlMxAAA.*; access_token=eHwAIJwzQiYsYkRGThn7kSt3NeOal0UMZGvPTUVI3MYGSeSY05mV8FKth6z3KrqdtAUXxRr4oKrMOmQU1KgkiYo_vcBx0-TP9EXlu76ic4sLR7Hnr_XhE_5p384spqRNU2-PsYQUaGtEM79hNeU4Qowy4Lh2B_sihhEr1X0V5ry_lUHdcH6gfQlJ1Nh9jDYlsa9z0zrUZizDzh52nrLYs3T_TAbE68rNFx-mAScaQYRdDSb1GyY-Xbbo50upPYoOF37FIbTlBbD6Eqph8GvOoOWJ75--pkT9NrtEplssXJKg-wiqn0PB2xVS90tmJW9LJbdh4EkqH0oDF1RZmAuw4HA2SAM; OCTANE_USER=dc6d2a07c6a31c45350e22733238fa8c72b667594ae4b0eb0a15934c6117a882; JSESSIONID=node01t67jdrm4s55617azboi8s6xrz108089.node0"

# API 端点
EP_DEFECT = "defects"
EP_MANUALRUN = "manual_runs"
EP_USER = "workspace_users"
EP_HISTORY = "history_logs"

DEFAULT_F_DEFECT_MAIN = (
    "id", "name", "creation_time", "last_modified", 
    "parent_child_udf", 
    "team",
    "vin_udf", "user_tags", "tqr_udf", "product_areas", "aida_businesskey_udf",
    "software_version_udf", "ecu_no_of_changes_udf", "first_use_sop_of_function_udf",
    "tolerated_count_udf", "blocking_reason_udf", "reprel_changes_udf",
    "requirements", 
    "parent",
    "parent_phase_udf", "sab_comment_udf",
    "relation_to_udf", # 新增：假设的 "Relation to" UDF 字段名
    "assigned_ecu_udf", "error_occurrence_udf",
    "problem_finder_team_udf", "program", "solution_responsible_udf",
    "solution_cluster_udf", "reporting_class_udf", "detected_in_release",
    "detected_by", "function_responsible1_udf", "owner", "phase", "severity",
    "involved_i_step1_udf", "author", "lead_model_udf", "problem_severity_udf",
    "ecu_to_modul_udf"
)


DEFAULT_F_MANUALRUN = (
    "defect", "is_completed", "steps_num", "name", "version_stamp", "id",
    "last_modified", "started", "creation_time", "test_name", "test",
    "finished_udf", "testplatformid_udf", "exec_model_series_udf",
    "execution_sw_version_udf", "author", "release", "run_by",
    "product_areas", "program", "set_udf", "testing_tool_type", "taxonomies",
    "test_version", "test_phase", "run_team_000_udf", "domain_udf", "status",
    "native_status", "target_ecu_conf_udf"
)


DEFAULT_TEAM = "DTSV_China" # Default team for all operations unless overridden by specific args

# 🚀 自动优化配置（已内置，无需手动调整）

# --- CORE FUNCTIONS ---
def fetch_octane_data(session, endpoint, fields, query, limit_per_page=DEFAULT_LIMIT_PER_PAGE, order_by=None, api_url=API_BASE_URL):
    all_data = []
    offset = 0
    total_fetched = 0
    logging.info(f"开始从端点 '{endpoint}' (API URL: {api_url}) 获取数据，查询条件: {query}")
    while True:
        request_params = {
            "fields": ",".join(fields) if isinstance(fields, (list, tuple)) else fields,
            "query": query,
            "limit": limit_per_page,
            "offset": offset
        }
        if order_by:
            request_params["order_by"] = order_by
        
        request_url_full = f"{api_url}/{endpoint}"
        logging.debug(f"请求 URL: {request_url_full} with params: {request_params}")
        try:
            resp = session.get(request_url_full, params=request_params, verify=False, allow_redirects=True, timeout=60)
            if resp.status_code == 401:
                logging.error(f"认证失败 (401). URL: {resp.url}"); return []
            elif resp.status_code == 403:
                logging.error(f"权限不足 (403). URL: {resp.url}"); return []
            elif resp.status_code == 404:
                 logging.warning(f"资源未找到 (404). URL: {resp.url}"); break
            elif resp.status_code >= 400:
                logging.error(f"请求失败: {resp.status_code}. URL: {resp.url}. Response: {resp.text[:500]}"); break
            resp.raise_for_status() # Will raise an HTTPError for bad responses (4xx or 5xx)
            data = resp.json()
            batch_data = data.get("data", [])
            batch_size = len(batch_data)
            total_count_api = data.get("total_count")
            total_count = int(total_count_api) if isinstance(total_count_api, int) else 0

            if not batch_data and offset == 0: # First page is empty
                logging.info(f"端点 '{endpoint}' 查询没有返回任何数据。"); break
            if not batch_data: # Subsequent empty page (should ideally not happen if total_count is accurate)
                logging.info(f"获取到空数据页，假定数据已全部获取. 总计 {total_fetched} 条."); break
            
            all_data.extend(batch_data)
            total_fetched += batch_size
            logging.info(f"成功获取 {batch_size} 条数据，累计 {total_fetched} 条 (API报告总数: {total_count_api if total_count_api is not None else '未知'}).")

            if total_count > 0 and total_fetched >= total_count: # API reported total and we fetched it
                logging.info(f"已获取 API 报告的所有 {total_fetched} 条数据."); break
            if batch_size < limit_per_page: # Last page fetched
                logging.info(f"获取到的数据 ({batch_size}) 少于分页限制 ({limit_per_page})，已获取所有数据. 总计 {total_fetched} 条."); break
            
            offset += limit_per_page
            # 🚀 动态延迟优化
            import sys
            if 'turbo_mode' in sys.argv or '--turbo-mode' in sys.argv:
                time.sleep(0.001)  # 极限模式：几乎无延迟
            else:
                time.sleep(0.01)   # 超级优化：极小延迟
        except requests.exceptions.Timeout:
             logging.warning(f"请求超时: {request_url_full}"); break
        except requests.exceptions.RequestException as e:
            logging.error(f"请求端点 '{endpoint}' 时发生网络或请求错误: {e}"); break
        except json.JSONDecodeError as e:
            logging.error(f"解析JSON失败: {e}. Response: {resp.text[:500]}"); break
        except Exception as e:
            logging.error(f"处理请求时发生未知错误 '{endpoint}': {e}"); break
    logging.info(f"从端点 '{endpoint}' 数据获取完成，共获取 {len(all_data)} 条数据。")
    return all_data

# 🚀 新增：单个分页请求函数（用于多线程）
def fetch_single_page(session, endpoint, fields, query, limit_per_page, offset, order_by=None, api_url=API_BASE_URL):
    """获取单个分页的数据（用于多线程并发）"""
    request_params = {
        "fields": ",".join(fields) if isinstance(fields, (list, tuple)) else fields,
        "query": query,
        "limit": limit_per_page,
        "offset": offset
    }
    if order_by:
        request_params["order_by"] = order_by
    
    request_url_full = f"{api_url}/{endpoint}"
    
    try:
        resp = session.get(request_url_full, params=request_params, verify=False, allow_redirects=True, timeout=60)
        if resp.status_code == 401:
            return {"error": f"认证失败 (401). URL: {resp.url}", "data": []}
        elif resp.status_code == 403:
            return {"error": f"权限不足 (403). URL: {resp.url}", "data": []}
        elif resp.status_code == 404:
            return {"error": f"资源未找到 (404). URL: {resp.url}", "data": []}
        elif resp.status_code >= 400:
            return {"error": f"请求失败: {resp.status_code}. URL: {resp.url}", "data": []}
        
        resp.raise_for_status()
        data = resp.json()
        batch_data = data.get("data", [])
        total_count = data.get("total_count", 0)
        
        return {
            "data": batch_data,
            "total_count": total_count,
            "offset": offset,
            "page_size": len(batch_data),
            "error": None
        }
        
    except requests.exceptions.Timeout:
        return {"error": f"请求超时: {request_url_full}", "data": []}
    except requests.exceptions.RequestException as e:
        return {"error": f"网络或请求错误: {e}", "data": []}
    except json.JSONDecodeError as e:
        return {"error": f"解析JSON失败: {e}", "data": []}
    except Exception as e:
        return {"error": f"未知错误: {e}", "data": []}

# 🚀 新增：多线程并发下载函数
def fetch_octane_data_parallel(session, endpoint, fields, query, limit_per_page=DEFAULT_LIMIT_PER_PAGE, 
                              order_by=None, api_url=API_BASE_URL, max_workers=10):
    """使用多线程并发获取Octane数据，显著提升下载速度"""
    logging.info(f"🚀 开始多线程并发下载 '{endpoint}' 数据，查询条件: {query}")
    
    # 首先获取第一页来确定总数据量
    first_page = fetch_single_page(session, endpoint, fields, query, limit_per_page, 0, order_by, api_url)
    
    if first_page["error"]:
        logging.error(f"获取第一页失败: {first_page['error']}")
        return []
    
    if not first_page["data"]:
        logging.info(f"端点 '{endpoint}' 查询没有返回任何数据。")
        return []
    
    total_count = first_page["total_count"]
    all_data = first_page["data"].copy()
    
    logging.info(f"第一页获取成功，总数据量: {total_count}，第一页数据: {len(first_page['data'])} 条")
    
    # 如果只有一页数据，直接返回
    if len(first_page["data"]) < limit_per_page or total_count <= limit_per_page:
        logging.info(f"数据量较小，无需多线程下载。总计: {len(all_data)} 条")
        return all_data
    
    # 计算需要的分页数量
    total_pages = (total_count + limit_per_page - 1) // limit_per_page
    remaining_pages = total_pages - 1  # 减去已获取的第一页
    
    logging.info(f"🚀 启动多线程下载，总页数: {total_pages}，剩余页数: {remaining_pages}，并发线程: {max_workers}")
    
    # 生成剩余页面的offset列表
    page_offsets = [limit_per_page * (i + 1) for i in range(remaining_pages)]
    
    successful_pages = 0
    failed_pages = 0
    
    # 使用线程池并发下载剩余页面
    with tqdm(total=remaining_pages, desc=f"🚀 并发下载{endpoint}") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_offset = {
                executor.submit(fetch_single_page, session, endpoint, fields, query, 
                              limit_per_page, offset, order_by, api_url): offset 
                for offset in page_offsets
            }
            
            # 收集结果
            page_results = []
            for future in concurrent.futures.as_completed(future_to_offset):
                offset = future_to_offset[future]
                try:
                    result = future.result()
                    if result["error"]:
                        logging.warning(f"页面 offset={offset} 下载失败: {result['error']}")
                        failed_pages += 1
                    else:
                        page_results.append((offset, result["data"]))
                        successful_pages += 1
                        
                except Exception as e:
                    logging.error(f"处理页面 offset={offset} 时发生异常: {e}")
                    failed_pages += 1
                
                pbar.update(1)
    
    # 按offset排序并合并数据
    page_results.sort(key=lambda x: x[0])  # 按offset排序
    for offset, page_data in page_results:
        all_data.extend(page_data)
    
    success_rate = (successful_pages / remaining_pages * 100) if remaining_pages > 0 else 100
    logging.info(f"🚀 多线程下载完成！")
    logging.info(f"  总页数: {total_pages}，成功: {successful_pages + 1}，失败: {failed_pages}")
    logging.info(f"  成功率: {success_rate:.1f}%，总数据量: {len(all_data)} 条")
    
    return all_data

def save_data(data_to_save, filename_prefix, output_directory, save_csv_flag=False, save_excel_flag=False):
    if not data_to_save:
        logging.warning(f"没有数据保存到 {filename_prefix} (目录 {output_directory}).")
        return
    
    os.makedirs(output_directory, exist_ok=True)
    json_filepath = os.path.join(output_directory, f"{filename_prefix}.json")
    
    try:
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=2)
        logging.info(f"数据已保存为 JSON: {json_filepath}")
    except IOError as e:
        logging.error(f"保存 JSON 文件时出错 ({json_filepath}): {e}")
    except TypeError as e:
        logging.error(f"保存 JSON 文件时数据类型错误 ({json_filepath}): {e}. Type: {type(data_to_save)}")

    if isinstance(data_to_save, list) and data_to_save and isinstance(data_to_save[0], dict):
        if save_csv_flag or save_excel_flag:
            try:
                df = pd.json_normalize(data_to_save, sep='_')
                if save_csv_flag:
                    csv_filepath = os.path.join(output_directory, f"{filename_prefix}.csv")
                    df.to_csv(csv_filepath, index=False, encoding="utf-8")
                    logging.info(f"数据已保存为 CSV: {csv_filepath}")
                if save_excel_flag:
                    excel_filepath = os.path.join(output_directory, f"{filename_prefix}.xlsx")
                    try:
                        df.to_excel(excel_filepath, index=False, engine="openpyxl")
                        logging.info(f"数据已保存为 Excel: {excel_filepath}")
                    except ImportError:
                        logging.warning("需要 'openpyxl' 保存为 Excel. Run: pip install openpyxl")
                    except Exception as e_excel:
                        logging.error(f"保存 Excel 时出错 ({excel_filepath}): {e_excel}")
            except ImportError:
                logging.warning("需要 'pandas' 保存为 CSV/Excel. Run: pip install pandas")
            except Exception as e_pd:
                logging.error(f"处理并保存为 CSV/Excel时出错 for {filename_prefix}: {e_pd}")
    elif save_csv_flag or save_excel_flag:
        logging.warning(f"无法为 {filename_prefix} 保存 CSV/Excel，数据非字典列表格式.")

def get_authenticated_session(auth_method_choice, sso_login_file=None, cookie_file_path=None):
    session_obj = requests.Session()
    session_obj.verify = False # Disable SSL verification for all requests in this session
 
    if auth_method_choice == 'sso':
        if not SSO_AVAILABLE:
             logging.error("SSO 模块不可用."); return None
        try:
            if not sso_login_file or not os.path.exists(sso_login_file):
                logging.error(f"SSO 文件未提供或不存在: {sso_login_file}"); return None
            logging.info(f"从文件 '{sso_login_file}' 读取 SSO 凭据...")
            with open(sso_login_file, "r", encoding="utf-8") as f:
                user_name, password = f.readline().strip(), f.readline().strip()
            if not user_name or not password:
                 logging.error(f"登录文件 '{sso_login_file}' 格式不正确."); return None
            logging.info(f"尝试 SSO 为用户 '{user_name}' 认证...")
            auth_session_sso = bmw_sso_session(BASE_URL, user_name, password, session=session_obj)
            if not auth_session_sso:
                 logging.error("SSO 认证失败."); return None
            session_obj = auth_session_sso # Update session_obj with the authenticated one
            logging.info("SSO 认证成功.")
        except Exception as e:
            logging.error(f"SSO 认证过程出错: {e}"); return None
    elif auth_method_choice == 'cookie':
        # Use the provided cookie file path, fallback to default if not provided
        actual_cookie_file_path = cookie_file_path or "cookie.txt"
        try:
            logging.info(f"尝试从 '{actual_cookie_file_path}' 文件读取 Cookie...")
            if not os.path.exists(actual_cookie_file_path):
                logging.error(f"Cookie 文件 '{actual_cookie_file_path}' 未找到。"); return None
            with open(actual_cookie_file_path, "r", encoding="utf-8") as f:
                cookie_val = f.read().strip()
            if not cookie_val:
                logging.error(f"Cookie 文件 '{actual_cookie_file_path}' 为空。"); return None
            
            # 🚀 修复：使用与history_downloader.py完全相同的headers配置
            session_obj.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_val
            })
            logging.info(f"使用从 '{actual_cookie_file_path}' 文件读取的 Cookie 进行认证.")
        except IOError as e:
            logging.error(f"读取 Cookie 文件 '{actual_cookie_file_path}' 时出错: {e}"); return None
        except Exception as e:
            logging.error(f"设置 Cookie 时出错: {e}"); return None
    else:
        logging.error(f"无效认证方法: {auth_method_choice}"); return None

    # Test authentication
    # Test authentication with a simple, quick API call
    test_url = f"{API_BASE_URL}/{EP_USER}" # Example: fetching a single user
    try:
        logging.info("测试认证...")
        test_resp = session_obj.get(test_url, params={"limit": 1, "fields": "id"}, timeout=15)
        if test_resp.status_code != 200:
            logging.error(f"认证测试失败: {test_resp.status_code}. URL: {test_resp.url}"); return None
        logging.info("认证测试成功.")
    except requests.exceptions.RequestException as e:
        logging.error(f"认证测试请求失败: {e}"); return None
    return session_obj

# --- 集成的历史下载模块 (基于history_downloader.py优化版本) ---
def get_all_defect_ids_for_history(session, team="DTSV_China", start_date=None, end_date=None, filter_field="creation_time"):
    """获取符合条件的所有defect ID (集成版本)
    
    Args:
        session: 请求会话
        team: 团队名称
        start_date: 开始日期，格式为'YYYY-MM-DD'
        end_date: 结束日期，格式为'YYYY-MM-DD'
        filter_field: 筛选字段，'creation_time'或'last_modified'
        
    Returns:
        list: defect_ids
    """
    start_date_formatted = f"{start_date}T00:00:00Z" if start_date else "2000-01-01T00:00:00Z"
    end_date_formatted = f"{end_date}T23:59:59Z" if end_date else "2099-12-31T23:59:59Z"
    
    field_description = "创建" if filter_field == "creation_time" else "修改"
    logging.info(f"正在获取{team or '所有团队'}在{start_date or '不限'}至{end_date or '不限'}期间{field_description}的defect ID列表...")
    
    query_parts = []
    if team:
        safe_team_name = team.replace("'", "\\'")
        query_parts.append(f"problem_finder_team_udf={{name=\'{safe_team_name}\'}}")
    
    # 添加日期范围条件
    if start_date:
        query_parts.append(f"{filter_field}>=\'{start_date_formatted}\'")
    if end_date:
        query_parts.append(f"{filter_field}<=\'{end_date_formatted}\'")

    if not query_parts:
        logging.warning("未指定任何筛选条件，将获取所有defect")
        query = '""'
    else:
        query_string = ";".join(query_parts)
        query = f'"({query_string})"'
    
    try:
        # 使用现有的fetch_octane_data函数，它会自动处理所有分页
        resp_data = fetch_octane_data(
            session, EP_DEFECT, ("id",), query, 
            limit_per_page=DEFAULT_LIMIT_PER_PAGE, api_url=API_BASE_URL
        )
        
        if not resp_data:
            logging.info("未获取到任何defect ID")
            return []
            
        defect_ids = [item["id"] for item in resp_data]
        logging.info(f"总共获取到 {len(defect_ids)} 个符合条件的defect ID")
        return list(set(defect_ids))  # 返回唯一ID
        
    except Exception as e:
        logging.error(f"获取defect ID时发生异常: {e}")
        return []

def get_single_defect_history(defect_id, session):
    """获取单个defect的历史记录的原始内容 (集成版本，与history_downloader.py完全一致)"""
    # 🚀 修复：使用与原始history_downloader.py完全相同的API结构
    s_query = f'"(entity_id=\'{defect_id}\';entity_type=\'defect\')"'
    
    request_params = {
        "query": s_query,
        "limit": 10000, 
        "offset": 0,
        "order_by": "-timestamp"
    }
    
    # 使用与原版相同的URL拼接方式
    request_params_encoded = urllib.parse.urlencode(request_params)
    request_url = f"{API_BASE_URL}/{EP_HISTORY}?{request_params_encoded}"
    
    try:
        resp = session.get(request_url, verify=False, allow_redirects=True, timeout=90)
        
        if not (200 <= resp.status_code < 400):
            logging.warning(f"获取 defect {defect_id} 历史时出错: {resp.status_code} - {resp.text[:200]}")
            return None
        
        return resp.json()
    
    except Exception as e:
        logging.error(f"获取 defect {defect_id} 历史时发生异常: {e}")
        return None

def fetch_histories_parallel_integrated(defect_ids, session, max_workers, output_dir):
    """并行获取多个defect的原始历史记录，并保存每个历史记录到单独的JSON文件 (集成版本)"""
    processed_ids = []
    error_ids = []
    
    # 保持原来的结构：直接在输出目录下保存，不创建子目录
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"历史记录将保存到: {output_dir}")
    
    with tqdm(total=len(defect_ids), desc="🚀 获取并保存历史记录") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {
                executor.submit(get_single_defect_history, defect_id, session): defect_id 
                for defect_id in defect_ids
            }
            
            for future in concurrent.futures.as_completed(future_to_id):
                defect_id = future_to_id[future]
                try:
                    history_data = future.result() 
                    
                    if history_data and history_data.get("data"): 
                        # 保持原来的文件命名和路径格式
                        history_filename = os.path.join(output_dir, f"{defect_id}_history.json")
                        with open(history_filename, "w", encoding="utf-8") as f:
                            json.dump(history_data, f, ensure_ascii=False, indent=2)
                        processed_ids.append(defect_id)
                    elif history_data is None:
                        error_ids.append(defect_id)
                    else:
                        logging.debug(f"Defect {defect_id} 历史数据为空")
                        error_ids.append(defect_id)
                
                except Exception as e:
                    logging.error(f"处理 defect {defect_id} 历史时发生错误: {e}")
                    error_ids.append(defect_id)
                
                finally:
                    pbar.update(1)
    
    logging.info(f"历史记录获取完成！成功: {len(processed_ids)}, 失败: {len(error_ids)}")
    
    # 保存失败的ID列表
    if error_ids:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        failed_ids_filename = os.path.join(output_dir, f"failed_defect_ids_for_history_{timestamp}.json")
        with open(failed_ids_filename, "w", encoding="utf-8") as f:
            json.dump(error_ids, f, ensure_ascii=False, indent=2)
        logging.warning(f"已将获取历史失败的{len(error_ids)}个defect ID保存至: {failed_ids_filename}")
    
    return processed_ids, error_ids

# --- 新增：处理Parent缺陷关联 ---
def extract_and_download_related_defects(session, defect_data, output_dir, year_str, save_csv_flag, save_excel_flag, limit_per_page, max_workers=5):
    """
    从已下载的缺陷数据中，识别 parent_child_udf.name 包含 "Child" 的缺陷，
    然后获取这些 "Child 缺陷" 的 relation_to_udf 字段中的 "Master 缺陷 ID"，并下载这些 Master 缺陷数据。
    在保存的 Master 缺陷数据中，会额外添加一个字段 referenced_by_child_id，
    记录引用此 Master 缺陷的第一个 Child 缺陷的 ID。
    """
    if not defect_data:
        logging.info("没有缺陷数据用于提取关联关系")
        return
    
    master_to_referencing_child_ids = {}
    
    logging.info("分析缺陷数据，查找 'Child' 类型缺陷并通过 'relation_to_udf' 获取其引用的 Master 缺陷ID...")
    for defect in defect_data:
        parent_child_info = defect.get("parent_child_udf", {})
        current_child_defect_id = defect.get('id') 
        if not current_child_defect_id:
            logging.debug(f"跳过一个没有ID的缺陷项: {defect.get('name', '{}')}")
            continue
        current_child_defect_id = str(current_child_defect_id)

        if isinstance(parent_child_info, dict) and "child" in parent_child_info.get("name", "").lower():
            relation_to = defect.get("relation_to_udf")
            child_type_name = parent_child_info.get('name', '未知类型')
            master_ids_from_relation = []
            if relation_to and isinstance(relation_to, str):
                master_ids_from_relation = [d_id.strip() for d_id in relation_to.split(',') if d_id.strip()]
            elif relation_to and isinstance(relation_to, (int, float)):
                 master_ids_from_relation.append(str(relation_to))
            
            if master_ids_from_relation:
                # Log actual child ID and master IDs it points to
                logging.info(f"Child缺陷 ID: {current_child_defect_id} (类型: {child_type_name}), 从 'relation_to_udf' 解析出Master ID(s): {master_ids_from_relation}")
                for master_id in master_ids_from_relation:
                    master_to_referencing_child_ids.setdefault(master_id, []).append(current_child_defect_id)
            # else:
                # This log might be too verbose if many children don't have this field
                # logging.debug(f"Child缺陷 ID: {current_child_defect_id} (类型: {child_type_name}) 的 'relation_to_udf' 为空或无效。")

    unique_master_ids_to_fetch = list(master_to_referencing_child_ids.keys())
    for master_id in unique_master_ids_to_fetch: # Ensure child ID lists are unique, though append should handle it mostly
        master_to_referencing_child_ids[master_id] = sorted(list(set(master_to_referencing_child_ids[master_id])))

    if not unique_master_ids_to_fetch:
        logging.info("未从 'Child' 类型缺陷的 'relation_to_udf' 字段找到任何可下载的 Master 缺陷ID")
        return
    
    logging.info(f"共找到 {len(unique_master_ids_to_fetch)} 个唯一的 Master 缺陷ID，准备下载...")
    
    # 验证和分析Master ID格式
    logging.info("开始验证和分析Master ID格式...")
    valid_ids = []
    invalid_ids = []
    id_analysis = {
        'numeric_ids': [],
        'alphanumeric_ids': [],
        'special_format_ids': [],
        'empty_or_none_ids': []
    }
    
    for master_id in unique_master_ids_to_fetch:
        if not master_id or str(master_id).strip() == '':
            id_analysis['empty_or_none_ids'].append(master_id)
            invalid_ids.append(master_id)
            continue
            
        master_id_str = str(master_id).strip()
        
        # 清理包含"Defect"前缀的ID
        if master_id_str.lower().startswith('defect'):
            # 尝试提取数字部分
            numbers = re.findall(r'\d+', master_id_str)
            if numbers:
                cleaned_id = numbers[0]  # 取第一个数字序列
                logging.info(f"清理ID格式: '{master_id_str}' -> '{cleaned_id}'")
                master_id_str = cleaned_id
            else:
                logging.warning(f"无法从 '{master_id_str}' 中提取有效数字ID")
                id_analysis['empty_or_none_ids'].append(master_id)
                invalid_ids.append(master_id)
                continue
        
        # 移除可能的空格和特殊字符
        master_id_str = re.sub(r'[^\w-]', '', master_id_str)
        
        if not master_id_str:
            id_analysis['empty_or_none_ids'].append(master_id)
            invalid_ids.append(master_id)
            continue
        
        # 分析ID格式
        if master_id_str.isdigit():
            id_analysis['numeric_ids'].append(master_id_str)
            valid_ids.append(master_id_str)
        elif master_id_str.replace('-', '').replace('_', '').isalnum():
            # 包含字母数字和常见分隔符的ID（如HU22DM-350611）
            id_analysis['alphanumeric_ids'].append(master_id_str)
            valid_ids.append(master_id_str)
        elif len(master_id_str) > 0:
            # 其他特殊格式
            id_analysis['special_format_ids'].append(master_id_str)
            valid_ids.append(master_id_str)  # 仍然尝试查询
        else:
            invalid_ids.append(master_id_str)
    
    # 输出分析结果
    logging.info(f"Master ID格式分析结果:")
    logging.info(f"  纯数字ID: {len(id_analysis['numeric_ids'])} 个")
    logging.info(f"  字母数字ID: {len(id_analysis['alphanumeric_ids'])} 个")
    if id_analysis['alphanumeric_ids']:
        logging.info(f"    示例: {id_analysis['alphanumeric_ids'][:5]}")
    logging.info(f"  特殊格式ID: {len(id_analysis['special_format_ids'])} 个")
    if id_analysis['special_format_ids']:
        logging.info(f"    示例: {id_analysis['special_format_ids'][:5]}")
    logging.info(f"  无效ID: {len(id_analysis['empty_or_none_ids'])} 个")
    
    # 分析Child到Master的映射统计
    child_count_by_master = {}
    for master_id, child_ids in master_to_referencing_child_ids.items():
        child_count_by_master[master_id] = len(child_ids)
    
    if child_count_by_master:
        max_children = max(child_count_by_master.values())
        masters_with_multiple_children = {k: v for k, v in child_count_by_master.items() if v > 1}
        logging.info(f"Master缺陷关联统计:")
        logging.info(f"  最多被引用次数: {max_children}")
        logging.info(f"  被多个Child引用的Master: {len(masters_with_multiple_children)} 个")
        if masters_with_multiple_children:
            # 显示前几个被多次引用的Master
            sorted_masters = sorted(masters_with_multiple_children.items(), key=lambda x: x[1], reverse=True)
            logging.info(f"  被引用最多的Master示例: {dict(sorted_masters[:5])}")
    
    if invalid_ids:
        logging.warning(f"发现 {len(invalid_ids)} 个无效的Master ID，将跳过: {invalid_ids}")
    
    if not valid_ids:
        logging.warning("没有有效的Master ID可供下载")
        return
    
    # 使用验证后的有效ID列表
    unique_master_ids_to_fetch = valid_ids
    
    # 分析ID格式并分类
    numeric_ids = []
    non_numeric_ids = []
    for master_id in unique_master_ids_to_fetch:
        if master_id.isdigit():
            numeric_ids.append(master_id)
        else:
            non_numeric_ids.append(master_id)
    
    if non_numeric_ids:
        logging.info(f"发现 {len(non_numeric_ids)} 个非数字格式的Master ID: {non_numeric_ids[:10]}{'...' if len(non_numeric_ids) > 10 else ''}")
    
    # 记录失败的ID和原因
    failed_ids = {}
    successful_ids = set()
    
    # 🚀 超级优化：增大块大小，从20提升到50
    chunks = [unique_master_ids_to_fetch[i:i + 50] for i in range(0, len(unique_master_ids_to_fetch), 50)]
    all_master_defects_data_augmented = []
    
    for chunk_idx, chunk in enumerate(chunks):
        # 再次验证chunk中的ID格式，避免API错误
        valid_chunk_ids = []
        for chunk_id in chunk:
            chunk_id_str = str(chunk_id).strip()
            # 确保ID不包含空格或特殊字符
            if ' ' in chunk_id_str or any(char in chunk_id_str for char in ['(', ')', '[', ']', '{', '}', '"', "'"]):
                logging.warning(f"跳过包含特殊字符的ID: '{chunk_id_str}'")
                failed_ids[chunk_id_str] = "ID格式包含特殊字符"
                continue
            valid_chunk_ids.append(chunk_id_str)
        
        if not valid_chunk_ids:
            logging.warning(f"数据块 {chunk_idx + 1} 中没有有效的ID，跳过")
            continue
            
        id_conditions = [f"id='{master_id}'" for master_id in valid_chunk_ids]
        id_query = "||".join(id_conditions)
        query = f'"({id_query})"'
        
        logging.info(f"下载 Master 缺陷数据块 {chunk_idx + 1}/{len(chunks)}... (包含ID: {valid_chunk_ids})")
        logging.debug(f"查询语句: {query}")
        
        # 🚀 使用多线程并发下载Master缺陷数据块
        master_defects_chunk = fetch_octane_data_parallel(
            session, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, query, 
            limit_per_page=limit_per_page, max_workers=max_workers
        )
        
        if master_defects_chunk:
            logging.info(f"成功获取 {len(master_defects_chunk)} 条 Master 缺陷数据。开始增强数据...")
            # 记录成功获取的ID
            chunk_successful_ids = {str(item.get("id")) for item in master_defects_chunk}
            successful_ids.update(chunk_successful_ids)
            
            # 记录失败的ID
            chunk_failed_ids = set(valid_chunk_ids) - chunk_successful_ids
            for failed_id in chunk_failed_ids:
                failed_ids[failed_id] = "API查询未返回数据"
            
            for master_defect_item in master_defects_chunk:
                master_item_id = str(master_defect_item.get("id"))
                referencing_child_ids = master_to_referencing_child_ids.get(master_item_id, [])
                
                if referencing_child_ids:
                    # 存储第一个引用此Master的Child缺陷的ID
                    master_defect_item["referenced_by_child_id"] = referencing_child_ids[0]
                    if len(referencing_child_ids) > 1:
                        logging.warning(
                            f"Master 缺陷 ID {master_item_id} 被多个 Child 缺陷 "
                            f"(IDs: {referencing_child_ids}) 通过其 'relation_to_udf' 字段引用。 "
                            f"已在 'referenced_by_child_id' 中存储第一个 Child ID: {referencing_child_ids[0]}."
                        )
                else:
                    master_defect_item["referenced_by_child_id"] = None 
                    logging.warning(f"Master 缺陷 ID {master_item_id} 已获取，但在映射中未找到引用的Child ID。'referenced_by_child_id' 设置为 None.")
                
                all_master_defects_data_augmented.append(master_defect_item)
            logging.info(f"数据块 {chunk_idx + 1} 增强完成。")
        else:
            logging.warning(f"下载Master缺陷数据块 {chunk_idx + 1} 未返回任何数据。查询: {query}")
            # 记录整个chunk的失败
            for failed_id in valid_chunk_ids:
                failed_ids[failed_id] = "整个数据块查询失败"

    # 🚀 使用多线程并发重试失败的ID
    if failed_ids:
        logging.info(f"尝试并发重试 {len(failed_ids)} 个失败的Master ID...")
        retry_successful = 0
        failed_ids_list = list(failed_ids.keys())
        
        def retry_single_id(failed_id):
            try:
                single_query = f'"(id=\'{failed_id}\')"'
                logging.debug(f"并发重试Master ID: {failed_id}")
                single_result = fetch_octane_data(
                    session, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, single_query, limit_per_page=limit_per_page
                )
                
                if single_result:
                    logging.info(f"并发重试成功: Master ID {failed_id}")
                    return failed_id, single_result, None
                else:
                    return failed_id, None, "并发重试仍无数据"
            except Exception as e:
                logging.error(f"并发重试Master ID {failed_id} 时出错: {e}")
                return failed_id, None, f"重试异常: {str(e)}"
        
        # 使用线程池并发重试
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(failed_ids_list))) as executor:
            retry_futures = {executor.submit(retry_single_id, failed_id): failed_id for failed_id in failed_ids_list}
            
            for future in tqdm(concurrent.futures.as_completed(retry_futures), 
                             total=len(retry_futures), desc="🔄 并发重试失败的Master ID"):
                failed_id, single_result, error_msg = future.result()
                
                if single_result:
                    # 处理成功获取的数据
                    for master_defect_item in single_result:
                        master_item_id = str(master_defect_item.get("id"))
                        referencing_child_ids = master_to_referencing_child_ids.get(master_item_id, [])
                        master_defect_item["referenced_by_child_id"] = referencing_child_ids[0] if referencing_child_ids else None
                        all_master_defects_data_augmented.append(master_defect_item)
                    
                    # 从失败列表中移除
                    del failed_ids[failed_id]
                    successful_ids.add(failed_id)
                    retry_successful += 1
                else:
                    failed_ids[failed_id] = error_msg
        
        logging.info(f"并发重试完成，成功: {retry_successful}, 仍失败: {len(failed_ids)}")

    # 生成详细的失败报告
    if failed_ids:
        logging.warning(f"=== Master缺陷下载失败报告 ===")
        logging.warning(f"总计失败: {len(failed_ids)} 个Master ID")
        
        # 按失败原因分组
        failure_reasons = {}
        for failed_id, reason in failed_ids.items():
            failure_reasons.setdefault(reason, []).append(failed_id)
        
        for reason, ids in failure_reasons.items():
            logging.warning(f"失败原因 '{reason}': {len(ids)} 个ID")
            if len(ids) <= 10:
                logging.warning(f"  失败ID列表: {ids}")
            else:
                logging.warning(f"  失败ID示例: {ids[:10]}... (共{len(ids)}个)")
        
        # 分析失败ID对应的Child缺陷
        logging.warning("=== 受影响的Child缺陷分析 ===")
        affected_children = []
        for failed_id in failed_ids.keys():
            child_ids = master_to_referencing_child_ids.get(failed_id, [])
            for child_id in child_ids:
                affected_children.append({
                    'child_id': child_id,
                    'failed_master_id': failed_id,
                    'failure_reason': failed_ids[failed_id]
                })
        
        if affected_children:
            logging.warning(f"共有 {len(affected_children)} 个Child缺陷的Master关联下载失败")
            # 保存失败报告到文件
            failure_report_path = os.path.join(output_dir, f"{year_str}_master_download_failures.json")
            try:
                with open(failure_report_path, "w", encoding="utf-8") as f:
                    json.dump({
                        'failed_master_ids': failed_ids,
                        'affected_child_defects': affected_children,
                        'id_analysis': id_analysis,
                        'invalid_ids': invalid_ids,
                        'summary': {
                            'total_failed_masters': len(failed_ids),
                            'total_affected_children': len(affected_children),
                            'successful_masters': len(successful_ids),
                            'invalid_ids_count': len(invalid_ids),
                            'total_requested_masters': len(unique_master_ids_to_fetch) + len(invalid_ids)
                        }
                    }, f, ensure_ascii=False, indent=2)
                logging.info(f"失败报告已保存到: {failure_report_path}")
            except Exception as e:
                logging.error(f"保存失败报告时出错: {e}")

    # 保存成功获取的数据
    if all_master_defects_data_augmented:
        filename = f"{year_str}_defect_master"
        save_data(all_master_defects_data_augmented, filename, output_dir, save_csv_flag, save_excel_flag)
        logging.info(f"已将 {len(all_master_defects_data_augmented)} 个 Master缺陷数据（已增强 referenced_by_child_id）保存到 {filename}")
        logging.info(f"成功率: {len(successful_ids)}/{len(unique_master_ids_to_fetch)} ({len(successful_ids)/len(unique_master_ids_to_fetch)*100:.1f}%)")
    else:
        logging.warning("未能获取任何Master缺陷数据进行保存，或增强后数据为空。")

# --- MAIN LOGIC ---
def main():
    global DEFAULT_LIMIT_PER_PAGE  # 🚀 在函数开始就声明global变量
    
    parser = argparse.ArgumentParser(description="从 Octane API 下载 Defects, Manual Runs, 和 Defect History 数据.")
    
    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument("--auth-method", choices=['sso', 'cookie'], help="认证方法.")
    auth_group.add_argument("--login-file", default="login_info.txt", help="SSO 用户名密码文件 (for --auth-method=sso)")
    auth_group.add_argument("--cookie-file", default="cookie.txt", help="Cookie 文件路径 (for --auth-method=cookie)")

    general_group = parser.add_argument_group('General Download Options')
    general_group.add_argument("--team", default=DEFAULT_TEAM, help=f"默认查询团队 (默认: {DEFAULT_TEAM})")
    general_group.add_argument("--save-csv", action='store_true', help="同时保存为 CSV")
    general_group.add_argument("--save-excel", action='store_true', help="同时保存为 Excel (需要 openpyxl)")
    general_group.add_argument("--limit-per-page", type=int, default=DEFAULT_LIMIT_PER_PAGE, help=f"API 分页大小 (默认: {DEFAULT_LIMIT_PER_PAGE})")

    defect_group = parser.add_argument_group('Defect Main Data Download')
    defect_group.add_argument("--skip-defects", action='store_true', help="跳过下载 Defects 主数据")
    # 🔄 修改：默认下载当前年份以及之前两年（确保包含2024及以后）
    current_year = datetime.now().year
    default_years = f"{current_year-2},{current_year-1},{current_year}"
    defect_group.add_argument("--defect-years", default=default_years, help=f"Defects 年份列表 (默认: {default_years})")

    mr_group = parser.add_argument_group('Manual Run Data Download')
    mr_group.add_argument("--skip-mr", action='store_true', help="跳过下载 Manual Runs")
    # 🔄 修改：默认下载当前年份以及之前两年的 Manual Runs
    current_year = datetime.now().year
    default_mr_spec = f"{current_year-2}:01-13,{current_year-1}:01-13,{current_year}:01-13"
    mr_group.add_argument("--mr-spec", default=default_mr_spec, help=f"Manual Runs 年份和 Release 范围 (默认: {default_mr_spec})")

    history_group = parser.add_argument_group('🚀 集成历史下载 (基于history_downloader.py优化, 默认启用)')
    history_group.add_argument("--fetch-history", action='store_true', default=True, help="启用集成的历史下载 (默认: 启用)")
    history_group.add_argument("--skip-history", action='store_true', help="跳过历史下载 (禁用默认的历史下载)")
    history_group.add_argument("--history-max-workers", type=int, default=50, help="并行下载历史线程数 (1-50, 默认: 50)")
    history_group.add_argument("--history-output-dir", default="history", help="保存历史记录的目录 (默认: history, 与history_downloader.py一致)")
    history_group.add_argument("--history-team", default=None, help="历史下载的团队名称 (默认: 使用--team参数)")
    history_group.add_argument("--history-start-date", default=None, help="历史下载开始日期 YYYY-MM-DD (默认: 当年1月1日)")
    history_group.add_argument("--history-end-date", default=None, help="历史下载结束日期 YYYY-MM-DD (默认: 今天)")
    history_group.add_argument("--history-filter-field", choices=['creation_time', 'last_modified'], default='creation_time', help="历史筛选字段 (默认: creation_time)")

    # 新增选项: 是否下载关联的parent缺陷
    parser.add_argument("--skip-parent-related", action='store_true', help="跳过下载Parent关联的缺陷")
    parser.add_argument("--enable-master-diagnostics", action='store_true', help="启用Master缺陷下载的详细诊断和错误报告")
    
    # 🚀 性能优化选项
    performance_group = parser.add_argument_group('Performance Optimization')
    performance_group.add_argument("--turbo-mode", action='store_true', help="🚀 启用极限性能模式 (更大分页+更多并发+极小延迟)")
    performance_group.add_argument("--max-concurrent-requests", type=int, default=10, help="最大并发请求数 (默认: 10, 极限模式: 25)")

    args = parser.parse_args()

    # 🚀 应用性能优化设置
    if args.turbo_mode:
        # 极限性能模式
        DEFAULT_LIMIT_PER_PAGE = 10000  # 极限分页大小
        args.history_max_workers = min(25, args.history_max_workers * 2)  # 双倍历史并发
        args.max_concurrent_requests = 25  # 最大并发
        logging.info("🚀 极限性能模式已启用！分页大小=10000，延迟=0.001s，历史并发=25，最大并发=25")
    else:
        logging.info("🚀 超级性能优化模式：分页大小=5000，延迟=0.01s，历史并发=15，最大线程=50")

    team_to_use = args.team # General team for defects and MRs

    auth_method_selected = args.auth_method
    if not auth_method_selected: # If no auth method provided via command line, use cookie as default
        auth_method_selected = 'cookie'  # 默认使用cookie认证
        logging.info(f"使用默认认证方法: {auth_method_selected}")
    else:
        logging.info(f"选择认证方法: {auth_method_selected}")

    if auth_method_selected == 'sso':
        if not SSO_AVAILABLE:
            logging.error("SSO 模块 (sso_session.py) 未找到，无法使用SSO认证。")
            return
        if not os.path.exists(args.login_file):
            logging.error(f"SSO 登录文件 '{args.login_file}' 未找到。")
            return
    elif auth_method_selected == 'cookie':
        logging.info(f"当前工作目录: {os.getcwd()}")
        logging.info(f"查找Cookie文件: {args.cookie_file}")
        logging.info(f"Cookie文件绝对路径: {os.path.abspath(args.cookie_file)}")
        if not os.path.exists(args.cookie_file):
            logging.error(f"Cookie 文件 '{args.cookie_file}' 未找到。请通过 --cookie-file 指定正确路径或确保文件存在。")
            logging.error(f"当前工作目录中的文件: {os.listdir('.')}")
            return

    if auth_method_selected == 'sso':
        session_active = get_authenticated_session(auth_method_selected, sso_login_file=args.login_file)
    else:  # cookie method
        session_active = get_authenticated_session(auth_method_selected, cookie_file_path=args.cookie_file)
    if not session_active:
        logging.critical("认证失败，脚本终止."); return

    script_dir_path = os.path.dirname(os.path.abspath(__file__))
    defect_main_output_path = os.path.join(script_dir_path, "defect")  # 修改为"defect"目录
    mr_output_path = os.path.join(script_dir_path, "mr")
    history_output_path_base = os.path.join(script_dir_path, args.history_output_dir)
    
    # 存储每年下载的defect数据，用于后续处理Parent关联
    year_to_defects_map = {}

    # --- Download Defects (Main Data) ---
    if not args.skip_defects and args.defect_years:
        os.makedirs(defect_main_output_path, exist_ok=True)
        years_list_defect = [y.strip() for y in args.defect_years.split(',') if y.strip().isdigit() and len(y.strip()) == 4]
        for year_str_defect in years_list_defect:
            logging.info(f"下载 {year_str_defect} Defects (团队: {team_to_use})...")
            start_t_str, end_t_str = f"{year_str_defect}-01-01T00:00:00Z", f"{year_str_defect}-12-31T23:59:59Z"
            
            # Corrected defect query construction
            time_query_part = f"creation_time>=\'{start_t_str}\';creation_time<=\'{end_t_str}\'"
            
            team_query_parts = []
            if team_to_use:
                safe_team_name = team_to_use.replace("'", "\\'") # Escape single quotes in team name
                # Use object literal with single quotes (escaped) — mirrors downloader6
                team_query_parts.append(f"problem_finder_team_udf={{name=\'{safe_team_name}\'}}")
                team_query_parts.append(f"author={{name=\'{safe_team_name}\'}}") 
                team_query_parts.append(f"team={{name=\'{safe_team_name}\'}}")    
            
            team_combined_part = ""
            if team_query_parts:
                team_combined_part = f"({'||'.join(team_query_parts)})"

            if team_combined_part:
                # Query for defects created in the time range AND (found by PFT OR authored by OR assigned to team)
                q_defect_inner = f"({time_query_part});{team_combined_part}"
            else: 
                q_defect_inner = f"({time_query_part})" 
            
            q_defect = f'"({q_defect_inner})"'
            logging.debug(f"Constructed defect query: {q_defect}")
            
            # 🚀 使用多线程并发下载defect数据
            defect_data_list = fetch_octane_data_parallel(
                session_active, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, q_defect,
                order_by="creation_time", limit_per_page=args.limit_per_page,
                max_workers=args.max_concurrent_requests
            )
            
            if defect_data_list:
                # 保存为文件
                fn_defect = f"{year_str_defect}_defect" # 文件名中移除 team_to_use
                save_data(defect_data_list, fn_defect, defect_main_output_path, args.save_csv, args.save_excel)
                
                # 保存到年份映射，用于后续处理Parent关联
                year_to_defects_map[year_str_defect] = defect_data_list
            else:
                logging.info(f"{year_str_defect} 年未找到团队 '{team_to_use}' Defects.")
    elif args.skip_defects: 
        logging.info("跳过 Defects 主数据下载.")

    # --- 处理Parent关联缺陷 ---
    if not args.skip_defects and not args.skip_parent_related and year_to_defects_map:
        logging.info("开始处理 'Child' 关联缺陷 (通过 'relation_to_udf' 查找其关联缺陷)...") # 更新日志信息
        for year_str, defects_data in year_to_defects_map.items():
            extract_and_download_related_defects(
                session_active,
                defects_data,
                defect_main_output_path,
                year_str,
                args.save_csv,
                args.save_excel,
                args.limit_per_page,
                max_workers=args.max_concurrent_requests
            )
    elif args.skip_parent_related:
        logging.info("跳过处理Parent关联缺陷.")

    # --- Download Manual Runs ---
    if not args.skip_mr and args.mr_spec:
        os.makedirs(mr_output_path, exist_ok=True)
        year_specs_mr = args.mr_spec.split(',')
        for spec_mr in year_specs_mr:
            try:
                if ':' not in spec_mr: logging.error(f"MR 规范 '{spec_mr}' 格式错误. 期望格式: 'YYYY:范围', e.g., '2024:01-05;07&09'."); continue
                year_s, rel_s_raw = spec_mr.strip().split(':', 1)
                year_v = int(year_s)
                if not (2000 < year_v < 2100): raise ValueError("年份无效")
                
                rels_fetch = []
                # Process semicolon-separated groups first (for OR logic between groups if intended, though current query is AND)
                for group_mr_semicolon in rel_s_raw.split(';'):
                    # Process ampersand-separated items within each semicolon group (for AND logic if intended)
                    for group_mr_ampersand in group_mr_semicolon.split('&'):
                        group_mr = group_mr_ampersand.strip()
                        if not group_mr: continue
                        if '-' in group_mr: # Range like "01-05"
                            s, e = map(int, group_mr.split('-'))
                            if s > e: raise ValueError(f"Release范围无效: {group_mr}")
                            rels_fetch.extend([f"{i:02d}" for i in range(s, e + 1)])
                        elif group_mr.isdigit() and 1 <= int(group_mr) <= 99: # Single number
                            rels_fetch.append(f"{int(group_mr):02d}")
                        else:
                            logging.warning(f"跳过无效release部分: '{group_mr}' in '{spec_mr}'")
                
                rels_fetch = sorted(list(set(rels_fetch))) # Unique and sorted
                if not rels_fetch: logging.warning(f"'{spec_mr}'未解析出有效Release."); continue

                logging.info(f"下载 {year_v} Manual Runs for releases: {rels_fetch} (团队: {team_to_use})")
                for rel_num_str in rels_fetch: # rel_num_str is already formatted like "01", "05"
                    rel_name = f"R-{str(year_v)[-2:]}-{rel_num_str}" # Correct release name format
                    logging.info(f"  下载 {rel_name}...")
                    # Query for MRs of the team AND in the specified release
                    safe_team_mr = team_to_use.replace("'", "\\'")
                    q_mr = f'"(run_team_000_udf={{name=\'{safe_team_mr}\'}});(release={{name=\'{rel_name}\'}})"'
                    logging.debug(f"Constructed MR query: {q_mr}")
                    # 🚀 使用多线程并发下载manual run数据
                    mr_data = fetch_octane_data_parallel(
                        session_active, EP_MANUALRUN, DEFAULT_F_MANUALRUN, q_mr,
                        limit_per_page=args.limit_per_page,
                        max_workers=args.max_concurrent_requests
                    )
                    if mr_data:
                        # 文件名中移除 team_to_use
                        fn_mr = f"R{str(year_v)[-2:]}{rel_num_str}" 
                        save_data(mr_data, fn_mr, mr_output_path, args.save_csv, args.save_excel)
                    else:
                        logging.info(f"  {rel_name} (团队: {team_to_use}) 无数据.") # 日志中仍然可以保留团队信息以便追踪
            except ValueError as e_mr_val: logging.error(f"解析 MR 规范 '{spec_mr}' 出错: {e_mr_val}")
            except Exception as e_mr_exc: logging.error(f"处理 MR 规范 '{spec_mr}' 时未知错误: {e_mr_exc}")
    elif args.skip_mr: 
        logging.info("跳过 Manual Runs 下载.")

    # --- 集成的历史下载 (基于history_downloader.py优化版本, 默认启用) ---
    if args.fetch_history and not args.skip_history:
        logging.info(f"--- 🚀 开始下载 Defect History (集成优化版本, 默认启用) ---")
        os.makedirs(history_output_path_base, exist_ok=True)

        # 🔄 修改：默认下载当前年份以及之前两年的历史数据（以覆盖更早年份如2024）
        current_year = datetime.now().year
        default_start_date = f"{current_year-2}-01-01"
        default_end_date = datetime.now().strftime("%Y-%m-%d")
        hist_start_date = args.history_start_date or default_start_date
        hist_end_date = args.history_end_date or default_end_date
        # normalize user-provided dates so that they always have two-digit month/day
        try:
            normalized_start = normalize_iso_date(hist_start_date)
            normalized_end = normalize_iso_date(hist_end_date)
        except Exception as e:
            logging.error(f"历史日期格式无效: start='{hist_start_date}', end='{hist_end_date}' -> {e}")
            return
        if normalized_start != hist_start_date or normalized_end != hist_end_date:
            logging.info(f"已规范化历史日期: '{hist_start_date}'->{normalized_start}, "
                         f"'{hist_end_date}'->{normalized_end}")
        hist_start_date = normalized_start
        hist_end_date = normalized_end
        history_team = args.history_team or team_to_use  # 优先使用专门的历史团队参数
        history_filter_field = args.history_filter_field

        logging.info(f"🚀 集成历史下载配置:")
        logging.info(f"  团队: {history_team}")
        logging.info(f"  筛选字段: {history_filter_field}")
        logging.info(f"  日期范围: {hist_start_date} 至 {hist_end_date}")
        logging.info(f"  并发线程: {args.history_max_workers}")

        # 获取符合条件的defect ID列表
        defect_ids_for_history = get_all_defect_ids_for_history(
            session_active,
            team=history_team,
            start_date=hist_start_date,
            end_date=hist_end_date,
            filter_field=history_filter_field
        )

        if not defect_ids_for_history:
            logging.info(f"未找到团队 '{history_team}' 在 {hist_start_date} 至 {hist_end_date} 的Defects用于历史下载.")
        else:
            hist_max_workers_val = min(max(1, args.history_max_workers), 50)
            logging.info(f"🚀 使用 {hist_max_workers_val} 线程并行获取 {len(defect_ids_for_history)} 个Defects的历史记录...")
            
            # 使用集成的并行历史下载函数
            processed_ids, error_ids = fetch_histories_parallel_integrated(
                defect_ids_for_history,
                session_active,
                hist_max_workers_val,
                history_output_path_base
            )
            
            # 显示详细统计信息
            success_rate = (len(processed_ids) / len(defect_ids_for_history) * 100) if defect_ids_for_history else 0
            logging.info(f"🚀 历史下载完成统计:")
            logging.info(f"  总计Defects: {len(defect_ids_for_history)}")
            logging.info(f"  成功下载: {len(processed_ids)}")
            logging.info(f"  失败数量: {len(error_ids)}")
            logging.info(f"  成功率: {success_rate:.1f}%")
    elif args.skip_history:
        logging.info("跳过 Defect History 下载 (因指定了 --skip-history).")
    else:
        logging.info("跳过 Defect History 下载 (未启用).")

    logging.info("所有指定任务完成.")

if __name__ == "__main__":
    main()
