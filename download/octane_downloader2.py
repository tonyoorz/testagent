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
import sys

try:
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from octane_db import OctaneSQLiteStore, default_db_path
    OCTANE_DB_AVAILABLE = True
except Exception:
    OCTANE_DB_AVAILABLE = False

try:
    from pg_storage import OctanePostgresStore, default_pg_url
    POSTGRES_DB_AVAILABLE = True
except Exception:
    POSTGRES_DB_AVAILABLE = False
    def default_pg_url():
        return ""

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

DEFAULT_COOKIE = "GUEST_LANGUAGE_ID=en_US; i18next=english; rxVisitor=1744613931631B6MLA5NP6DPA5LIVUM9BJ21MS3QBPFUP; dtSa=-; rxvt=1744857836387|1744856036387; dtPC=3$527970904_157h-vSGPCCISHODRVURAJBWSFIRIUHMHFKPJD-0e0; dtCookie=v_4_srv_3_sn_5NK42I4QNH2GA03S7UH3N7O9F2DJ6BQ1_perc_100000_ol_0_mul_1_app-3A2579a82aa388e4a2_1_app-3A3a336dbc3f55ee1c_1_rcs-3Acss_0; XSRF_COOKIE=4men8boi1mfdn4oiaarg4br81a; OCTANE_USER=dc6d2a07c6a31c45350e22733238fa8c72b667594ae4b0eb0a15934c6117a882; lbwen=01; wen=iOx1wHFcscVRmtNKOA-Kx_7Sol0.*AAJTSQACMDEAAlNLABxpV1QwVXh0K0puZktDQ0p6ZlZRUEcvcWVhWFU9AAR0eXBlAANDVFMAAlMxAAA.*; access_token=eHwAIKaPJljQGTXxemKQWOAwFssjbqFVXWi02gHBQQK2vfAzy1hCiQQ0LsEo9luaod5Glfk2h1rrYIM2uRy05aNyanze5uURS3E702WFPMoehLPDr_XhE_5p384spqRNU2-PsYQUaGtEM79hNeU4Qowy4Lh2B_sihhEr1X0V5ry_lUHdcH6gfQlJ1Nh9jDYlsa9z0zrUZizDzh52nrLYs3T_TAbE68rNFx-mAScaQYRdDSb1Ym-fUqh0cRRf_MKVCtw9TOk02Juxopenhrt372_g88a-pkT9NrtEplssXJKg-wiqw7L6VG094HwtXqB5KgWnyDx1zfkM7sa8hU81YgW_Hvg; JSESSIONID=node09bzqdju7vxwo8t6v7dbgvwao53155.node0; HPECLIENTTYPE=HPE_MQM_UI"

# API 端点
EP_DEFECT = "defects"
EP_MANUALRUN = "manual_runs"
EP_USER = "workspace_users"
EP_HISTORY = "history_logs"

DEFAULT_F_DEFECT_MAIN = (
    "id", "name", "creation_time", "last_modified", "parent_child_udf", "team",
    "vin_udf", "user_tags", "tqr_udf", "product_areas", "aida_businesskey_udf",
    "software_version_udf", "ecu_no_of_changes_udf", "first_use_sop_of_function_udf",
    "tolerated_count_udf", "blocking_reason_udf", "reprel_changes_udf",
    "requirements", "parent", "assigned_ecu_udf", "error_occurrence_udf",
    "parent_phase_udf", "sab_comment_udf", "relation_to_udf",
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
            resp.raise_for_status()
            data = resp.json()
            batch_data = data.get("data", [])
            batch_size = len(batch_data)
            total_count_api = data.get("total_count")
            total_count = int(total_count_api) if isinstance(total_count_api, int) else 0

            if not batch_data and offset == 0:
                logging.info(f"端点 '{endpoint}' 查询没有返回任何数据。"); break
            if not batch_data:
                logging.info(f"获取到空数据页，假定数据已全部获取. 总计 {total_fetched} 条."); break
            
            all_data.extend(batch_data)
            total_fetched += batch_size
            logging.info(f"成功获取 {batch_size} 条数据，累计 {total_fetched} 条 (API报告总数: {total_count_api if total_count_api is not None else '未知'}).")

            if total_count > 0 and total_fetched >= total_count:
                logging.info(f"已获取 API 报告的所有 {total_fetched} 条数据."); break
            if batch_size < limit_per_page:
                logging.info(f"获取到的数据 ({batch_size}) 少于分页限制 ({limit_per_page})，已获取所有数据. 总计 {total_fetched} 条."); break
            offset += limit_per_page
            time.sleep(0.3)
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

def get_authenticated_session(auth_method_choice, sso_login_file=None, cookie_file=None):
    session_obj = requests.Session()
    session_obj.verify = False

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
            session_obj = auth_session_sso
            logging.info("SSO 认证成功.")
        except Exception as e:
            logging.error(f"SSO 认证过程出错: {e}"); return None
    elif auth_method_choice == 'cookie':
        # allow cookie to come from a file (cookie.txt) if it exists, otherwise fall back to
        # the hard‑coded DEFAULT_COOKIE.  downloader7 already uses the file path, so the
        # behaviour here is intentionally aligned.
        cookie_val = None
        # `cookie_file` argument passed from caller (parser) takes precedence
        if cookie_file and os.path.exists(cookie_file):
            try:
                logging.info(f"尝试从 '{cookie_file}' 文件读取 Cookie...")
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookie_val = f.read().strip()
            except IOError as e:
                logging.error(f"读取 Cookie 文件 '{cookie_file}' 时出错: {e}"); return None
        if cookie_file and os.path.exists(cookie_file):
            try:
                logging.info(f"尝试从 '{cookie_file}' 文件读取 Cookie...")
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookie_val = f.read().strip()
            except IOError as e:
                logging.error(f"读取 Cookie 文件 '{cookie_file}' 时出错: {e}"); return None
        # if we didn't get a cookie file or it was empty, use the default constant
        if not cookie_val:
            cookie_val = DEFAULT_COOKIE
            if not cookie_val:
                logging.error("预定义 Cookie 为空!"); return None
            logging.warning("未提供或无法读取 cookie 文件，使用硬编码 DEFAULT_COOKIE（可能已过期）")
        try:
            session_obj.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_val
            })
            logging.info("使用 Cookie 认证.")
        except Exception as e:
            logging.error(f"设置 Cookie 时出错: {e}"); return None
    else:
        logging.error(f"无效认证方法: {auth_method_choice}"); return None

    test_url = f"{API_BASE_URL}/{EP_USER}"
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
    
    query_hist = f'"(problem_finder_team_udf={{name=\'{team_name_hist}\'}};{filter_field_hist}>=\'{start_date_formatted}\';{filter_field_hist}<=\'{end_date_formatted}\')"'
    
    defects_data = fetch_octane_data(
        session, EP_DEFECT, F_DEFECT_FOR_HISTORY_IDS, query_hist,
        limit_per_page=limit_per_page_hist, api_url=API_BASE_URL
    )
    all_defect_ids_hist = [item["id"] for item in defects_data] if defects_data else []
    logging.info(f"为历史获取了 {len(all_defect_ids_hist)} 个 Defect ID.")
    return list(set(all_defect_ids_hist))

def get_single_defect_history_module(defect_id_hist, session_hist):
    # history endpoint must include workspace path (same as downloader7); otherwise returns 403
    history_api_url_actual = f"{API_BASE_URL}/{EP_HISTORY}"
    # build URL manually to avoid requests sometimes reordering or quoting differently
    s_query_hist = f"\"(entity_id='{defect_id_hist}';entity_type='defect')\""
    request_params_hist = {
        "query": s_query_hist,
        # use slightly larger limit like downloader7 for safety
        "limit": 10000,
        "offset": 0,
        "order_by": "-timestamp"
    }
    request_params_encoded = urllib.parse.urlencode(request_params_hist)
    request_url_hist = f"{history_api_url_actual}?{request_params_encoded}"
    
    try:
        resp_hist = session_hist.get(request_url_hist, verify=False, allow_redirects=True, timeout=90)
        if not (200 <= resp_hist.status_code < 300):
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
                    if raw_history_data and raw_history_data.get("total_count", 0) > 0:
                        history_filename = f"{defect_id_current}_history"
                        save_data(raw_history_data, history_filename, individual_hist_dir, save_csv_flag=save_csv_hist)
                        processed_count += 1
                    elif raw_history_data and raw_history_data.get("total_count", 0) == 0:
                        logging.info(f"Defect {defect_id_current} 无历史记录.")
                        processed_count +=1 
                    else:
                        logging.warning(f"未能获取Defect {defect_id_current}历史或历史为空.")
                        error_count += 1
                except Exception as e_proc_hist:
                    logging.error(f"处理Defect ID {defect_id_current}历史时出错: {e_proc_hist}")
                    error_count += 1
                finally: pbar_hist.update(1)
    
    logging.info(f"Defect历史获取完成. 成功下载: {processed_count}, 失败: {error_count}")
    return processed_count, error_count

def fetch_defect_histories_parallel_to_db(defect_ids_list_hist, session_obj_hist, max_workers_hist, store_obj, team_name, save_files_dir=None, save_csv_hist=False):
    processed_count = 0
    error_count = 0
    stores = list(store_obj) if isinstance(store_obj, (list, tuple)) else [store_obj]

    individual_hist_dir = None
    if save_files_dir:
        individual_hist_dir = os.path.join(save_files_dir, "individual_raw_histories")
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
                    if raw_history_data is None:
                        logging.warning(f"未能获取Defect {defect_id_current}历史.")
                        error_count += 1
                        continue

                    write_failed = False
                    for single_store in stores:
                        try:
                            single_store.upsert_defect_history(
                                defect_id=str(defect_id_current),
                                team=team_name,
                                payload=raw_history_data,
                                total_count=raw_history_data.get("total_count") if isinstance(raw_history_data, dict) else None,
                            )
                        except Exception as e_db:
                            logging.error(f"写入数据库失败 Defect {defect_id_current}: {e_db}")
                            write_failed = True
                            break
                    if write_failed:
                        error_count += 1
                        continue

                    if save_files_dir:
                        history_filename = f"{defect_id_current}_history"
                        save_data(raw_history_data, history_filename, individual_hist_dir, save_csv_flag=save_csv_hist)

                    processed_count += 1
                except Exception as e_proc_hist:
                    logging.error(f"处理Defect ID {defect_id_current}历史时出错: {e_proc_hist}")
                    error_count += 1
                finally:
                    pbar_hist.update(1)

    logging.info(f"Defect历史获取完成. 成功处理: {processed_count}, 失败: {error_count}")
    return processed_count, error_count

# --- MAIN LOGIC ---
def main():
    parser = argparse.ArgumentParser(description="从 Octane API 下载 Defects, Manual Runs, 和 Defect History 数据.")
    
    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument("--auth-method", choices=['sso', 'cookie'], help="认证方法.")
    auth_group.add_argument("--login-file", default="login_info.txt", help="SSO 用户名密码文件 (for --auth-method=sso)")
    auth_group.add_argument("--cookie-file", default="cookie.txt", help="Cookie 文件路径 (for --auth-method=cookie, 默认: cookie.txt)")

    general_group = parser.add_argument_group('General Download Options')
    general_group.add_argument("--team", default=DEFAULT_TEAM, help=f"默认查询团队 (默认: {DEFAULT_TEAM})")
    general_group.add_argument("--save-csv", action='store_true', help="同时保存为 CSV")
    general_group.add_argument("--save-excel", action='store_true', help="同时保存为 Excel (需要 openpyxl)")
    general_group.add_argument("--limit-per-page", type=int, default=DEFAULT_LIMIT_PER_PAGE, help=f"API 分页大小 (默认: {DEFAULT_LIMIT_PER_PAGE})")
    general_group.add_argument("--db-path", default=None, help="SQLite 数据库路径 (默认: 自动优先 database/local_data_rebuilt.db, 否则 database/local_data.db)")
    general_group.add_argument("--skip-db", action='store_true', help="跳过写入 SQLite 数据库")
    general_group.add_argument("--skip-file-output", action='store_true', help="不输出 JSON/CSV/Excel 文件，仅写入数据库（如启用）")
    general_group.add_argument("--legacy-schema", action='store_true', help="使用旧表结构(仅保留原始JSON，不展平字段)")
    general_group.add_argument("--enable-pg", action='store_true', help="启用 PostgreSQL 双写（默认关闭）")
    general_group.add_argument("--pg-url", default=default_pg_url(), help="PostgreSQL 连接串，支持环境变量 POSTGRES_URL")
    general_group.add_argument("--pg-schema", default=os.environ.get("PG_SCHEMA", "public"), help="PostgreSQL schema (默认: public)")
    general_group.add_argument("--pg-only", action='store_true', help="仅写入 PostgreSQL（SQLite 仍保持可用逻辑，不会被删除）")

    defect_group = parser.add_argument_group('Defect Main Data Download')
    defect_group.add_argument("--skip-defects", action='store_true', help="跳过下载 Defects 主数据")
    defect_group.add_argument("--defect-years", default=datetime.now().strftime('%Y'), help="Defects 年份列表 (e.g., '2024,2025')")
    defect_group.add_argument("--fetch-master", action='store_true', help="同时下载 Master Defect 数据 (用于enrichment)")

    mr_group = parser.add_argument_group('Manual Run Data Download')
    mr_group.add_argument("--skip-mr", action='store_true', help="跳过下载 Manual Runs")
    mr_group.add_argument("--mr-spec",default=f"{datetime.now().strftime('%Y')}:01-13", help="Manual Runs 年份和 Release 范围.")

    history_group = parser.add_argument_group('Defect History Download (Automated for current year)')
    # history is enabled by default; use --no-fetch-history to disable
    history_group.add_argument("--fetch-history", action='store_true', default=True,
                               help="启用 Defect History 下载 (当年至今, DTSV_China, 按last_modified) 默认启用")
    history_group.add_argument("--no-fetch-history", action='store_false', dest='fetch_history',
                               help="禁用 Defect History 下载 (与 --fetch-history 相反)")
    history_group.add_argument("--history-max-workers", type=int, default=5, help="并行下载历史线程数 (1-20, 默认: 5)")
    history_group.add_argument("--history-output-dir", default="history_files", help="保存原始Defect History JSON的目录 (默认: history_files)")

    args = parser.parse_args()

    team_to_use = args.team # General team for defects and MRs

    auth_method_selected = args.auth_method
    if not auth_method_selected:
        while True:
            print("\n选择认证方法:\n1: SSO\n2: Cookie (预定义)")
            choice = input("选项 (1 or 2): ").strip()
            if choice == '1': auth_method_selected = 'sso'; break
            elif choice == '2': auth_method_selected = 'cookie'; break
            else: print("无效选择.")
        logging.info(f"选择认证方法: {auth_method_selected}")

    if auth_method_selected == 'sso':
        if not SSO_AVAILABLE or not os.path.exists(args.login_file):
            logging.error(f"SSO 不可用或登录文件 '{args.login_file}' 未找到.")
            return

    # choose appropriate parameters for the auth function
    if auth_method_selected == 'cookie':
        session_active = get_authenticated_session(auth_method_selected, args.login_file, cookie_file=args.cookie_file)
    else:
        session_active = get_authenticated_session(auth_method_selected, args.login_file)
    if not session_active:
        logging.critical("认证失败."); return

    script_dir_path = os.path.dirname(os.path.abspath(__file__))
    repo_root_path = os.path.dirname(script_dir_path)
    # 默认存储到根目录，与现有项目结构兼容
    defect_main_output_path = os.path.join(repo_root_path, "defect")
    # MR 数据目录应与其他 downloader 脚本一致 ("mr" 而非 "mr_data")
    mr_output_path = os.path.join(repo_root_path, "mr")
    history_output_path_base = os.path.join(repo_root_path, args.history_output_dir)

    sqlite_store = None
    pg_store = None
    store_targets = []

    if args.pg_only and not args.enable_pg:
        logging.error("指定了 --pg-only 但未启用 --enable-pg")
        return

    # SQLite (legacy + optimized tables) — keep existing behavior by default.
    if not args.skip_db and not args.pg_only:
        if not OCTANE_DB_AVAILABLE:
            logging.error("SQLite 模块不可用，已跳过写入 SQLite。")
        else:
            db_path = args.db_path or default_db_path(repo_root_path)
            try:
                sqlite_store = OctaneSQLiteStore(db_path)
                sqlite_store.create_tables()
                if not args.legacy_schema:
                    sqlite_store.create_optimized_tables()
                    logging.info(f"SQLite 数据库已启用: {db_path} (使用优化表结构)")
                else:
                    logging.info(f"SQLite 数据库已启用: {db_path} (使用旧表结构)")
                store_targets.append(("sqlite", sqlite_store))
            except Exception as e_db_init:
                logging.error(f"初始化 SQLite 失败，已跳过写入: {e_db_init}")
                sqlite_store = None

    # PostgreSQL (optional dual-write)
    if args.enable_pg:
        if not POSTGRES_DB_AVAILABLE:
            logging.error("PostgreSQL 模块不可用，请先安装 psycopg 或 psycopg2。")
            if args.pg_only:
                return
        elif not args.pg_url:
            logging.error("启用 PostgreSQL 失败：缺少 --pg-url 或 POSTGRES_URL")
            if args.pg_only:
                return
        else:
            try:
                pg_store = OctanePostgresStore(args.pg_url, schema=args.pg_schema)
                pg_store.create_tables()
                if not args.legacy_schema:
                    pg_store.create_optimized_tables()
                logging.info(f"PostgreSQL 已启用: schema={args.pg_schema}")
                store_targets.append(("postgres", pg_store))
            except Exception as e_pg_init:
                logging.error(f"初始化 PostgreSQL 失败，已跳过写入: {e_pg_init}")
                pg_store = None
                if args.pg_only:
                    return

    if args.skip_file_output and not store_targets:
        logging.error("已禁用文件输出，但没有可用数据库写入目标，任务已终止。")
        return

    # --- Download Defects (Main Data) ---
    if not args.skip_defects and args.defect_years:
        os.makedirs(defect_main_output_path, exist_ok=True)
        years_list_defect = [y.strip() for y in args.defect_years.split(',') if y.strip().isdigit() and len(y.strip()) == 4]
        for year_str_defect in years_list_defect:
            logging.info(f"下载 {year_str_defect} Defects (团队: {team_to_use})...")
            start_t, end_t = f"{year_str_defect}-01-01T00:00:00Z", f"{year_str_defect}-12-31T23:59:59Z"
            # construct query in the safer style used by downloader7; avoid wrapping the whole
            # expression in literal quotes which the API rejects.
            time_query_part = f"creation_time>='{start_t}';creation_time<='{end_t}'"
            team_query_parts = []
            if team_to_use:
                safe_team = team_to_use.replace("'", "\\'")
                team_query_parts.append(f"problem_finder_team_udf={{name='{safe_team}'}}")
                team_query_parts.append(f"author={{name='{safe_team}'}}")
                team_query_parts.append(f"team={{name='{safe_team}'}}")

            team_combined = ''
            if team_query_parts:
                team_combined = '(' + '||'.join(team_query_parts) + ')'

                if team_combined:
                    inner = f"({time_query_part});{team_combined}"
                else:
                    inner = f"({time_query_part})"

                q_defect = f'"({inner})"'
                logging.debug(f"构建的 defect 查询: {q_defect}")
            
            defect_data_list = fetch_octane_data(
                session_active, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, q_defect,
                order_by="creation_time", limit_per_page=args.limit_per_page
            )
            if defect_data_list:
                # 与项目现有命名规范兼容: 2025_defect.json
                fn_defect = f"{year_str_defect}_defect"
                if store_targets:
                    for store_name, store_obj in store_targets:
                        try:
                            store_obj.upsert_payload(
                                kind="defects",
                                team=team_to_use,
                                year=int(year_str_defect),
                                spec="",
                                payload={"data": defect_data_list},
                            )
                            logging.info(f"  [{store_name}] 已保存旧表: {len(defect_data_list)} 条 defects")

                            if not args.legacy_schema:
                                try:
                                    count = store_obj.upsert_defects_batch(
                                        defects=defect_data_list,
                                        year=int(year_str_defect),
                                    )
                                    logging.info(f"  [{store_name}] 已保存优化表: {count} 条 defects")
                                except Exception as e_opt:
                                    logging.error(f"  [{store_name}] 保存优化表失败: {e_opt}")
                        except Exception as e_db_write:
                            logging.error(f"[{store_name}] 写入 defects {year_str_defect} 失败: {e_db_write}")
                if not args.skip_file_output:
                    save_data(defect_data_list, fn_defect, defect_main_output_path, args.save_csv, args.save_excel)

                # --- Download Master Defects (for enrichment) ---
                if args.fetch_master:
                    logging.info(f"  下载 {year_str_defect} Master Defects (parent defects)...")
                    # 获取所有有parent_id的defect的parent
                    parent_ids = set()
                    for d in defect_data_list:
                        parent = d.get('parent')
                        if parent and isinstance(parent, dict):
                            pid = parent.get('id')
                            if pid:
                                parent_ids.add(str(pid))

                    if parent_ids:
                        logging.info(f"    发现 {len(parent_ids)} 个唯一的 parent IDs")
                        # 批量获取parent defects (每次100个)
                        parent_id_list = list(parent_ids)
                        batch_size = 100
                        master_defects = []
                        for i in range(0, len(parent_id_list), batch_size):
                            batch = parent_id_list[i:i+batch_size]
                            id_query = '||'.join([f"id='{pid}'" for pid in batch])
                            q_master = f'"({id_query})"'

                            master_batch = fetch_octane_data(
                                session_active, EP_DEFECT, DEFAULT_F_DEFECT_MAIN, q_master,
                                limit_per_page=batch_size, api_url=API_BASE_URL
                            )
                            if master_batch:
                                master_defects.extend(master_batch)
                            time.sleep(0.3)

                        if master_defects:
                            fn_master = f"{year_str_defect}_defect_master"
                            logging.info(f"    成功下载 {len(master_defects)} 条 Master Defects")
                            if not args.skip_file_output:
                                save_data(master_defects, fn_master, defect_main_output_path, args.save_csv, args.save_excel)
                        else:
                            logging.info(f"    未找到 Master Defects")
                    else:
                        logging.info(f"    没有发现需要下载的 parent IDs")
            else:
                logging.info(f"{year_str_defect} 年未找到团队 '{team_to_use}' Defects.")
    elif args.skip_defects: logging.info("跳过 Defects 主数据下载.")

    # --- Download Manual Runs ---
    if not args.skip_mr and args.mr_spec:
        os.makedirs(mr_output_path, exist_ok=True)
        year_specs_mr = args.mr_spec.split(',')
        for spec_mr in year_specs_mr:
            try:
                if ':' not in spec_mr: logging.error(f"MR 规范 '{spec_mr}' 格式错误."); continue
                year_s, rel_s = spec_mr.strip().split(':', 1)
                year_v = int(year_s)
                if not (2000 < year_v < 2100): raise ValueError("年份无效")
                
                rels_fetch = []
                for group_mr in rel_s.split(';'):
                    group_mr = group_mr.strip()
                    if not group_mr: continue
                    if '-' in group_mr:
                        s, e = map(int, group_mr.split('-'))
                        if s > e: raise ValueError(f"Release范围无效: {group_mr}")
                        rels_fetch.extend([f"{i:02d}" for i in range(s, e + 1)])
                    else:
                         for r_str in group_mr.split('&'):
                              r_str = r_str.strip()
                              if r_str.isdigit() and 1 <= int(r_str) <= 99: rels_fetch.append(f"{int(r_str):02d}")
                              else: logging.warning(f"跳过无效release: '{r_str}' in '{spec_mr}'")
                
                rels_fetch = sorted(list(set(rels_fetch)))
                if not rels_fetch: logging.warning(f"'{spec_mr}'未解析出有效Release."); continue

                logging.info(f"下载 {year_v} Manual Runs for releases: {rels_fetch} (团队: {team_to_use})")
                for rel_num in rels_fetch:
                    rel_name = f"R-{str(year_v)[-2:]}-{rel_num}"
                    logging.info(f"  下载 {rel_name}...")
                    q_mr = f'"(run_team_000_udf={{name=\'{team_to_use}\'}});(release={{name=\'{rel_name}\'}})"'
                    mr_data = fetch_octane_data(
                        session_active, EP_MANUALRUN, DEFAULT_F_MANUALRUN, q_mr,
                        limit_per_page=args.limit_per_page
                    )
                    if mr_data: # Only save if data is found
                        fn_mr = f"R{str(year_v)[-2:]}{rel_num}_{team_to_use}"
                        if store_targets:
                            for store_name, store_obj in store_targets:
                                try:
                                    store_obj.upsert_payload(
                                        kind="manual_runs",
                                        team=team_to_use,
                                        year=year_v,
                                        spec=rel_name,
                                        payload={"data": mr_data},
                                    )
                                    logging.info(f"  [{store_name}] 已保存旧表: {len(mr_data)} 条 manual runs")

                                    if not args.legacy_schema:
                                        try:
                                            count = store_obj.upsert_manual_runs_batch(
                                                manual_runs=mr_data,
                                                year=year_v,
                                                spec=rel_name,
                                            )
                                            logging.info(f"  [{store_name}] 已保存优化表: {count} 条 manual runs")
                                        except Exception as e_opt:
                                            logging.error(f"  [{store_name}] 保存优化表失败: {e_opt}")
                                except Exception as e_db_write:
                                    logging.error(f"[{store_name}] 写入 manual_runs {rel_name} 失败: {e_db_write}")
                        if not args.skip_file_output:
                            save_data(mr_data, fn_mr, mr_output_path, args.save_csv, args.save_excel)
                    else:
                        logging.info(f"  {rel_name} (团队: {team_to_use}) 无数据.")
            except ValueError as e_mr_val: logging.error(f"解析 MR 规范 '{spec_mr}' 出错: {e_mr_val}")
            except Exception as e_mr_exc: logging.error(f"处理 MR 规范 '{spec_mr}' 时未知错误: {e_mr_exc}")
    elif args.skip_mr: logging.info("跳过 Manual Runs 下载.")

    # --- Download Defect History (Automated for current year) ---
    if args.fetch_history:
        logging.info(f"--- 开始下载 Defect History (当年至今, 团队: {DEFAULT_TEAM}) ---")
        if not args.skip_file_output:
            os.makedirs(history_output_path_base, exist_ok=True)

        current_year_str = str(datetime.now().year)
        hist_start_date_val = f"{current_year_str}-01-01"
        hist_end_date_val = datetime.now().strftime("%Y-%m-%d")
        history_team_fixed = DEFAULT_TEAM # Fixed team for history
        history_filter_field_fixed = "last_modified" # Fixed filter field

        logging.info(f"自动历史下载: 团队 '{history_team_fixed}', 日期范围 '{hist_start_date_val}' 至 '{hist_end_date_val}', 筛选字段 '{history_filter_field_fixed}'.")

        defect_ids_for_history_list = get_defect_ids_for_history_module(
            session_active,
            history_team_fixed,
            hist_start_date_val,
            hist_end_date_val,
            history_filter_field_fixed,
            args.limit_per_page
        )

        if not defect_ids_for_history_list:
            logging.info(f"未找到团队 '{history_team_fixed}' 在 {hist_start_date_val} 至 {hist_end_date_val} 的Defects用于历史下载.")
        else:
            hist_max_workers_val = min(max(1, args.history_max_workers), 20)
            logging.info(f"使用 {hist_max_workers_val} 线程并行获取 {len(defect_ids_for_history_list)} Defects的原始历史...")
            if store_targets:
                fetch_defect_histories_parallel_to_db(
                    defect_ids_for_history_list,
                    session_active,
                    hist_max_workers_val,
                    [s for _, s in store_targets],
                    history_team_fixed,
                    save_files_dir=history_output_path_base if not args.skip_file_output else None,
                    save_csv_hist=args.save_csv,
                )
            else:
                if args.skip_file_output:
                    logging.error("未启用任何数据库写入且已禁用文件输出，历史数据无法保存。")
                else:
                    fetch_defect_histories_parallel(
                        defect_ids_for_history_list,
                        session_active,
                        hist_max_workers_val,
                        history_output_path_base,
                        args.save_csv
                    )
    else:
        logging.info("跳过 Defect History 下载 (已禁用).")

    logging.info("所有指定任务完成.")

    for _, store_obj in store_targets:
        try:
            store_obj.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
