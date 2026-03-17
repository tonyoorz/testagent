import json
import time
import urllib.parse
import requests
import logging
import pandas as pd
from datetime import datetime, timedelta
import os
import argparse
import urllib3
import concurrent.futures
from tqdm import tqdm

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
    "runs_in_suite{subtype}", "test{subtype}", "parent_suite{subtype}", 
    "taxonomies{subtype}"
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

def get_authenticated_session(auth_method_choice, sso_login_file=None):
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
            cookie_val = DEFAULT_COOKIE
            if not cookie_val:
                logging.error("预定义 Cookie 为空!")
                return None
            session_obj.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                "cookie": cookie_val
            })
            logging.info("使用预定义 Cookie 认证.")
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
    query = f'"((phase={{id IN \'2y5g0779ygk9yigrv3gj907vp\',\'phase.test_suite.ready\',\'phase.model_based_test.ready\',\'phase.gherkin_test.ready\'}};subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\');((covered_content={{(path=\'{epic_id}*\')}}))"'
    
    tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_EPIC_TESTS, query, order_by="id")
    return tests_data

def get_test_executions(session, test_id, team="DTSV_China"):
    """根据Test ID获取相关的Test Executions (Runs)"""
    logging.info(f"获取Test {test_id} 的Test Executions...")
    
    # 构建查询，根据需求文档中的接口格式
    query = f'"(((run_team_000_udf={{id=59139}});(subtype=\'run_manual\');subtype IN \'run_manual\',\'run_automated\');((test={{(covered_manual_test={{id={test_id}}})}}))||(test={{id={test_id}}})))"'
    
    runs_data = fetch_octane_data(session, EP_RUNS, FIELDS_TEST_RUNS, query, order_by="id")
    return runs_data

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
    query = f'"((phase={{id IN \'2y5g0779ygk9yigrv3gj907vp\',\'phase.test_suite.ready\',\'phase.model_based_test.ready\',\'phase.gherkin_test.ready\'}};subtype IN \'test_suite\',\'model_based_test\',\'test_manual\',\'gherkin_test\');((covered_content={{(path=\'{feature_id}*\')}}))"'
    
    tests_data = fetch_octane_data(session, EP_TESTS, FIELDS_FEATURE_TESTS, query, order_by="id")
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
    
    epic_group = parser.add_argument_group('Epic Options')
    epic_group.add_argument("--epic-id", required=True, help="Epic ID (必需)")
    
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument("--output-dir", default="tests", help="输出目录 (默认: tests)")
    output_group.add_argument("--save-csv", action='store_true', help="同时保存为 CSV")
    output_group.add_argument("--save-excel", action='store_true', help="同时保存为 Excel")
    
    args = parser.parse_args()
    
    # 如果没有指定认证方法，提示用户选择
    auth_method_selected = args.auth_method
    if not auth_method_selected:
        while True:
            print("\n选择认证方法:\n1: SSO\n2: Cookie (预定义)")
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
    session_active = get_authenticated_session(auth_method_selected, args.login_file)
    if not session_active:
        logging.critical("认证失败.")
        return
    
    # 创建输出目录
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    
    epic_id = args.epic_id
    logging.info(f"开始处理Epic: {epic_id}")
    
    # 1. 获取Epic的Tests
    logging.info("=== 第1步: 获取Epic的Tests ===")
    epic_tests = get_epic_tests(session_active, epic_id)
    save_data(epic_tests, f"epic_{epic_id}_tests", output_dir, args.save_csv, args.save_excel)
    
    # 2. 获取Epic的Features
    logging.info("=== 第2步: 获取Epic的Features ===")
    epic_features = get_epic_features(session_active, epic_id)
    save_data(epic_features, f"epic_{epic_id}_features", output_dir, args.save_csv, args.save_excel)
    
    # 3. 获取每个Feature的Tests
    logging.info("=== 第3步: 获取每个Feature的Tests ===")
    all_feature_tests = []
    for feature in epic_features:
        feature_id = feature.get("id")
        if feature_id:
            feature_tests = get_feature_tests(session_active, feature_id)
            all_feature_tests.extend(feature_tests)
    
    save_data(all_feature_tests, f"epic_{epic_id}_feature_tests", output_dir, args.save_csv, args.save_excel)
    
    # 4. 获取所有Tests的Test Executions
    logging.info("=== 第4步: 获取Tests的Test Executions ===")
    all_test_ids = set()
    
    # 收集所有test IDs
    for test in epic_tests:
        if test.get("id"):
            all_test_ids.add(test.get("id"))
    
    for test in all_feature_tests:
        if test.get("id"):
            all_test_ids.add(test.get("id"))
    
    all_executions = []
    for test_id in all_test_ids:
        executions = get_test_executions(session_active, test_id)
        all_executions.extend(executions)
    
    save_data(all_executions, f"epic_{epic_id}_test_executions", output_dir, args.save_csv, args.save_excel)
    
    # 5. 进行覆盖率分析
    logging.info("=== 第5步: 进行覆盖率分析 ===")
    epic_info = {"id": epic_id, "name": f"Epic_{epic_id}"}  # 简化的epic信息
    
    # 合并所有tests
    all_tests = epic_tests + all_feature_tests
    # 去重
    unique_tests = {}
    for test in all_tests:
        test_id = test.get("id")
        if test_id:
            unique_tests[test_id] = test
    all_tests_unique = list(unique_tests.values())
    
    coverage_analysis = analyze_coverage(epic_info, epic_features, all_tests_unique, all_executions)
    save_data(coverage_analysis, f"epic_{epic_id}_coverage_analysis", output_dir, args.save_csv, args.save_excel)
    
    # 6. 输出汇总信息
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