import json
import urllib
import urllib3
import requests
import os
import pandas as pd 
import time
import concurrent.futures
from datetime import datetime, timedelta
from tqdm import tqdm

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# API配置
BASE_URL = "https://octane-prod.bmwgroup.net" # 实际中可能不需要，因为API_URL是完整的
API_URL = "https://octane-prod.bmwgroup.net/api/shared_spaces/1002/workspaces/2001"
EP_DEFECT = "defects"
EP_HISTORY = "history_logs"

# 只需要id来获取历史
F_DEFECT = ("id",) # 只请求id，因为这是 get_all_defect_ids 唯一实际使用的字段

def load_cookie_from_file(cookie_file_path="cookie.txt"):
    """从文件中读取cookie"""
    try:
        print(f"尝试从 '{cookie_file_path}' 文件读取 Cookie...")
        if not os.path.exists(cookie_file_path):
            print(f"Cookie 文件 '{cookie_file_path}' 未找到。")
            return None
        
        with open(cookie_file_path, "r", encoding="utf-8") as f:
            cookie_val = f.read().strip()
        
        if not cookie_val:
            print(f"Cookie 文件 '{cookie_file_path}' 为空。")
            return None
        
        print(f"成功从 '{cookie_file_path}' 文件读取 Cookie")
        return cookie_val
        
    except IOError as e:
        print(f"读取 Cookie 文件 '{cookie_file_path}' 时出错: {e}")
        return None
    except Exception as e:
        print(f"处理 Cookie 文件时出错: {e}")
        return None

def create_session_with_cookie(cookie_value):
    """使用cookie创建会话"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "cookie": cookie_value
    })
    return session

def get_all_defect_ids(session, headers, team="DTSV_China", start_date=None, end_date=None, filter_field="creation_time"):
    """获取符合条件的所有defect ID
    
    Args:
        session: 请求会话
        headers: 请求头
        team: 团队名称
        start_date: 开始日期，格式为'YYYY-MM-DD'
        end_date: 结束日期，格式为'YYYY-MM-DD'
        filter_field: 筛选字段，'creation_time'或'last_modified'
        
    Returns:
        list: defect_ids
    """
    all_defect_ids = []
    offset = 0
    limit = 1000 # API 每页最大数量
    
    start_date_formatted = f"{start_date}T00:00:00Z" if start_date else "2000-01-01T00:00:00Z"
    end_date_formatted = f"{end_date}T23:59:59Z" if end_date else "2099-12-31T23:59:59Z"
    
    field_description = "创建" if filter_field == "creation_time" else "修改"
    print(f"正在获取{team or '所有团队'}在{start_date or '不限'}至{end_date or '不限'}期间{field_description}的defect ID列表...")
    
    while True:
        query_parts = []
        if team:
            query_parts.append(f"problem_finder_team_udf={{name=\'{team}\'}}")
        # 只有当提供了日期时才添加到查询中
        if start_date and filter_field == "creation_time": # 确保只在按创建时间筛选时应用开始日期
             query_parts.append(f"{filter_field}>=\'{start_date_formatted}\'")
        if end_date and filter_field == "creation_time": # 确保只在按创建时间筛选时应用结束日期
            query_parts.append(f"{filter_field}<=\'{end_date_formatted}\'")
        # 如果是按last_modified筛选，也应用日期范围
        if start_date and filter_field == "last_modified":
             query_parts.append(f"{filter_field}>=\'{start_date_formatted}\'")
        if end_date and filter_field == "last_modified":
            query_parts.append(f"{filter_field}<=\'{end_date_formatted}\'")

        if not query_parts:
            # 如果API不允许完全空的查询，可能需要一个通用查询，例如基于ID存在
            # query = '"(id>0)"' # 示例，具体看API要求
            # 或者，如果team是必须的，而其他是可选的:
            if not team: # 如果连team都没有，可能API不允许，或者需要一个非常通用的查询
                 print("警告: 未指定团队且未指定日期范围，可能导致查询非常广泛或失败。")
                 # 根据API行为，此处可能需要中止或设置一个默认查询
            query = '""' # 假设API支持空字符串查询以获取所有（或基于其他隐式上下文）
        else:
            query_string = ";".join(query_parts)
            query = f'"({query_string})"'
        
        request_params = {
            "fields": ",".join(F_DEFECT), # 使用F_DEFECT常量
            "query": query,
            "limit": limit,
            "offset": offset
        }
        
        request_params_encoded = urllib.parse.urlencode(request_params)
        request_url = f"{API_URL}/{EP_DEFECT}?{request_params_encoded}"
        
        try:
            resp = session.get(request_url, verify=False, headers=headers)
            if resp.status_code >= 400:
                print(f"获取defect ID时错误: {resp.status_code} - {resp.content.decode(errors='ignore')}")
                print(f"请求URL: {request_url}")
                print(f"请求参数: {request_params}")
                break
                
            data = resp.json()
            batch_defects = data.get("data", [])
            
            batch_defect_ids = [item["id"] for item in batch_defects]
            all_defect_ids.extend(batch_defect_ids)
            
            print(f"本批次获取到 {len(batch_defects)} 个defect ID")
            
            if not batch_defects or len(batch_defects) < limit:
                break
                
            offset += limit
            print(f"目前总共获取到 {len(all_defect_ids)} 个defect ID")
            
            time.sleep(0.3) # 礼貌性停顿
            
        except Exception as e:
            print(f"获取defect ID时发生异常: {e}")
            break
        
    return all_defect_ids

def get_defect_history(defect_id, session, headers):
    """获取单个defect的历史记录的原始内容"""
    S_QUERY = f'"(entity_id=\'{defect_id}\';entity_type=\'defect\')"'
    
    request_params = {
        "query": S_QUERY,
        "limit": 10000, 
        "offset": 0,
        "order_by": "-timestamp"
    }
    
    request_params_encoded = urllib.parse.urlencode(request_params)
    request_url = f"{API_URL}/{EP_HISTORY}?{request_params_encoded}"
    
    try:
        resp = session.get(request_url, verify=False, headers=headers, allow_redirects=True)
        
        if not 200 <= resp.status_code < 400:
            tqdm.write(f"获取 defect {defect_id} 历史时出错: {resp.status_code} - {resp.text}")
            return None
        
        return resp.json()
    
    except Exception as e:
        tqdm.write(f"获取 defect {defect_id} 历史时发生异常: {e}")
        return None

def get_histories_parallel(defect_ids, session, headers, max_workers=10):
    """并行获取多个defect的原始历史记录，并保存每个历史记录到单独的JSON文件"""
    processed_ids = []
    error_ids = []
    
    with tqdm(total=len(defect_ids), desc="获取并保存历史记录") as pbar:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {
                executor.submit(get_defect_history, defect_id, session, headers): defect_id 
                for defect_id in defect_ids
            }
            
            for future in concurrent.futures.as_completed(future_to_id):
                defect_id = future_to_id[future]
                try:
                    history_data = future.result() 
                    
                    if history_data and history_data.get("data"): 
                        history_filename = f"./history/{defect_id}_history.json"
                        with open(history_filename, "w", encoding="utf-8") as f:
                            json.dump(history_data, f, ensure_ascii=False, indent=2)
                        processed_ids.append(defect_id)
                    elif history_data is None: # Error should have been printed by get_defect_history
                        error_ids.append(defect_id)
                    else: # History data received but malformed or "data" is empty/missing
                        tqdm.write(f"Defect {defect_id} 历史数据为空或格式不正确 (例如: 'data' 键不存在或其值为空).")
                        error_ids.append(defect_id)
                
                except Exception as e: # Catching exceptions from future.result() or file writing
                    tqdm.write(f"处理 defect {defect_id} 历史时发生顶层错误: {e}")
                    error_ids.append(defect_id)
                
                finally:
                    pbar.update(1)
    
    return processed_ids, error_ids

def main():
    # --- 预设配置 ---
    # 1. 从cookie.txt文件读取Cookie
    cookie_value = load_cookie_from_file("cookie.txt")
    if not cookie_value:
        print("无法读取Cookie，程序退出。")
        return
    
    print("成功从cookie.txt文件读取Cookie")

    # 2. 默认筛选方式
    filter_field = "creation_time"
    field_description = "创建" # 用于打印信息

    # 3. 默认时间范围
    start_date = "2025-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d") # 当天

    # 4. 默认团队
    team = "DTSV_China"

    # 5. 默认线程数
    max_workers = 30 # 可以根据需要调整这个默认值
    # --- 预设配置结束 ---

    print("脚本将使用以下预设配置执行：")
    print(f"  Cookie: [已提供，已隐藏部分内容]")
    print(f"  团队: {team}")
    print(f"  筛选字段: {filter_field} ({field_description}时间)")
    print(f"  开始日期: {start_date}")
    print(f"  结束日期: {end_date}")
    print(f"  最大线程数: {max_workers}")
    print("-" * 30)

    # 创建session
    session = create_session_with_cookie(cookie_value)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36", # 使用一个常见的User-Agent
        "cookie": cookie_value
    }
    
    # 创建history目录
    os.makedirs("./history", exist_ok=True)
    
    # 时间戳用于文件名 (例如失败列表)
    timestamp_global = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 获取defect ID列表
    defect_ids = get_all_defect_ids(
        session, headers, team=team, start_date=start_date, 
        end_date=end_date, filter_field=filter_field
    )
    
    if not defect_ids:
        print(f"没有找到符合条件的defect ID!")
        return # 提前退出
    
    print(f"找到了 {len(defect_ids)} 个符合条件的defect ID。")
    
    print(f"正在使用{max_workers}个线程并行获取每个defect的历史记录并保存...")
    
    # 并行获取并保存历史记录
    processed_ids, error_ids = get_histories_parallel(
        defect_ids, session, headers, max_workers=max_workers
    )
    
    print(f"\n历史记录获取和保存完成！成功: {len(processed_ids)}, 失败: {len(error_ids)}")
    
    # 保存获取失败的ID列表
    if error_ids:
        failed_ids_filename = f"./history/failed_defect_ids_for_history_{timestamp_global}.json"
        with open(failed_ids_filename, "w") as f:
            json.dump(error_ids, f)
        print(f"已将获取历史失败的{len(error_ids)}个defect ID保存至文件: {failed_ids_filename}")
    
    print("处理完成!")

if __name__ == "__main__":
    main()
