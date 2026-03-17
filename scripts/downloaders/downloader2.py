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
DEFAULT_LIMIT_PER_PAGE = 1000

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
    "sab_comment_udf.name",  # 只获取name字段
    "requirements", 
    "parent",
    "parent_phase_udf", # 新增
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
F_DEFECT_FOR_HISTORY_IDS = ("id", "name", "last_modified", "creation_time", "team", "problem_finder_team_udf", "severity", "phase", "owner", "detected_in_release")

DEFAULT_TEAM = "DTSV_China" # Default team for all operations unless overridden by specific args

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
            time.sleep(0.3) # Be a good API citizen
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

def get_authenticated_session(auth_method_choice, sso_login_file=None):
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
                # 首先尝试JSON格式
                try:
                    login_data = json.load(f)
                    if isinstance(login_data, dict):
                        user_name = login_data.get("username")
                        password = login_data.get("password")
                        if user_name and password:
                            logging.info(f"成功从JSON格式文件读取用户 '{user_name}' 的登录凭据")
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
                        user_name = lines[0].strip()
                        password = lines[1].strip()
                        logging.info(f"成功从行格式文件读取用户 '{user_name}' 的登录凭据")
                    else:
                        logging.error(f"登录文件 '{sso_login_file}' 格式不正确.")
                        return None
                        
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
        cookie_file_path = "cookie.txt"
        try:
            logging.info(f"尝试从 '{cookie_file_path}' 文件读取 Cookie...")
            if not os.path.exists(cookie_file_path):
                logging.error(f"Cookie 文件 '{cookie_file_path}' 未找到。"); return None
            with open(cookie_file_path, "r", encoding="utf-8") as f:
                cookie_val = f.read().strip()
            if not cookie_val:
                logging.error(f"Cookie 文件 '{cookie_file_path}' 为空。"); return None
            
            session_obj.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_val
            })
            logging.info(f"使用从 '{cookie_file_path}' 文件读取的 Cookie 进行认证.")
        except IOError as e:
            logging.error(f"读取 Cookie 文件 '{cookie_file_path}' 时出错: {e}"); return None
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

# --- DEFECT HISTORY MODULE ---
def get_defect_ids_for_history_module(session, team_name_hist, start_date_hist, end_date_hist, filter_field_hist, limit_per_page_hist):
    start_date_formatted = f"{start_date_hist}T00:00:00Z"
    end_date_formatted = f"{end_date_hist}T23:59:59Z"
    field_description = "创建" if filter_field_hist == "creation_time" else "修改"
    logging.info(f"获取团队 '{team_name_hist}' 在 {start_date_hist} 至 {end_date_hist} 期间按'{field_description}'筛选的Defect ID列表 (用于历史)...")
    
    # Escape single quotes in team_name_hist if it might contain them
    safe_team_name_hist = team_name_hist.replace("'", "\\'")
    query_hist = f'"(problem_finder_team_udf={{name=\'{safe_team_name_hist}\'}};{filter_field_hist}>=\'{start_date_formatted}\';{filter_field_hist}<=\'{end_date_formatted}\')"'
    
    defects_data = fetch_octane_data(
        session, EP_DEFECT, F_DEFECT_FOR_HISTORY_IDS, query_hist,
        limit_per_page=limit_per_page_hist, api_url=API_BASE_URL
    )
    all_defect_ids_hist = [item["id"] for item in defects_data] if defects_data else []
    logging.info(f"为历史获取了 {len(all_defect_ids_hist)} 个 Defect ID.")
    return list(set(all_defect_ids_hist)) # Return unique IDs

def get_single_defect_history_module(defect_id_hist, session_hist):
    history_api_url_actual = f"{API_SHARED_SPACES_URL}/{EP_HISTORY}" # Correct API for history logs
    s_query_hist = f'"(entity_id=\'{defect_id_hist}\';entity_type=\'defect\')"'
    request_params_hist = {"query": s_query_hist, "limit": 5000, "offset": 0, "order_by": "-timestamp"}
    
    try:
        # Use session_hist which should be the authenticated session object
        resp_hist = session_hist.get(history_api_url_actual, params=request_params_hist, verify=False, allow_redirects=True, timeout=90)
        if not (200 <= resp_hist.status_code < 300): # Check for successful status codes
            logging.warning(f"获取Defect ID {defect_id_hist}历史失败: {resp_hist.status_code}. URL: {resp_hist.url}")
            return None
        return resp_hist.json()
    except Exception as e_hist:
        logging.error(f"获取Defect ID {defect_id_hist}历史时异常: {e_hist}")
        return None

def fetch_defect_histories_parallel(defect_ids_list_hist, session_obj_hist, max_workers_hist, hist_output_dir_actual, save_csv_hist=False):
    processed_count = 0
    error_count = 0
    individual_hist_dir = os.path.join(hist_output_dir_actual, "individual_raw_histories")
    os.makedirs(individual_hist_dir, exist_ok=True)
    logging.info(f"单个defect原始历史将保存到: {individual_hist_dir}")

    with tqdm(total=len(defect_ids_list_hist), desc="获取Defect历史") as pbar_hist:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_hist) as executor_hist:
            future_to_id_hist = {
                executor_hist.submit(get_single_defect_history_module, df_id, session_obj_hist): df_id
                for df_id in defect_ids_list_hist
            }
            for future_hist in concurrent.futures.as_completed(future_to_id_hist):
                defect_id_current = future_to_id_hist[future_hist]
                try:
                    raw_history_data = future_hist.result()
                    if raw_history_data and raw_history_data.get("total_count", 0) > 0: # Check if history itself has data
                        history_filename = f"{defect_id_current}_history"

                        # Pass the raw_history_data (which is the full JSON object for that history)
                        save_data(raw_history_data, history_filename, individual_hist_dir, save_csv_flag=save_csv_hist) # Save the whole object
                        processed_count += 1
                    elif raw_history_data and raw_history_data.get("total_count", 0) == 0:
                        logging.info(f"Defect {defect_id_current} 无历史记录.")
                        # Optionally save an empty file or a note? For now, just log.
                        processed_count +=1 # Still counts as processed if API confirmed no history
                    else: # raw_history_data is None or malformed
                        logging.warning(f"未能获取Defect {defect_id_current}历史或历史为空/格式错误.")
                        error_count += 1
                except Exception as e_proc_hist:
                    logging.error(f"处理Defect ID {defect_id_current}历史时出错: {e_proc_hist}")
                    error_count += 1
                finally: pbar_hist.update(1)
    
    logging.info(f"Defect历史获取完成. 成功下载/处理: {processed_count}, 失败: {error_count}")
    return processed_count, error_count

# --- 新增：处理Parent缺陷关联 ---
def extract_and_download_related_defects(session, defect_data, output_dir, year_str, save_csv_flag, save_excel_flag, limit_per_page):
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
    
    # Explicitly create the chunks list first - 处理所有ID（数字和非数字）
    chunks = [unique_master_ids_to_fetch[i:i + 20] for i in range(0, len(unique_master_ids_to_fetch), 20)]
    all_master_defects_data_augmented = []
    
    for chunk_idx, chunk in enumerate(chunks): # Now iterate over the defined 'chunks' variable
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
        
        master_defects_chunk = fetch_octane_data(
            session, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, query, limit_per_page=limit_per_page
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

    # 尝试单独重试失败的ID（仅针对可能的权限或临时问题）
    if failed_ids:
        logging.info(f"尝试单独重试 {len(failed_ids)} 个失败的Master ID...")
        retry_successful = 0
        for failed_id in list(failed_ids.keys()):
            try:
                single_query = f'"(id=\'{failed_id}\')"'
                logging.debug(f"单独重试Master ID: {failed_id}")
                single_result = fetch_octane_data(
                    session, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, single_query, limit_per_page=limit_per_page
                )
                
                if single_result:
                    logging.info(f"单独重试成功: Master ID {failed_id}")
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
                    failed_ids[failed_id] = "单独重试仍无数据"
                    
                time.sleep(0.1)  # 避免过于频繁的请求
            except Exception as e:
                logging.error(f"单独重试Master ID {failed_id} 时出错: {e}")
                failed_ids[failed_id] = f"重试异常: {str(e)}"
        
        logging.info(f"单独重试完成，成功: {retry_successful}, 仍失败: {len(failed_ids)}")

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
    defect_group.add_argument("--defect-years", default=datetime.now().strftime('%Y'), help="Defects 年份列表 (e.g., '2024,2025')")

    mr_group = parser.add_argument_group('Manual Run Data Download')
    mr_group.add_argument("--skip-mr", action='store_true', help="跳过下载 Manual Runs")
    mr_group.add_argument("--mr-spec",default=f"{datetime.now().strftime('%Y')}:01-13", help="Manual Runs 年份和 Release 范围 (e.g., '2024:01-05;07&09,2025:01-12').")

    history_group = parser.add_argument_group('Defect History Download (Automated for current year)')
    history_group.add_argument("--fetch-history", action='store_true', help="启用 Defect History 下载 (当年至今, DTSV_China, 按last_modified)")
    history_group.add_argument("--history-max-workers", type=int, default=5, help="并行下载历史线程数 (1-20, 默认: 5)")
    history_group.add_argument("--history-output-dir", default="history_files", help="保存原始Defect History JSON的目录 (默认: history_files)")

    # 新增选项: 是否下载关联的parent缺陷
    parser.add_argument("--skip-parent-related", action='store_true', help="跳过下载Parent关联的缺陷")
    parser.add_argument("--enable-master-diagnostics", action='store_true', help="启用Master缺陷下载的详细诊断和错误报告")

    args = parser.parse_args()

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
        if not os.path.exists(args.cookie_file):
            logging.error(f"Cookie 文件 '{args.cookie_file}' 未找到。请通过 --cookie-file 指定正确路径或确保文件存在。")
            return

    session_active = get_authenticated_session(auth_method_selected, args.login_file if auth_method_selected == 'sso' else args.cookie_file)
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
            
            defect_data_list = fetch_octane_data(
                session_active, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, q_defect,
                order_by="creation_time", limit_per_page=args.limit_per_page
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
                args.limit_per_page
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
                    mr_data = fetch_octane_data(
                        session_active, EP_MANUALRUN, DEFAULT_F_MANUALRUN, q_mr,
                        limit_per_page=args.limit_per_page
                    )
                    if mr_data:
                        # 文件名中移除 team_to_use
                        fn_mr = f"R{str(year_v)[-2:]}{rel_num_str}" 
                        save_data(mr_data, fn_mr, mr_output_path, args.save_csv, args.save_excel)
                    else:
                        logging.info(f"  {rel_name} (团队: {team_to_use}) 无数据.") # 日志中仍然可以保留团队信息以便追踪
            except ValueError as e_mr_val: logging.error(f"解析 MR 规范 '{spec_mr}' 出错: {e_mr_val}")
            except Exception as e_mr_exc: logging.error(f"处理 MR 规范 '{spec_mr}' 时未知错误: {e_mr_exc}")
    elif args.skip_mr: logging.info("跳过 Manual Runs 下载.")

    # --- Download Defect History (Automated for current year) ---
    if args.fetch_history:
        logging.info(f"--- 开始下载 Defect History (当年至今, 团队: {DEFAULT_TEAM}) ---")
        os.makedirs(history_output_path_base, exist_ok=True)

        current_year_str = str(datetime.now().year)
        # Default to current year, Jan 1st to today for history
        hist_start_date_val = f"{current_year_str}-01-01"
        hist_end_date_val = datetime.now().strftime("%Y-%m-%d")
        history_team_fixed = DEFAULT_TEAM # Use the general default team for history downloads
        history_filter_field_fixed = "last_modified" 

        logging.info(f"自动历史下载: 团队 '{history_team_fixed}', 日期范围 '{hist_start_date_val}' 至 '{hist_end_date_val}', 筛选字段 '{history_filter_field_fixed}'.")

        defect_ids_for_history_list = get_defect_ids_for_history_module(
            session_active,
            history_team_fixed,
            hist_start_date_val,
            hist_end_date_val,
            history_filter_field_fixed,
            args.limit_per_page # Use general limit per page for fetching defect IDs
        )

        if not defect_ids_for_history_list:
            logging.info(f"未找到团队 '{history_team_fixed}' 在 {hist_start_date_val} 至 {hist_end_date_val} 的Defects用于历史下载.")
        else:
            hist_max_workers_val = min(max(1, args.history_max_workers), 20) # Clamp between 1 and 20
            logging.info(f"使用 {hist_max_workers_val} 线程并行获取 {len(defect_ids_for_history_list)} Defects的原始历史...")
            
            fetch_defect_histories_parallel(
                defect_ids_for_history_list,
                session_active,
                hist_max_workers_val,
                history_output_path_base,
                args.save_csv # Pass CSV saving flag for individual history files if needed
            )
    else:
        logging.info("跳过 Defect History 下载 (因未指定 --fetch-history).")

    logging.info("所有指定任务完成.")

if __name__ == "__main__":
    main()
