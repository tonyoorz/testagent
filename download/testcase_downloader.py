import json
import time
import urllib.parse
import requests
import logging
from datetime import datetime, timedelta
import os
import argparse
import urllib3
import concurrent.futures
from tqdm import tqdm
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
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pd = None
    PANDAS_AVAILABLE = False

# 尝试导入 sso_session，如果失败则告知用户
try:
    from sso_session import bmw_sso_session
    SSO_AVAILABLE = True
except ImportError:
    SSO_AVAILABLE = False
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
DEFAULT_LIMIT_PER_PAGE = 100
DEFAULT_DTSV_PAGE_LIMIT = 500
DEFAULT_DTSV_WORKERS = 8

DEFAULT_COOKIE = "GUEST_LANGUAGE_ID=en_US; i18next=english; rxVisitor=1744613931631B6MLA5NP6DPA5LIVUM9BJ21MS3QBPFUP; dtSa=-; rxvt=1744857836387|1744856036387; dtPC=3$527970904_157h-vSGPCCISHODRVURAJBWSFIRIUHMHFKPJD-0e0; dtCookie=v_4_srv_3_sn_5NK42I4QNH2GA03S7UH3N7O9F2DJ6BQ1_perc_100000_ol_0_mul_1_app-3A2579a82aa388e4a2_1_app-3A3a336dbc3f55ee1c_1_rcs-3Acss_0; XSRF_COOKIE=4men8boi1mfdn4oiaarg4br81a; OCTANE_USER=dc6d2a07c6a31c45350e22733238fa8c72b667594ae4b0eb0a15934c6117a882; lbwen=01; wen=iOx1wHFcscVRmtNKOA-Kx_7Sol0.*AAJTSQACMDEAAlNLABxpV1QwVXh0K0puZktDQ0p6ZlZRUEcvcWVhWFU9AAR0eXBlAANDVFMAAlMxAAA.*; access_token=eHwAIKaPJljQGTXxemKQWOAwFssjbqFVXWi02gHBQQK2vfAzy1hCiQQ0LsEo9luaod5Glfk2h1rrYIM2uRy05aNyanze5uURS3E702WFPMoehLPDr_XhE_5p384spqRNU2-PsYQUaGtEM79hNeU4Qowy4Lh2B_sihhEr1X0V5ry_lUHdcH6gfQlJ1Nh9jDYlsa9z0zrUZizDzh52nrLYs3T_TAbE68rNFx-mAScaQYRdDSb1Ym-fUqh0cRRf_MKVCtw9TOk02Juxopenhrt372_g88a-pkT9NrtEplssXJKg-wiqw7L6VG094HwtXqB5KgWnyDx1zfkM7sa8hU81YgW_Hvg; JSESSIONID=node09bzqdju7vxwo8t6v7dbgvwao53155.node0; HPECLIENTTYPE=HPE_MQM_UI"

# API 端点
EP_TESTS = "tests"
EP_RUNS = "runs"
EP_WORK_ITEMS = "work_items"

# 字段定义
FIELDS_EPIC_TESTS = [
    "package", "class_name", "test_priority_udf", "testing_tool_type", 
    "followed_by_me", "has_attachments", "name", "owner", "creation_time", 
    "id", "phase", "test_type", "covered_manual_test", "test_status", "author", 
    "subtype", "owner{full_name}", "author{full_name}", 
    "covered_content{entity_icon,subtype}", "covered_requirement{entity_icon,subtype}", 
    "product_areas{entity_icon}", "covered_manual_test{subtype}"
]

FIELDS_TEST_RUNS = [
    "manual", "draft_run", "runs_in_suite", "cluster", "past_status", 
    "has_attachments", "started", "sprint", "error_type", "error_message", 
    "test", "name", "duration", "native_status", "parent_suite", "id", 
    "taxonomies", "error_details", "author", "run_by", "blocked_by_previous_run", 
    "subtype", "build", "author{full_name}", "run_by{full_name}", 
    "release{end_date}", "milestone{release_specific,date,release}", 
    "runs_in_suite{subtype}", "test{subtype,id,name}", "parent_suite{subtype}", 
    "taxonomies{subtype}", "linked_defects", "defect", 
    "test{covered_manual_test{id,name,subtype},covered_content{id,name,subtype,path,parent}}", 
    "status", "test_name", "run_team_000_udf", "release"
]

FIELDS_EPIC_FEATURES = [
    "rank", "followed_by_me", "has_attachments", "story_points", "name", 
    "owner", "id", "phase", "blocked", "author", "tasks_number", "subtype", 
    "is_in_filter", "limit_line", "metaphase", "start_date", "cycle_time_value", 
    "waste", "shared", "entity_icon", "owner{full_name}", "author{full_name}", 
    "parent{entity_icon,subtype}", "release{end_date}", 
    "detected_in_release{end_date}", "milestone{release_specific,date,release}"
]

FIELDS_FEATURE_TESTS = FIELDS_EPIC_TESTS  # 使用相同的字段

FIELDS_TESTS_ENRICH = [
    "id", "name", "subtype",
    "covered_manual_test{id,name,subtype}",
    "covered_content{id,name,subtype,path,parent{id,name,subtype}}",
]

FIELDS_WORKITEMS_BY_RUN = [
    "id", "name", "subtype",
    "parent{id,name,subtype}",
]

def fetch_octane_data(session, endpoint, fields, query, limit_per_page=DEFAULT_LIMIT_PER_PAGE, order_by=None):
    """获取Octane API数据"""
    all_data = []
    offset = 0
    total_fetched = 0
    
    logging.info(f"开始从端点 '{endpoint}' 获取数据，查询条件: {query}")
    
    while True:
        request_params = {
            "fields": ",".join(fields) if isinstance(fields, (list, tuple)) else fields,
            "query": query,
            "limit": limit_per_page,
            "offset": offset
        }
        if order_by:
            request_params["order_by"] = order_by
        
        request_url_full = f"{API_BASE_URL}/{endpoint}"
        logging.debug(f"请求 URL: {request_url_full} with params: {request_params}")
        
        try:
            resp = session.get(request_url_full, params=request_params, verify=False, allow_redirects=True, timeout=60)
            if resp.status_code == 401:
                logging.error(f"认证失败 (401). URL: {resp.url}")
                return []
            elif resp.status_code == 403:
                logging.error(f"权限不足 (403). URL: {resp.url}")
                return []
            elif resp.status_code == 404:
                logging.warning(f"资源未找到 (404). URL: {resp.url}")
                break
            elif resp.status_code >= 400:
                logging.error(f"请求失败: {resp.status_code}. URL: {resp.url}. Response: {resp.text[:500]}")
                break
            
            resp.raise_for_status()
            data = resp.json()
            batch_data = data.get("data", [])
            batch_size = len(batch_data)
            total_count_api = data.get("total_count")
            total_count = int(total_count_api) if isinstance(total_count_api, int) else 0

            if not batch_data and offset == 0:
                logging.info(f"端点 '{endpoint}' 查询没有返回任何数据。")
                break
            if not batch_data:
                logging.info(f"获取到空数据页，假定数据已全部获取. 总计 {total_fetched} 条.")
                break
            
            all_data.extend(batch_data)
            total_fetched += batch_size
            logging.info(f"成功获取 {batch_size} 条数据，累计 {total_fetched} 条 (API报告总数: {total_count_api if total_count_api is not None else '未知'}).")

            if total_count > 0 and total_fetched >= total_count:
                logging.info(f"已获取 API 报告的所有 {total_fetched} 条数据.")
                break
            if batch_size < limit_per_page:
                logging.info(f"获取到的数据 ({batch_size}) 少于分页限制 ({limit_per_page})，已获取所有数据. 总计 {total_fetched} 条.")
                break
            
            offset += limit_per_page
            time.sleep(0.3)
            
        except requests.exceptions.Timeout:
            logging.warning(f"请求超时: {request_url_full}")
            break
        except requests.exceptions.RequestException as e:
            logging.error(f"请求端点 '{endpoint}' 时发生网络或请求错误: {e}")
            break
        except json.JSONDecodeError as e:
            logging.error(f"解析JSON失败: {e}. Response: {resp.text[:500]}")
            break
        except Exception as e:
            logging.error(f"处理请求时发生未知错误 '{endpoint}': {e}")
            break
    
    logging.info(f"从端点 '{endpoint}' 数据获取完成，共获取 {len(all_data)} 条数据。")
    return all_data

def _request_page(session, endpoint, fields, query, limit_per_page, offset, order_by=None, timeout=60):
    request_params = {
        "fields": ",".join(fields) if isinstance(fields, (list, tuple)) else fields,
        "query": query,
        "limit": limit_per_page,
        "offset": offset,
    }
    if order_by:
        request_params["order_by"] = order_by

    request_url_full = f"{API_BASE_URL}/{endpoint}"
    resp = session.get(request_url_full, params=request_params, verify=False, allow_redirects=True, timeout=timeout)
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}: {resp.text[:300]}", response=resp)

    data = resp.json()
    page_data = data.get("data", [])
    total_count_api = data.get("total_count")
    total_count = int(total_count_api) if isinstance(total_count_api, int) else 0
    return page_data, total_count, total_count_api

def fetch_octane_data_parallel(session, endpoint, fields, query, limit_per_page=DEFAULT_DTSV_PAGE_LIMIT, order_by=None, max_workers=DEFAULT_DTSV_WORKERS):
    """并发分页拉取，适合大数据量端点（如 DTSV 全量 runs）。"""
    all_data = []
    logging.info(f"开始并发获取端点 '{endpoint}' 数据，查询条件: {query}")

    try:
        first_page, total_count, total_count_api = _request_page(
            session=session,
            endpoint=endpoint,
            fields=fields,
            query=query,
            limit_per_page=limit_per_page,
            offset=0,
            order_by=order_by,
            timeout=90,
        )
    except Exception as e:
        logging.error(f"并发拉取初始化失败: {e}")
        return []

    if not first_page:
        logging.info(f"端点 '{endpoint}' 查询没有返回任何数据。")
        return []

    all_data.extend(first_page)
    fetched = len(first_page)
    logging.info(f"成功获取 {len(first_page)} 条数据，累计 {fetched} 条 (API报告总数: {total_count_api if total_count_api is not None else '未知'}).")

    if total_count <= fetched:
        logging.info(f"并发拉取完成，共获取 {len(all_data)} 条数据。")
        return all_data

    offsets = list(range(limit_per_page, total_count, limit_per_page))
    page_results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                _request_page,
                session,
                endpoint,
                fields,
                query,
                limit_per_page,
                off,
                order_by,
                90,
            ): off
            for off in offsets
        }

        for future in concurrent.futures.as_completed(future_map):
            off = future_map[future]
            try:
                page_data, _, _ = future.result()
                page_results[off] = page_data
                fetched += len(page_data)
                logging.info(f"成功获取 {len(page_data)} 条数据，累计 {fetched} 条 (API报告总数: {total_count}).")
            except Exception as e:
                logging.error(f"offset={off} 的分页请求失败: {e}")

    for off in sorted(page_results.keys()):
        all_data.extend(page_results[off])

    logging.info(f"并发拉取完成，共获取 {len(all_data)} 条数据。")
    return all_data

def save_data(data_to_save, filename_prefix, output_directory, save_csv_flag=False, save_excel_flag=False):
    """保存数据到文件"""
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
                if not PANDAS_AVAILABLE:
                    logging.warning("未安装 pandas，跳过 CSV/Excel 导出。请执行: pip install pandas")
                    return
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

def save_dtsv_dataset_to_db(dataset, db_path=None):
    """将 dtsv-all testcase 数据写入优化 SQLite 表。"""
    if not OCTANE_DB_AVAILABLE:
        raise RuntimeError("octane_db 模块不可用，无法写入 SQLite。")

    target_db_path = db_path or default_db_path(_repo_root)
    store = OctaneSQLiteStore(target_db_path)
    try:
        store.create_tables()
        store.create_optimized_tables()
        result = store.upsert_testcase_dataset(dataset)
        logging.info(
            "testcase 数据已写入 SQLite: %s (testcases=%s, relations=%s)",
            target_db_path,
            result.get("testcases", 0),
            result.get("relations", 0),
        )
        return target_db_path, result
    finally:
        store.close()

def _load_cookie_from_file(cookie_file_path):
    if not cookie_file_path:
        return None
    if not os.path.exists(cookie_file_path):
        logging.warning(f"Cookie 文件不存在: {cookie_file_path}")
        return None
    try:
        with open(cookie_file_path, "r", encoding="utf-8") as f:
            cookie_val = f.read().strip()
        if not cookie_val:
            logging.warning(f"Cookie 文件为空: {cookie_file_path}")
            return None
        return cookie_val
    except Exception as e:
        logging.warning(f"读取 Cookie 文件失败: {cookie_file_path}, 错误: {e}")
        return None

def get_authenticated_session(auth_method_choice, sso_login_file=None, cookie_file_path=None):
    """获取认证会话"""
    session_obj = requests.Session()
    session_obj.verify = False

    if auth_method_choice == 'sso':
        if not SSO_AVAILABLE:
            logging.error("SSO 模块不可用.")
            return None
        try:
            if not sso_login_file or not os.path.exists(sso_login_file):
                logging.error(f"SSO 文件未提供或不存在: {sso_login_file}")
                return None
            logging.info(f"从文件 '{sso_login_file}' 读取 SSO 凭据...")
            with open(sso_login_file, "r", encoding="utf-8") as f:
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
                    f.seek(0)
                    lines = f.readlines()
                    if len(lines) >= 2:
                        user_name = lines[0].strip()
                        password = lines[1].strip()
                        logging.info(f"成功从行格式文件读取用户 '{user_name}' 的登录凭据")
                    else:
                        logging.error(f"登录文件 '{sso_login_file}' 格式不正确.")
                        return None
            logging.info(f"尝试 SSO 为用户 '{user_name}' 认证...")
            auth_session_sso = bmw_sso_session(BASE_URL, user_name, password, session=session_obj)
            if not auth_session_sso:
                logging.error("SSO 认证失败.")
                return None
            session_obj = auth_session_sso
            logging.info("SSO 认证成功.")
        except Exception as e:
            logging.error(f"SSO 认证过程出错: {e}")
            return None
    elif auth_method_choice == 'cookie':
        try:
            cookie_val = _load_cookie_from_file(cookie_file_path)
            if cookie_val:
                logging.info(f"使用 Cookie 文件认证: {cookie_file_path}")
            else:
                cookie_val = DEFAULT_COOKIE
                logging.warning("Cookie 文件不可用，回退到内置默认 Cookie（可能已过期）。")
            if not cookie_val:
                logging.error("未找到可用 Cookie。请先运行: python playwright_cookie_manager.py --refresh")
                return None
            session_obj.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_val
            })
            if len(cookie_val) < 50:
                logging.warning("当前 Cookie 字符串长度异常偏短，可能无效。")
        except Exception as e:
            logging.error(f"设置 Cookie 时出错: {e}")
            return None
    else:
        logging.error(f"无效认证方法: {auth_method_choice}")
        return None

    # 测试认证
    test_url = f"{API_BASE_URL}/workspace_users"
    try:
        logging.info("测试认证...")
        test_resp = session_obj.get(test_url, params={"limit": 1, "fields": "id"}, timeout=15)
        if test_resp.status_code != 200:
            logging.error(f"认证测试失败: {test_resp.status_code}. URL: {test_resp.url}")
            if auth_method_choice == 'cookie':
                logging.error("Cookie 可能已失效。建议先执行: python playwright_cookie_manager.py --refresh")
            return None
        logging.info("认证测试成功.")
    except requests.exceptions.RequestException as e:
        logging.error(f"认证测试请求失败: {e}")
        return None
    return session_obj

def get_epic_tests(session, epic_id):
    """根据Epic ID获取相关的Tests"""
    logging.info(f"获取Epic {epic_id} 的Tests...")
    
    # 构建查询，根据需求文档中的接口格式
    query = f'"((phase={{id IN \'2y5g0779ygk9yigrv3gj907vp\',\'phase.test_suite.ready\',\'phase.model_based_test.ready\',\'phase.gherkin_test.ready\'}};subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\');((covered_content={{(path=\'{epic_id}*\')}})))"'
    
    tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_EPIC_TESTS, query, order_by="id")
    if not tests_data:
        fallback_query = f'"(subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\';(covered_content={{(path=\'{epic_id}*\')}}))"'
        logging.info("主查询返回 0 条，使用无 phase 限制的回退查询重试 Epic Tests...")
        tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_EPIC_TESTS, fallback_query, order_by="id")
    return tests_data

def get_test_executions(session, test_id, team="DTSV_China"):
    """根据Test ID获取相关的Test Executions (Runs)"""
    logging.info(f"获取Test {test_id} 的Test Executions...")
    
    # 构建查询，根据需求文档中的接口格式
    query = f'"(((run_team_000_udf={{id=59139}});(subtype=\'run_manual\');subtype IN \'run_manual\',\'run_automated\');((test={{(covered_manual_test={{id={test_id}}})}}))||(test={{id={test_id}}})))"'
    
    runs_data = fetch_octane_data(session, EP_RUNS, FIELDS_TEST_RUNS, query, order_by="id")
    return runs_data

def get_dtsv_runs(session, team_name="DTSV_China", release_name=None, page_limit=DEFAULT_DTSV_PAGE_LIMIT, workers=DEFAULT_DTSV_WORKERS):
    """拉取 DTSV 全量 runs（manual + automated），用于构建全量 testcase 关系。"""
    logging.info(f"获取团队 {team_name} 的全量 Test Executions...")
    if release_name:
        query = f'"(subtype IN \'run_manual\',\'run_automated\';run_team_000_udf={{name=\'{team_name}\'}};release={{name=\'{release_name}\'}})"'
    else:
        query = f'"(subtype IN \'run_manual\',\'run_automated\';run_team_000_udf={{name=\'{team_name}\'}})"'
    runs_data = fetch_octane_data_parallel(
        session,
        EP_RUNS,
        FIELDS_TEST_RUNS,
        query,
        limit_per_page=page_limit,
        order_by="id",
        max_workers=workers,
    )
    return runs_data

def _ensure_list(value):
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]

def _extract_id_name(item):
    if isinstance(item, dict):
        return item.get("id"), item.get("name")
    return item, None

def _normalize_id(value):
    if value is None:
        return None
    value_str = str(value).strip()
    return value_str if value_str else None

def _add_id(set_obj, value):
    norm = _normalize_id(value)
    if norm is not None:
        set_obj.add(norm)
        return norm
    return None

def _collect_covered_entities(test_ref, target_entry):
    covered_contents = _ensure_list(test_ref.get("covered_content"))
    for cc in covered_contents:
        cc_id, cc_name = _extract_id_name(cc)
        cc_id_str = _normalize_id(cc_id)
        if cc_id_str is None:
            continue

        cc_subtype = cc.get("subtype") if isinstance(cc, dict) else None
        cc_item = {
            "id": cc_id_str,
            "name": cc_name,
            "subtype": cc_subtype,
            "path": cc.get("path") if isinstance(cc, dict) else None,
        }

        if cc_subtype == "feature":
            target_entry["feature_ids"].add(cc_id_str)
            target_entry["feature_links"][cc_id_str] = cc_item
            target_entry["feature_parent_testevent"][cc_id_str] = {
                "id": cc_id_str,
                "name": cc_name,
                "subtype": "feature",
            }
        elif cc_subtype == "story":
            target_entry["story_ids"].add(cc_id_str)
            target_entry["story_links"][cc_id_str] = cc_item

            parent = cc.get("parent") if isinstance(cc, dict) and isinstance(cc.get("parent"), dict) else None
            if parent:
                pid, pname = _extract_id_name(parent)
                pid_str = _normalize_id(pid)
                if pid_str is not None:
                    target_entry["feature_parent_testevent"][pid_str] = {
                        "id": pid_str,
                        "name": pname,
                        "subtype": parent.get("subtype"),
                    }

def _chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]

def get_tests_by_ids(session, test_ids, chunk_size=150):
    """按 test_id 批量回填 tests 关联信息，用于补全 feature/story 关系。"""
    valid_ids = [_normalize_id(tid) for tid in test_ids]
    valid_ids = [tid for tid in valid_ids if tid is not None]
    if not valid_ids:
        return {}

    result = {}
    for id_chunk in _chunked(valid_ids, max(1, chunk_size)):
        id_expr = ",".join(f"'{tid}'" for tid in id_chunk)
        query = f'"(id IN {id_expr})"'
        tests_data = fetch_octane_data(
            session,
            EP_TESTS,
            FIELDS_TESTS_ENRICH,
            query,
            limit_per_page=max(len(id_chunk), DEFAULT_LIMIT_PER_PAGE),
            order_by="id",
        )
        for t in tests_data:
            tid = _normalize_id(t.get("id"))
            if tid is not None:
                result[tid] = t
    return result

def enrich_dtsv_dataset_with_tests(session, dataset, chunk_size=150):
    """对 feature/story 缺失的 testcase 进行 tests 二段式补全。"""
    testcases = dataset.get("testcases", [])
    unresolved_ids = []
    for tc in testcases:
        if not tc.get("feature_ids") or not tc.get("story_ids"):
            tid = _normalize_id(tc.get("test_id"))
            if tid is not None:
                unresolved_ids.append(tid)

    unresolved_ids = sorted(set(unresolved_ids))
    if not unresolved_ids:
        return {
            "unresolved_testcases": 0,
            "tests_lookup_count": 0,
            "enriched_testcases": 0,
        }

    tests_by_id = get_tests_by_ids(session, unresolved_ids, chunk_size=chunk_size)
    enriched_count = 0

    for tc in testcases:
        tid = _normalize_id(tc.get("test_id"))
        if tid is None:
            continue
        test_ref = tests_by_id.get(tid)
        if not isinstance(test_ref, dict):
            continue

        feature_ids_before = len(tc.get("feature_ids", []))
        story_ids_before = len(tc.get("story_ids", []))

        feature_links_map = {str(it.get("id")): it for it in tc.get("feature_links", []) if _normalize_id(it.get("id"))}
        story_links_map = {str(it.get("id")): it for it in tc.get("story_links", []) if _normalize_id(it.get("id"))}
        feature_parent_map = {str(it.get("id")): it for it in tc.get("feature_parent_testevent", []) if _normalize_id(it.get("id"))}

        merge_target = {
            "feature_ids": set(tc.get("feature_ids", [])),
            "feature_links": feature_links_map,
            "story_ids": set(tc.get("story_ids", [])),
            "story_links": story_links_map,
            "feature_parent_testevent": feature_parent_map,
        }
        _collect_covered_entities(test_ref, merge_target)

        tc["feature_ids"] = sorted(merge_target["feature_ids"])
        tc["feature_links"] = sorted(merge_target["feature_links"].values(), key=lambda x: str(x.get("id")))
        tc["story_ids"] = sorted(merge_target["story_ids"])
        tc["story_links"] = sorted(merge_target["story_links"].values(), key=lambda x: str(x.get("id")))
        tc["feature_parent_testevent"] = sorted(merge_target["feature_parent_testevent"].values(), key=lambda x: str(x.get("id")))

        if len(tc["feature_ids"]) > feature_ids_before or len(tc["story_ids"]) > story_ids_before:
            enriched_count += 1

    return {
        "unresolved_testcases": len(unresolved_ids),
        "tests_lookup_count": len(tests_by_id),
        "enriched_testcases": enriched_count,
    }

def build_dtsv_audit(dataset, pre_stats, post_stats, enrich_stats):
    testcases = dataset.get("testcases", [])
    total = len(testcases)

    defect_non_empty = sum(1 for tc in testcases if tc.get("defect_ids"))
    feature_non_empty = sum(1 for tc in testcases if tc.get("feature_ids"))
    story_non_empty = sum(1 for tc in testcases if tc.get("story_ids"))

    return {
        "generated_at": datetime.now().isoformat(),
        "scope": dataset.get("scope", {}),
        "totals": {
            "testcases": total,
            "runs": dataset.get("total_runs", 0),
        },
        "coverage_before_enrichment": pre_stats,
        "coverage_after_enrichment": post_stats,
        "enrichment": enrich_stats,
        "non_empty_rates": {
            "defect": round((defect_non_empty / total * 100), 2) if total else 0,
            "feature": round((feature_non_empty / total * 100), 2) if total else 0,
            "story": round((story_non_empty / total * 100), 2) if total else 0,
        },
    }

def _work_items_query_by_run_id(run_id):
    run_id_norm = _normalize_id(run_id)
    if run_id_norm is None:
        return None
    return f'"(subtype IN \'defect\',\'feature\',\'story\';run_covered_content_relation={{id=\'{run_id_norm}\'}})"'

def _fetch_work_items_for_run(session, run_id):
    query = _work_items_query_by_run_id(run_id)
    if not query:
        return run_id, []
    data = fetch_octane_data(
        session,
        EP_WORK_ITEMS,
        FIELDS_WORKITEMS_BY_RUN,
        query,
        limit_per_page=200,
        order_by="id",
    )
    return run_id, data

def enrich_dtsv_dataset_with_work_items(
    session,
    dataset,
    max_testcases=1000,
    workers=8,
):
    """对仍缺失 feature/story 的 testcase 使用 work_items(run 关系)兜底补全。"""
    testcases = dataset.get("testcases", [])
    unresolved = []
    for tc in testcases:
        if tc.get("feature_ids") and tc.get("story_ids"):
            continue
        run_ids = tc.get("run_ids", [])
        if not run_ids:
            continue
        # 使用代表性 run id 兜底，减少请求量
        representative_run = run_ids[-1]
        unresolved.append((tc, representative_run))

    total_unresolved = len(unresolved)
    if max_testcases > 0:
        unresolved = unresolved[:max_testcases]

    if not unresolved:
        return {
            "candidate_testcases": total_unresolved,
            "processed_testcases": 0,
            "work_items_queries": 0,
            "enriched_testcases": 0,
        }

    enriched = 0
    processed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(_fetch_work_items_for_run, session, run_id): tc
            for tc, run_id in unresolved
        }

        for future in concurrent.futures.as_completed(future_map):
            tc = future_map[future]
            processed += 1
            try:
                _, items = future.result()
            except Exception as e:
                logging.warning(f"work_items fallback 查询失败: {e}")
                continue

            if not items:
                continue

            feature_before = len(tc.get("feature_ids", []))
            story_before = len(tc.get("story_ids", []))

            feature_links_map = {str(it.get("id")): it for it in tc.get("feature_links", []) if _normalize_id(it.get("id"))}
            story_links_map = {str(it.get("id")): it for it in tc.get("story_links", []) if _normalize_id(it.get("id"))}
            defect_links_map = {str(it.get("id")): it for it in tc.get("defect_links", []) if _normalize_id(it.get("id"))}
            feature_parent_map = {str(it.get("id")): it for it in tc.get("feature_parent_testevent", []) if _normalize_id(it.get("id"))}
            feature_ids_set = set(tc.get("feature_ids", []))
            story_ids_set = set(tc.get("story_ids", []))
            defect_ids_set = set(tc.get("defect_ids", []))

            for wi in items:
                wi_id = _normalize_id(wi.get("id"))
                if wi_id is None:
                    continue
                wi_name = wi.get("name")
                wi_subtype = wi.get("subtype")

                if wi_subtype == "feature":
                    feature_ids_set.add(wi_id)
                    feature_links_map[wi_id] = {
                        "id": wi_id,
                        "name": wi_name,
                        "subtype": "feature",
                        "path": None,
                    }
                    feature_parent_map[wi_id] = {
                        "id": wi_id,
                        "name": wi_name,
                        "subtype": "feature",
                    }
                elif wi_subtype == "story":
                    story_ids_set.add(wi_id)
                    story_links_map[wi_id] = {
                        "id": wi_id,
                        "name": wi_name,
                        "subtype": "story",
                        "path": None,
                    }
                    parent = wi.get("parent") if isinstance(wi.get("parent"), dict) else None
                    if parent:
                        pid = _normalize_id(parent.get("id"))
                        if pid is not None:
                            feature_parent_map[pid] = {
                                "id": pid,
                                "name": parent.get("name"),
                                "subtype": parent.get("subtype"),
                            }
                elif wi_subtype == "defect":
                    defect_ids_set.add(wi_id)
                    defect_links_map[wi_id] = {
                        "id": wi_id,
                        "name": wi_name,
                        "subtype": "defect",
                    }

            tc["feature_ids"] = sorted(feature_ids_set)
            tc["feature_links"] = sorted(feature_links_map.values(), key=lambda x: str(x.get("id")))
            tc["story_ids"] = sorted(story_ids_set)
            tc["story_links"] = sorted(story_links_map.values(), key=lambda x: str(x.get("id")))
            tc["defect_ids"] = sorted(defect_ids_set)
            tc["defect_links"] = sorted(defect_links_map.values(), key=lambda x: str(x.get("id")))
            tc["feature_parent_testevent"] = sorted(feature_parent_map.values(), key=lambda x: str(x.get("id")))

            if len(tc["feature_ids"]) > feature_before or len(tc["story_ids"]) > story_before:
                enriched += 1

            if processed % 200 == 0:
                logging.info(f"work_items fallback 进度: {processed}/{len(unresolved)}")

    return {
        "candidate_testcases": total_unresolved,
        "processed_testcases": len(unresolved),
        "work_items_queries": len(unresolved),
        "enriched_testcases": enriched,
    }

def build_feature_summary(feature_id, tests_data, runs_data):
    """构建 feature 维度的标准化摘要，便于后续导出和二次分析。"""
    tests_summary = []
    run_summary = []
    defect_ids = set()
    manual_test_ids = set()
    story_ids = set()
    related_feature_ids = set()

    for test in tests_data:
        covered_manual = _ensure_list(test.get("covered_manual_test"))
        covered_content = _ensure_list(test.get("covered_content"))

        manual_links = []
        content_links = []

        for manual in covered_manual:
            mid, mname = _extract_id_name(manual)
            if mid is not None:
                manual_test_ids.add(str(mid))
                manual_links.append({"id": mid, "name": mname, "subtype": manual.get("subtype") if isinstance(manual, dict) else None})

        for content in covered_content:
            cid, cname = _extract_id_name(content)
            subtype = content.get("subtype") if isinstance(content, dict) else None
            content_links.append({"id": cid, "name": cname, "subtype": subtype, "path": content.get("path") if isinstance(content, dict) else None})
            if cid is not None and subtype == "story":
                story_ids.add(str(cid))
            if cid is not None and subtype == "feature":
                related_feature_ids.add(str(cid))

        tests_summary.append({
            "feature_id": str(feature_id),
            "test_id": test.get("id"),
            "test_name": test.get("name"),
            "test_subtype": test.get("subtype"),
            "test_phase": test.get("phase", {}).get("name") if isinstance(test.get("phase"), dict) else None,
            "covered_manual_test_links": manual_links,
            "covered_content_links": content_links
        })

    for run in runs_data:
        run_id = run.get("id")
        test_ref = run.get("test") if isinstance(run.get("test"), dict) else {}
        linked_defects = _ensure_list(run.get("linked_defects"))
        defect_ref = run.get("defect")

        defect_link_ids = []
        for linked in linked_defects:
            did, _ = _extract_id_name(linked)
            if did is not None:
                defect_ids.add(str(did))
                defect_link_ids.append(did)

        did_single, _ = _extract_id_name(defect_ref)
        if did_single is not None:
            defect_ids.add(str(did_single))
            defect_link_ids.append(did_single)

        covered_manual = _ensure_list(test_ref.get("covered_manual_test"))
        for manual in covered_manual:
            mid, _ = _extract_id_name(manual)
            if mid is not None:
                manual_test_ids.add(str(mid))

        covered_content = _ensure_list(test_ref.get("covered_content"))
        for content in covered_content:
            cid, _ = _extract_id_name(content)
            subtype = content.get("subtype") if isinstance(content, dict) else None
            if cid is not None and subtype == "story":
                story_ids.add(str(cid))
            if cid is not None and subtype == "feature":
                related_feature_ids.add(str(cid))

        run_summary.append({
            "feature_id": str(feature_id),
            "run_id": run_id,
            "test_id": test_ref.get("id"),
            "test_name": test_ref.get("name") or run.get("test_name"),
            "status": run.get("status", {}).get("name") if isinstance(run.get("status"), dict) else run.get("status"),
            "native_status": run.get("native_status", {}).get("name") if isinstance(run.get("native_status"), dict) else run.get("native_status"),
            "linked_defect_ids": sorted(set(str(d) for d in defect_link_ids if d is not None))
        })

    related_feature_ids.add(str(feature_id))
    summary = {
        "feature_id": str(feature_id),
        "tests_count": len(tests_data),
        "runs_count": len(runs_data),
        "linked_defect_ids": sorted(defect_ids),
        "manual_test_ids": sorted(manual_test_ids),
        "related_feature_ids": sorted(related_feature_ids),
        "related_story_ids": sorted(story_ids),
        "tests": tests_summary,
        "runs": run_summary,
    }
    return summary

def build_dtsv_testcase_dataset(runs_data, team_name="DTSV_China", release_name=None):
    """从 runs 构建 testcase 维度数据，包含 defect/feature/us 关联。"""
    by_testcase = {}
    runs_without_test = 0

    for run in runs_data:
        test_ref = run.get("test") if isinstance(run.get("test"), dict) else {}
        test_id = test_ref.get("id")
        if test_id is None:
            runs_without_test += 1
            continue

        key = str(test_id)
        if key not in by_testcase:
            by_testcase[key] = {
                "test_id": test_id,
                "test_name": test_ref.get("name") or run.get("test_name"),
                "test_subtype": test_ref.get("subtype"),
                "manual_test_ids": set(),
                "manual_test_links": {},
                "defect_ids": set(),
                "defect_links": {},
                "feature_ids": set(),
                "feature_links": {},
                "feature_parent_testevent": {},
                "story_ids": set(),
                "story_links": {},
                "run_ids": set(),
                "run_statuses": {},
            }

        entry = by_testcase[key]
        run_id = run.get("id")
        if run_id is not None:
            entry["run_ids"].add(run_id)
            status_name = run.get("status", {}).get("name") if isinstance(run.get("status"), dict) else run.get("status")
            native_status_name = run.get("native_status", {}).get("name") if isinstance(run.get("native_status"), dict) else run.get("native_status")
            status_key = native_status_name or status_name or "Unknown"
            entry["run_statuses"][status_key] = entry["run_statuses"].get(status_key, 0) + 1

        defect_ref = run.get("defect")
        linked_defects = _ensure_list(run.get("linked_defects"))
        for defect_obj in [defect_ref] + linked_defects:
            did, dname = _extract_id_name(defect_obj)
            did_norm = _add_id(entry["defect_ids"], did)
            if did_norm is not None:
                entry["defect_links"][did_norm] = {
                    "id": did_norm,
                    "name": dname,
                    "subtype": "defect",
                }

        covered_manual_tests = _ensure_list(test_ref.get("covered_manual_test"))
        for mt in covered_manual_tests:
            mt_id, mt_name = _extract_id_name(mt)
            if mt_id is not None:
                mt_id_str = str(mt_id)
                entry["manual_test_ids"].add(mt_id_str)
                entry["manual_test_links"][mt_id_str] = {
                    "id": mt_id,
                    "name": mt_name,
                    "subtype": mt.get("subtype") if isinstance(mt, dict) else None,
                }

        covered_contents = _ensure_list(test_ref.get("covered_content"))
        if covered_contents:
            _collect_covered_entities(test_ref, entry)

    testcases = []
    for _, entry in by_testcase.items():
        testcases.append({
            "test_id": entry["test_id"],
            "test_name": entry["test_name"],
            "test_subtype": entry["test_subtype"],
            "run_count": len(entry["run_ids"]),
            "run_ids": sorted(entry["run_ids"], key=lambda x: str(x)),
            "run_status_distribution": entry["run_statuses"],
            "defect_ids": sorted(entry["defect_ids"]),
            "defect_links": sorted(entry["defect_links"].values(), key=lambda x: str(x.get("id"))),
            "manual_test_ids": sorted(entry["manual_test_ids"]),
            "manual_test_links": sorted(entry["manual_test_links"].values(), key=lambda x: str(x.get("id"))),
            "feature_ids": sorted(entry["feature_ids"]),
            "feature_links": sorted(entry["feature_links"].values(), key=lambda x: str(x.get("id"))),
            "feature_parent_testevent": sorted(entry["feature_parent_testevent"].values(), key=lambda x: str(x.get("id"))),
            "story_ids": sorted(entry["story_ids"]),
            "story_links": sorted(entry["story_links"].values(), key=lambda x: str(x.get("id"))),
        })

    testcases.sort(key=lambda x: str(x.get("test_id")))
    return {
        "generated_at": datetime.now().isoformat(),
        "scope": {
            "team": team_name,
            "release": release_name,
            "source": "runs",
        },
        "total_runs": len(runs_data),
        "runs_without_test_id": runs_without_test,
        "total_testcases": len(testcases),
        "testcases": testcases,
    }

def process_feature(session_active, feature_id, output_dir, save_csv, save_excel, full_details):
    """按 feature 拉取 testcase，并保存单一文件。"""
    target_dir = os.path.join(output_dir, f"feature_{feature_id}")
    os.makedirs(target_dir, exist_ok=True)

    logging.info(f"=== 获取 Feature {feature_id} 的 Tests ===")
    feature_tests = get_feature_tests(session_active, feature_id)

    all_executions = []
    if full_details:
        logging.info(f"=== 获取 Feature {feature_id} 的 Test Executions ===")
        all_test_ids = sorted({test.get("id") for test in feature_tests if test.get("id") is not None})
        for test_id in all_test_ids:
            all_executions.extend(get_test_executions(session_active, test_id))

    normalized = build_feature_summary(feature_id, feature_tests, all_executions)
    save_data(normalized, f"feature_{feature_id}_testcases", target_dir, False, False)

def process_dtsv_all(
    session_active,
    output_dir,
    team_name="DTSV_China",
    release_name=None,
    page_limit=DEFAULT_DTSV_PAGE_LIMIT,
    workers=DEFAULT_DTSV_WORKERS,
    workitems_fallback_max=1000,
    workitems_fallback_workers=8,
    save_db=False,
    db_path=None,
):
    """拉取 DTSV 全量 testcase，并仅保存一个 JSON 文件。"""
    os.makedirs(output_dir, exist_ok=True)
    runs_data = get_dtsv_runs(
        session_active,
        team_name=team_name,
        release_name=release_name,
        page_limit=page_limit,
        workers=workers,
    )
    dataset = build_dtsv_testcase_dataset(runs_data, team_name=team_name, release_name=release_name)

    pre_stats = {
        "defect_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("defect_ids")),
        "feature_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("feature_ids")),
        "story_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("story_ids")),
    }

    enrich_stats = enrich_dtsv_dataset_with_tests(session_active, dataset, chunk_size=150)
    fallback_stats = enrich_dtsv_dataset_with_work_items(
        session_active,
        dataset,
        max_testcases=workitems_fallback_max,
        workers=workitems_fallback_workers,
    )
    enrich_stats["work_items_fallback"] = fallback_stats

    post_stats = {
        "defect_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("defect_ids")),
        "feature_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("feature_ids")),
        "story_non_empty": sum(1 for tc in dataset.get("testcases", []) if tc.get("story_ids")),
    }

    audit = build_dtsv_audit(dataset, pre_stats, post_stats, enrich_stats)

    if release_name:
        safe_release = release_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        filename_prefix = f"dtsv_testcases_{safe_release}"
    else:
        filename_prefix = "dtsv_testcases_all"
    save_data(dataset, filename_prefix, output_dir, False, False)
    save_data(audit, f"{filename_prefix}.audit", output_dir, False, False)

    db_result = None
    if save_db:
        _, db_result = save_dtsv_dataset_to_db(dataset, db_path=db_path)

    return {
        "dataset": dataset,
        "audit": audit,
        "db_result": db_result,
        "filename_prefix": filename_prefix,
    }

def get_epic_features(session, epic_id):
    """根据Epic ID获取相关的Features"""
    logging.info(f"获取Epic {epic_id} 的Features...")
    
    # 构建查询，根据需求文档中的接口格式
    query = f'"(parent={{id={epic_id}}};(subtype=\'feature\'))"'
    
    features_data = fetch_octane_data(session, EP_WORK_ITEMS, FIELDS_EPIC_FEATURES, query, order_by="id")
    return features_data

def get_feature_tests(session, feature_id):
    """根据Feature ID获取相关的Tests"""
    logging.info(f"获取Feature {feature_id} 的Tests...")
    
    # 构建查询，根据需求文档中的接口格式
    query = f'"((phase={{id IN \'2y5g0779ygk9yigrv3gj907vp\',\'phase.test_suite.ready\',\'phase.model_based_test.ready\',\'phase.gherkin_test.ready\'}};subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\');((covered_content={{(path=\'{feature_id}*\')}})))"'
    
    tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_FEATURE_TESTS, query, order_by="id")
    if not tests_data:
        fallback_query = f'"(subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\';(covered_content={{(path=\'{feature_id}*\')}}))"'
        logging.info("主查询返回 0 条，使用无 phase 限制的回退查询重试 Feature Tests...")
        tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_FEATURE_TESTS, fallback_query, order_by="id")
    if not tests_data:
        fallback_query_by_id = f'"(subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\';covered_content={{id={feature_id}}})"'
        logging.info("path 回退查询仍为 0 条，使用 covered_content.id 回退查询重试 Feature Tests...")
        tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_FEATURE_TESTS, fallback_query_by_id, order_by="id")
    return tests_data

def analyze_coverage(epic_data, features_data, tests_data, runs_data):
    """分析覆盖率情况"""
    logging.info("开始分析覆盖率...")
    
    coverage_analysis = {
        "epic_summary": {
            "epic_id": epic_data.get("id") if epic_data else "Unknown",
            "epic_name": epic_data.get("name") if epic_data else "Unknown",
            "total_features": len(features_data),
            "total_tests": len(tests_data),
            "total_test_executions": len(runs_data)
        },
        "feature_coverage": [],
        "test_coverage": [],
        "execution_summary": {}
    }
    
    # 创建test到runs的映射
    test_to_runs = {}
    for run in runs_data:
        test_ref = run.get("test", {})
        if isinstance(test_ref, dict):
            test_id = test_ref.get("id")
        else:
            test_id = test_ref
        
        if test_id:
            if test_id not in test_to_runs:
                test_to_runs[test_id] = []
            test_to_runs[test_id].append(run)
    
    # 分析每个test的覆盖率
    for test in tests_data:
        test_id = test.get("id")
        test_runs = test_to_runs.get(test_id, [])
        
        coverage_analysis["test_coverage"].append({
            "test_id": test_id,
            "test_name": test.get("name"),
            "test_type": test.get("subtype"),
            "phase": test.get("phase", {}).get("name") if test.get("phase") else None,
            "is_covered": len(test_runs) > 0,
            "execution_count": len(test_runs),
            "executions": test_runs
        })
    
    # 分析每个feature的覆盖率
    for feature in features_data:
        feature_id = feature.get("id")
        # 获取feature相关的tests
        feature_tests = [t for t in tests_data if str(feature_id) in str(t.get("covered_content", []))]
        
        feature_test_ids = [t.get("id") for t in feature_tests]
        feature_executions = []
        for test_id in feature_test_ids:
            feature_executions.extend(test_to_runs.get(test_id, []))
        
        # 检查是否所有tests都有executions
        all_tests_covered = all(test_id in test_to_runs for test_id in feature_test_ids) if feature_test_ids else False
        
        coverage_analysis["feature_coverage"].append({
            "feature_id": feature_id,
            "feature_name": feature.get("name"),
            "feature_phase": feature.get("phase", {}).get("name") if feature.get("phase") else None,
            "total_tests": len(feature_tests),
            "covered_tests": sum(1 for test_id in feature_test_ids if test_id in test_to_runs),
            "is_fully_covered": all_tests_covered,
            "coverage_percentage": (sum(1 for test_id in feature_test_ids if test_id in test_to_runs) / len(feature_test_ids) * 100) if feature_test_ids else 0,
            "execution_count": len(feature_executions)
        })
    
    # 执行状态汇总
    execution_statuses = {}
    for run in runs_data:
        status = run.get("native_status", {}).get("name") if run.get("native_status") else "Unknown"
        execution_statuses[status] = execution_statuses.get(status, 0) + 1
    
    coverage_analysis["execution_summary"] = {
        "status_distribution": execution_statuses,
        "total_executions": len(runs_data),
        "unique_tests_executed": len(test_to_runs)
    }
    
    # 总体覆盖率统计
    total_tests = len(tests_data)
    covered_tests = sum(1 for test in tests_data if test.get("id") in test_to_runs)
    
    coverage_analysis["overall_coverage"] = {
        "test_coverage_percentage": (covered_tests / total_tests * 100) if total_tests > 0 else 0,
        "covered_tests": covered_tests,
        "total_tests": total_tests,
        "uncovered_tests": total_tests - covered_tests
    }
    
    logging.info("覆盖率分析完成.")
    return coverage_analysis

def main():
    parser = argparse.ArgumentParser(description="从 Octane API 下载测试用例相关数据并分析覆盖率")
    
    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument("--auth-method", choices=['sso', 'cookie'], help="认证方法.")
    auth_group.add_argument("--login-file", default="login_info.txt", help="SSO 用户名密码文件")
    auth_group.add_argument("--cookie-file", default="cookie.txt", help="Cookie 文件路径 (for --auth-method=cookie)")
    
    scope_group = parser.add_argument_group('Scope Options')
    scope_exclusive = scope_group.add_mutually_exclusive_group(required=True)
    scope_exclusive.add_argument("--epic-id", help="Epic ID")
    scope_exclusive.add_argument("--feature-id", help="Feature ID")
    scope_exclusive.add_argument("--dtsv-all", action='store_true', help="拉取 DTSV 全量 testcase")
    scope_group.add_argument("--team-name", default="DTSV_China", help="团队名称 (默认: DTSV_China)")
    scope_group.add_argument("--release-name", help="可选：按 release 过滤 DTSV 全量拉取")
    scope_group.add_argument("--page-limit", type=int, default=DEFAULT_DTSV_PAGE_LIMIT, help=f"DTSV 全量拉取分页大小 (默认: {DEFAULT_DTSV_PAGE_LIMIT})")
    scope_group.add_argument("--workers", type=int, default=DEFAULT_DTSV_WORKERS, help=f"DTSV 全量拉取并发线程数 (默认: {DEFAULT_DTSV_WORKERS})")
    scope_group.add_argument("--workitems-fallback-max", type=int, default=1000, help="work_items 兜底补全最多处理的 testcase 数 (0=全部，默认: 1000)")
    scope_group.add_argument("--workitems-fallback-workers", type=int, default=8, help="work_items 兜底补全并发线程数 (默认: 8)")
    scope_group.add_argument("--full-details", action='store_true', help="拉取 runs 等详情")
    scope_group.add_argument("--save-db", action='store_true', help="将 dtsv-all 的 testcase 关系同步写入 SQLite")
    scope_group.add_argument("--db-path", help="可选：SQLite 数据库路径，默认沿用本项目 local_data_rebuilt.db/local_data.db 规则")
    
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument("--output-dir", default="testcase", help="输出目录 (固定建议: testcase)")
    output_group.add_argument("--save-csv", action='store_true', help="同时保存为 CSV")
    output_group.add_argument("--save-excel", action='store_true', help="同时保存为 Excel")
    
    args = parser.parse_args()
    
    # 如果没有指定认证方法，提示用户选择
    auth_method_selected = args.auth_method
    if not auth_method_selected:
        while True:
            print("\n选择认证方法:\n1: SSO\n2: Cookie (优先读取 cookie.txt)")
            choice = input("选项 (1 or 2): ").strip()
            if choice == '1':
                auth_method_selected = 'sso'
                break
            elif choice == '2':
                auth_method_selected = 'cookie'
                break
            else:
                print("无效选择.")
        logging.info(f"选择认证方法: {auth_method_selected}")
    
    # 检查SSO文件是否存在
    if auth_method_selected == 'sso':
        if not SSO_AVAILABLE or not os.path.exists(args.login_file):
            logging.error(f"SSO 不可用或登录文件 '{args.login_file}' 未找到.")
            return
    
    # 获取认证会话
    session_active = get_authenticated_session(auth_method_selected, args.login_file, args.cookie_file)
    if not session_active:
        logging.critical("认证失败.")
        return
    
    if args.save_db and not args.dtsv_all:
        logging.warning("当前仅 --dtsv-all 支持 --save-db；feature/epic 模式仍为文件输出。")

    if args.save_db and not OCTANE_DB_AVAILABLE:
        logging.error("无法启用 --save-db：octane_db 模块不可用。")
        return

    # 创建输出目录
    output_dir = "testcase"
    if args.output_dir != "testcase":
        logging.warning(f"按你的要求，输出目录固定为 testcase，已忽略 --output-dir={args.output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    if args.dtsv_all:
        logging.info(f"开始处理 DTSV 全量 testcase，团队: {args.team_name}, release: {args.release_name or 'ALL'}")
        result = process_dtsv_all(
            session_active=session_active,
            output_dir=output_dir,
            team_name=args.team_name,
            release_name=args.release_name,
            page_limit=max(100, args.page_limit),
            workers=max(1, args.workers),
            workitems_fallback_max=max(0, args.workitems_fallback_max),
            workitems_fallback_workers=max(1, args.workitems_fallback_workers),
            save_db=args.save_db,
            db_path=args.db_path,
        )
        logging.info(f"DTSV 全量 testcase 文件已保存到目录: {output_dir}")
        if result.get("db_result"):
            logging.info(
                "DTSV 全量 testcase 已同步写库: testcases=%s, relations=%s",
                result["db_result"].get("testcases", 0),
                result["db_result"].get("relations", 0),
            )
        logging.info("处理完成！")
        return

    if args.feature_id:
        feature_id = args.feature_id
        logging.info(f"开始处理 Feature: {feature_id}")
        process_feature(
            session_active=session_active,
            feature_id=feature_id,
            output_dir=output_dir,
            save_csv=args.save_csv,
            save_excel=args.save_excel,
            full_details=args.full_details,
        )
        logging.info(f"Feature {feature_id} 数据已保存到目录: {os.path.join(output_dir, f'feature_{feature_id}')}")
        logging.info("处理完成！")
        return

    epic_id = args.epic_id
    logging.info(f"开始处理 Epic: {epic_id}")

    logging.info("=== 第1步: 获取Epic的Tests ===")
    epic_tests = get_epic_tests(session_active, epic_id)
    save_data(epic_tests, f"epic_{epic_id}_tests", output_dir, args.save_csv, args.save_excel)

    logging.info("=== 第2步: 获取Epic的Features ===")
    epic_features = get_epic_features(session_active, epic_id)
    save_data(epic_features, f"epic_{epic_id}_features", output_dir, args.save_csv, args.save_excel)

    logging.info("=== 第3步: 获取每个Feature的Tests ===")
    all_feature_tests = []
    for feature in epic_features:
        feature_id = feature.get("id")
        if feature_id:
            feature_tests = get_feature_tests(session_active, feature_id)
            all_feature_tests.extend(feature_tests)
    save_data(all_feature_tests, f"epic_{epic_id}_feature_tests", output_dir, args.save_csv, args.save_excel)

    all_executions = []
    if args.full_details:
        logging.info("=== 第4步: 获取Tests的Test Executions ===")
        all_test_ids = set()
        for test in epic_tests:
            if test.get("id"):
                all_test_ids.add(test.get("id"))
        for test in all_feature_tests:
            if test.get("id"):
                all_test_ids.add(test.get("id"))

        for test_id in all_test_ids:
            executions = get_test_executions(session_active, test_id)
            all_executions.extend(executions)

        save_data(all_executions, f"epic_{epic_id}_test_executions", output_dir, args.save_csv, args.save_excel)

    logging.info("=== 第5步: 进行覆盖率分析 ===")
    epic_info = {"id": epic_id, "name": f"Epic_{epic_id}"}

    all_tests = epic_tests + all_feature_tests
    unique_tests = {}
    for test in all_tests:
        test_id = test.get("id")
        if test_id:
            unique_tests[test_id] = test
    all_tests_unique = list(unique_tests.values())

    coverage_analysis = analyze_coverage(epic_info, epic_features, all_tests_unique, all_executions)
    save_data(coverage_analysis, f"epic_{epic_id}_coverage_analysis", output_dir, args.save_csv, args.save_excel)

    logging.info("=== 汇总信息 ===")
    logging.info(f"Epic ID: {epic_id}")
    logging.info(f"总Features数: {len(epic_features)}")
    logging.info(f"总Tests数: {len(all_tests_unique)}")
    logging.info(f"总Test Executions数: {len(all_executions)}")

    overall_coverage = coverage_analysis.get("overall_coverage", {})
    logging.info(f"测试覆盖率: {overall_coverage.get('test_coverage_percentage', 0):.2f}%")
    logging.info(f"已覆盖Tests: {overall_coverage.get('covered_tests', 0)}")
    logging.info(f"未覆盖Tests: {overall_coverage.get('uncovered_tests', 0)}")

    execution_summary = coverage_analysis.get("execution_summary", {})
    status_dist = execution_summary.get("status_distribution", {})
    logging.info("执行状态分布:")
    for status, count in status_dist.items():
        logging.info(f"  {status}: {count}")

    logging.info(f"所有数据已保存到目录: {output_dir}")
    logging.info("处理完成！")

if __name__ == "__main__":
    main() 