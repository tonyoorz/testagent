# db_storage.py
import sqlite3
import pandas as pd
import json
import os
import glob
import logging
import re # 用于解析 history 文件名

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 配置 ---
# 将数据库文件创建在 pre-analysis/database 目录下
DB_FILE = '/Users/tonyorz/pre-analysis/database/local_data.db'
MR_FOLDER = '/Users/tonyorz/pre-analysis/mr'
DEFECT_FOLDER = '/Users/tonyorz/pre-analysis/defect'
HISTORY_FOLDER = '/Users/tonyorz/pre-analysis/history'

# --- 辅助函数 (简化嵌套 JSON 提取) ---
def safe_get(data, keys, default=None):
    """安全地从嵌套字典中获取值"""
    if not isinstance(keys, list):
        keys = keys.split('.')
    temp = data
    try:
        for key in keys:
            if isinstance(temp, list): # 如果路径中遇到列表，尝试获取第一个元素
                 if not temp: return default
                 temp = temp[0]
            if key not in temp:
                return default
            temp = temp[key]
        # 如果最终结果是字典或列表，可以考虑返回其JSON字符串或特定字段
        if isinstance(temp, (dict, list)):
             # 例如，如果期望 name，可以返回 temp.get('name', default)
             # 为了通用性，我们先返回原始值，让调用者处理
             return temp
        return temp
    except (TypeError, KeyError, IndexError):
        return default

def safe_get_name(data, key, default=""):
    """安全地提取嵌套字典中的 'name' 字段"""
    value = safe_get(data, key)
    return value.get("name", default) if isinstance(value, dict) else default

def safe_get_fullname(data, key, default=""):
    """安全地提取嵌套字典中的 'full_name' 字段"""
    value = safe_get(data, key)
    return value.get("full_name", default) if isinstance(value, dict) else default

def safe_get_id(data, key, default=""):
     """安全地提取嵌套字典中的 'id' 字段"""
     value = safe_get(data, key)
     return value.get("id", default) if isinstance(value, dict) else default

def safe_get_list_names(data, key, default=None):
    """安全地提取嵌套结构中 'data' 列表下所有字典的 'name' 字段"""
    value = safe_get(data, key)
    if isinstance(value, dict) and 'data' in value and isinstance(value['data'], list):
        names = [item.get("name") for item in value['data'] if isinstance(item, dict) and item.get("name")]
        # 返回 JSON 字符串以便存入 TEXT 列
        return json.dumps(names) if names else None
    # 如果需要返回空列表的 JSON 字符串，取消注释下一行
    # return json.dumps([])
    return default if default is not None else None # 返回 None 或指定的默认值

def get_top_aida_from_list(aida_list_json):
    """从 AIDA 列表的 JSON 字符串中提取 top_aida"""
    if not aida_list_json:
        return None
    try:
        lst_req = json.loads(aida_list_json)
        if not isinstance(lst_req, list) or len(lst_req) == 0:
            return None

        top_req = None # 初始化为 None
        len_req = float('inf') # 初始化为无穷大

        for item in lst_req:
            if not isinstance(item, str):
                continue
            # 假设 AIDA 格式是 "描述 [ID]" 或类似，我们关心最后的 ID 部分的长度
            # 或者，如果 get_top_req 的原始逻辑是找最短的字符串，则简化如下：
            if len(item) < len_req:
                 len_req = len(item)
                 top_req = item
        return top_req
    except json.JSONDecodeError:
        return None
    except Exception: # 其他潜在错误
        return None

def calculate_test_week(timestamp_str):
     """从时间戳字符串计算测试周 ('YY-CWww')"""
     if not timestamp_str:
         return 'Future Planning'
     try:
         # 尝试解析包含 T 和 Z 的格式
         dt = pd.to_datetime(timestamp_str.replace('T', ' ').replace('Z', ''), errors='coerce', format='%Y-%m-%d %H:%M:%S')
         if pd.isna(dt):
             # 尝试不带毫秒的格式
             dt = pd.to_datetime(timestamp_str.split('.')[0], errors='coerce', format='%Y-%m-%d %H:%M:%S')
         if pd.isna(dt):
              # 尝试仅日期格式
              dt = pd.to_datetime(timestamp_str, errors='coerce', format='%Y-%m-%d')

         if not pd.isna(dt):
             # 使用 strftime %y (2位年份) 和 %V (ISO 周数)
             return dt.strftime('%y-CW%V')
         else:
             return 'Future Planning' # 或返回 None
     except Exception:
         return 'Future Planning' # 或返回 None


# --- 数据库连接 ---
try:
    conn = sqlite3.connect(DB_FILE)
    # 启用外键约束 (如果需要的话)
    # conn.execute("PRAGMA foreign_keys = 1")
    cursor = conn.cursor()
    logging.info(f"Successfully connected to database: {DB_FILE}")
except sqlite3.Error as e:
    logging.error(f"Error connecting to database: {e}")
    exit(1)

# --- 创建表 (结构调整后) ---
def create_tables():
    logging.info("Ensuring database tables exist...")
    try:
        # Test Runs 数据表 (来自 mr/*.json)
        # 参考 tdf 的关键字段
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_runs (
            run_id TEXT NOT NULL,          -- 假设顶层 'id' 是唯一的运行 ID
            report_period TEXT NOT NULL,   -- 从文件名提取 Rxxxx
            test_id TEXT,                  -- 从 test.id
            test_name TEXT,                -- 从 test.name
            run_status TEXT,               -- 从 status.name
            tester TEXT,                   -- 从 run_by.full_name
            finished_time TEXT,            -- 从 finished_udf (保留原始字符串)
            test_week TEXT,                -- 从 finished_udf 计算
            project TEXT,                  -- 从 name 或 exec_model_series_udf.name? 需要确认来源
            model TEXT,                    -- 从 exec_model_series_udf.name
            aidas TEXT,                    -- JSON 字符串列表，从 product_areas.data[*].name
            top_aida TEXT,                 -- 从 aidas 列表计算得到的最短/第一个 AIDA
            source_file TEXT,
            PRIMARY KEY (report_period, run_id) -- 假设报告期+运行ID是唯一的
        )
        ''')
        logging.info("Table 'test_runs' ensured.")

        # Defects 数据表 (来自 defect/*.json)
        # 参考 ddf 的关键字段
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS defects (
            defect_id TEXT NOT NULL PRIMARY KEY, -- 从 id
            year INTEGER NOT NULL,               -- 从文件名提取
            creation_time TEXT,                  -- 从 creation_time
            summary TEXT,                        -- 从 name
            description TEXT,                    -- 从 description
            status_phase TEXT,                   -- 从 phase.name
            severity TEXT,                       -- 从 problem_severity_udf.name
            project TEXT,                        -- 从 assigned_ecu_udf.name
            detected_by TEXT,                    -- 从 detected_by.full_name
            detected_in_release TEXT,            -- 从 detected_in_release.name
            domain TEXT,                         -- 从 solution_cluster_udf.name
            aidas TEXT,                          -- JSON 字符串列表，从 product_areas.data[*].name
            top_aida TEXT,                       -- 从 aidas 列表计算
            tags TEXT,                           -- JSON 字符串列表，从 user_tags.data[*].name
            classification TEXT,                 -- JSON 字符串列表，从 reporting_class_udf.data[*].name
            pingpong INTEGER,                    -- 从 ecu_no_of_changes_udf
            vin TEXT,                            -- 从 vin_udf
            source_file TEXT
        )
        ''')
        logging.info("Table 'defects' ensured.")

        # History 数据表 (来自 history/*)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS history_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT,                -- 缺陷 ID 或其他实体 ID
            log_timestamp TEXT,            -- 时间戳 (保留原始字符串)
            user TEXT,                     -- 操作用户
            action_type TEXT,              -- 操作类型 (如 UPDATE, CREATE)
            change_details TEXT,           -- JSON 字符串，包含变更集或其他详情
            source_file TEXT,
            source_format TEXT             -- 'JSON', 'Excel', 'SpecificJSON'
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_object_id ON history_log (object_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history_log (log_timestamp)')
        logging.info("Table 'history_log' and indices ensured.")

        conn.commit()
        logging.info("Database schema setup complete.")
    except sqlite3.Error as e:
        logging.error(f"Error creating tables: {e}")
        conn.rollback()

# --- 数据处理函数 (更新后) ---

def process_test_run_files(folder_path):
    """处理 MR 文件夹下的 JSON 文件到 test_runs 表"""
    logging.info(f"Processing Test Run (MR) JSON files in {folder_path}...")
    for filepath in glob.glob(os.path.join(folder_path, 'R*.json')):
        filename = os.path.basename(filepath)
        report_period = filename.split('.')[0] # 提取 Rxxxx
        logging.info(f"  Processing Test Run JSON: {filename}...")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    logging.warning(f"    Skipping empty file: {filename}")
                    continue
                f.seek(0)
                raw_data = json.load(f)

            # 假设顶层是 {"data": [list of records]}
            if "data" not in raw_data or not isinstance(raw_data["data"], list):
                logging.warning(f"    JSON structure unexpected in {filename}. Expected '{{'data': [...]}}'. Skipping.")
                continue

            records_to_insert = []
            for record in raw_data["data"]:
                if not isinstance(record, dict): continue # 跳过非字典记录

                run_id = record.get('id') # 假设顶层有唯一 run id
                if run_id is None:
                     logging.warning(f"    Skipping record in {filename} due to missing 'id'. Record: {record.get('name', 'N/A')}")
                     continue

                # 提取字段，参考 data_processor.py 中的 tdf 转换
                test_id = safe_get_id(record, 'test')
                test_name = safe_get_name(record, 'test')
                run_status = safe_get_name(record, 'status')
                tester = safe_get_fullname(record, 'run_by')
                finished_time = record.get('finished_udf') # 保留原始字符串
                test_week = calculate_test_week(finished_time)
                # 项目来源需要确认，可能是 'name' 或 'release.name' 或 'exec_model_series_udf.name'
                # 暂时用 release.name 作为 project 示例
                project = safe_get_name(record, 'release', default='Unknown')
                model = safe_get_name(record, 'exec_model_series_udf')
                aidas_list_json = safe_get_list_names(record, 'product_areas')
                top_aida = get_top_aida_from_list(aidas_list_json)

                record_data = {
                    'run_id': str(run_id), # 确保是字符串
                    'report_period': report_period,
                    'test_id': str(test_id) if test_id is not None else None,
                    'test_name': test_name,
                    'run_status': run_status,
                    'tester': tester,
                    'finished_time': finished_time,
                    'test_week': test_week,
                    'project': project,
                    'model': model,
                    'aidas': aidas_list_json,
                    'top_aida': top_aida,
                    'source_file': filename
                }
                records_to_insert.append(record_data)

            # 批量插入
            if records_to_insert:
                try:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO test_runs
                        (run_id, report_period, test_id, test_name, run_status, tester, finished_time, test_week, project, model, aidas, top_aida, source_file)
                        VALUES (:run_id, :report_period, :test_id, :test_name, :run_status, :tester, :finished_time, :test_week, :project, :model, :aidas, :top_aida, :source_file)
                    ''', records_to_insert)
                    logging.info(f"    Inserted/Replaced {len(records_to_insert)} records from {filename}")
                except sqlite3.Error as e:
                    logging.error(f"    Error bulk inserting from {filename}: {e}")
                    # 可以选择在这里尝试逐行插入

        except json.JSONDecodeError:
            logging.error(f"    Error decoding JSON from {filename}")
        except Exception as e:
            logging.error(f"    Unexpected error processing {filename}: {e}")

    conn.commit()
    logging.info("Finished processing Test Run (MR) JSON files.")


def process_defect_files(folder_path):
    """处理 Defect 文件夹下的 JSON 文件到 defects 表"""
    logging.info(f"Processing Defect JSON files in {folder_path}...")
    for filepath in glob.glob(os.path.join(folder_path, '*_defect.json')):
        filename = os.path.basename(filepath)
        year_str = filename.split('_')[0]
        try:
            year = int(year_str)
        except ValueError:
            logging.warning(f"  Could not parse year from filename: {filename}. Skipping.")
            continue

        logging.info(f"  Processing Defect JSON: {filename}...")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    logging.warning(f"    Skipping empty file: {filename}")
                    continue
                f.seek(0)
                raw_data = json.load(f)

             # 假设顶层是 {"data": [list of records]}
            if "data" not in raw_data or not isinstance(raw_data["data"], list):
                logging.warning(f"    JSON structure unexpected in {filename}. Expected '{{'data': [...]}}'. Skipping.")
                continue

            records_to_insert = []
            for record in raw_data["data"]:
                if not isinstance(record, dict): continue

                defect_id = record.get('id')
                if defect_id is None:
                    logging.warning(f"    Skipping defect record in {filename} due to missing 'id'. Record: {record.get('name', 'N/A')}")
                    continue

                # 提取字段，参考 data_processor.py 中的 ddf 转换
                creation_time = record.get('creation_time') # 保留原始字符串
                summary = record.get('name') # 'name' 似乎是摘要
                description = record.get('description')
                status_phase = safe_get_name(record, 'phase') # 或 status_phase?
                severity = safe_get_name(record, 'problem_severity_udf')
                project = safe_get_name(record, 'assigned_ecu_udf')
                detected_by = safe_get_fullname(record, 'detected_by')
                detected_in_release = safe_get_name(record, 'detected_in_release')
                domain = safe_get_name(record, 'solution_cluster_udf')
                aidas_list_json = safe_get_list_names(record, 'product_areas')
                top_aida = get_top_aida_from_list(aidas_list_json)
                tags_list_json = safe_get_list_names(record, 'user_tags')
                classification_list_json = safe_get_list_names(record, 'reporting_class_udf')
                pingpong = record.get('ecu_no_of_changes_udf')
                vin = record.get('vin_udf')

                record_data = {
                    'defect_id': str(defect_id),
                    'year': year,
                    'creation_time': creation_time,
                    'summary': summary,
                    'description': description,
                    'status_phase': status_phase,
                    'severity': severity,
                    'project': project,
                    'detected_by': detected_by,
                    'detected_in_release': detected_in_release,
                    'domain': domain,
                    'aidas': aidas_list_json,
                    'top_aida': top_aida,
                    'tags': tags_list_json,
                    'classification': classification_list_json,
                    'pingpong': pingpong,
                    'vin': vin,
                    'source_file': filename
                }
                records_to_insert.append(record_data)

            # 批量插入
            if records_to_insert:
                try:
                    cursor.executemany('''
                        INSERT OR REPLACE INTO defects
                        (defect_id, year, creation_time, summary, description, status_phase, severity, project,
                         detected_by, detected_in_release, domain, aidas, top_aida, tags, classification,
                         pingpong, vin, source_file)
                        VALUES (:defect_id, :year, :creation_time, :summary, :description, :status_phase, :severity, :project,
                         :detected_by, :detected_in_release, :domain, :aidas, :top_aida, :tags, :classification,
                         :pingpong, :vin, :source_file)
                    ''', records_to_insert)
                    logging.info(f"    Inserted/Replaced {len(records_to_insert)} records from {filename}")
                except sqlite3.Error as e:
                    logging.error(f"    Error bulk inserting from {filename}: {e}")

        except json.JSONDecodeError:
            logging.error(f"    Error decoding JSON from {filename}")
        except Exception as e:
            logging.error(f"    Unexpected error processing {filename}: {e}")

    conn.commit()
    logging.info("Finished processing Defect JSON files.")


def process_history_files(folder_path):
    """处理 History 文件夹下的 JSON 和 Excel 文件到 history_log 表"""
    logging.info(f"Processing History files in {folder_path}...")

    # --- 处理通用 history JSON 文件 ---
    for filepath in glob.glob(os.path.join(folder_path, 'history_DTSV_China_*.json')):
        filename = os.path.basename(filepath)
        logging.info(f"  Processing generic history JSON: {filename}...")
        source_format = 'JSON'
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # 检查文件是否为空
                content = f.read()
                if not content.strip():
                    logging.warning(f"    Skipping empty file: {filename}")
                    continue
                f.seek(0)
                data = json.load(f)

            # 假设通用 history JSON 直接是一个记录列表
            if isinstance(data, list):
                records_to_insert = []
                for record in data:
                    if not isinstance(record, dict): continue
                    # **你需要根据实际 JSON 结构调整这里的 key**
                    object_id = record.get('entity_id') or record.get('id') # 尝试不同 key
                    log_timestamp = record.get('timestamp') or record.get('creation_time')
                    user = safe_get_fullname(record, 'user') or record.get('author_name') # 尝试不同用户字段
                    action_type = record.get('operation_type') or record.get('action') # 尝试不同动作字段
                    # 将整个记录或其中的 'change_set'/'details' 存储为 JSON 字符串
                    details_field = record.get('change_set') or record.get('details') or record # 获取详情，或整个记录
                    change_details = json.dumps(details_field) if details_field else None

                    record_data = {
                        'object_id': str(object_id) if object_id else None,
                        'log_timestamp': log_timestamp,
                        'user': user,
                        'action_type': action_type,
                        'change_details': change_details,
                        'source_file': filename,
                        'source_format': source_format
                    }
                    records_to_insert.append(record_data)

                # 批量插入
                if records_to_insert:
                    try:
                        cursor.executemany('''
                            INSERT INTO history_log (object_id, log_timestamp, user, action_type, change_details, source_file, source_format)
                            VALUES (:object_id, :log_timestamp, :user, :action_type, :change_details, :source_file, :source_format)
                        ''', records_to_insert)
                        logging.info(f"    Inserted {len(records_to_insert)} records from {filename}")
                    except sqlite3.Error as e:
                        logging.error(f"    Error bulk inserting from {filename}: {e}")

            else:
                logging.warning(f"    Expected a list of records in {filename}, but got {type(data)}. Skipping.")

        except json.JSONDecodeError:
             logging.error(f"    Error decoding JSON from {filename}")
        except Exception as e:
            logging.error(f"    Unexpected error processing {filename}: {e}")

    # --- 处理通用 history Excel 文件 ---
    try:
        import openpyxl # 确保 openpyxl 已安装
        for filepath in glob.glob(os.path.join(folder_path, 'history_DTSV_China_*.xlsx')):
            filename = os.path.basename(filepath)
            logging.info(f"  Processing generic history Excel: {filename}...")
            source_format = 'Excel'
            try:
                df = pd.read_excel(filepath)
                if df.empty:
                    logging.warning(f"    Skipping empty Excel file: {filename}")
                    continue

                # **你需要根据实际 Excel 列名调整这里的列名**
                # 假设列名为: 'ID', 'Timestamp', 'User Name', 'Action', 'Changed Fields'
                required_cols_map = {
                    'ID': 'object_id',                  # **替换实际 Excel 列名**
                    'Timestamp': 'log_timestamp',       # **替换实际 Excel 列名**
                    'User Name': 'user',                # **替换实际 Excel 列名**
                    'Action': 'action_type',            # **替换实际 Excel 列名**
                    'Changed Fields': 'change_details' # **替换实际 Excel 列名**
                }
                # 过滤掉 DataFrame 中不存在的列
                cols_to_rename = {k: v for k, v in required_cols_map.items() if k in df.columns}
                missing_cols = set(required_cols_map.keys()) - set(df.columns)
                if missing_cols:
                     logging.warning(f"    Missing expected columns in {filename}: {missing_cols}. Proceeding with available columns.")

                if not cols_to_rename:
                    logging.error(f"    No required columns found in {filename}. Skipping.")
                    continue

                df_to_insert = df[list(cols_to_rename.keys())].rename(columns=cols_to_rename)
                df_to_insert['source_file'] = filename
                df_to_insert['source_format'] = source_format

                # 转换数据类型并处理 NaN
                df_to_insert = df_to_insert.astype(str).where(pd.notnull(df_to_insert), None)

                records = df_to_insert.to_dict('records')

                # 批量或逐行插入
                if records:
                     try:
                        cursor.executemany('''
                            INSERT INTO history_log (object_id, log_timestamp, user, action_type, change_details, source_file, source_format)
                            VALUES (:object_id, :log_timestamp, :user, :action_type, :change_details, :source_file, :source_format)
                        ''', records)
                        logging.info(f"    Inserted {len(records)} records from {filename}")
                     except sqlite3.Error as e:
                         logging.error(f"    Error bulk inserting from {filename}: {e}")

            except Exception as e:
                 logging.error(f"    Unexpected error processing Excel {filename}: {e}")
    except ImportError:
        logging.warning("Skipping .xlsx files because 'openpyxl' is not installed. Run: pip install openpyxl pandas")

    # --- 处理特定 ID 的 history 文件 (JSON) ---
    for filepath in glob.glob(os.path.join(folder_path, '*_history.json')):
        filename = os.path.basename(filepath)
        # 改进文件名解析以处理非数字前缀的可能性
        match = re.match(r"(\d+)_history\.json", filename)
        if match:
            object_id_str = match.group(1)
            logging.info(f"  Processing specific history JSON: {filename} (Object ID: {object_id_str})...")
            source_format = 'SpecificJSON'
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    # 检查文件是否为空
                    content = f.read()
                    if not content.strip():
                         logging.warning(f"    Skipping empty file: {filename}")
                         continue
                    f.seek(0)
                    # 检查 history JSON 的顶层结构
                    raw_data = json.load(f)

                data_list = []
                if isinstance(raw_data, list): # 直接是列表
                    data_list = raw_data
                elif isinstance(raw_data, dict) and 'data' in raw_data and isinstance(raw_data['data'], list): # 包含在 'data' 键下
                    data_list = raw_data['data']
                else:
                     logging.warning(f"    Unexpected JSON structure in specific history file {filename}. Expected list or {{'data': [...]}}. Skipping.")
                     continue


                if data_list:
                    records_to_insert = []
                    for record in data_list:
                        if not isinstance(record, dict): continue
                         # **根据特定 history JSON 结构调整 key**
                        log_timestamp = record.get('timestamp') # 通常有 timestamp
                        user = safe_get_fullname(record, 'user') # 通常有 user
                        action_type = record.get('operation_type') # 可能有 operation_type
                        # 将 change_set 或整个记录作为详情
                        details_field = record.get('change_set') or record
                        change_details = json.dumps(details_field) if details_field else None

                        record_data = {
                            'object_id': object_id_str, # 使用从文件名提取的 ID
                            'log_timestamp': log_timestamp,
                            'user': user,
                            'action_type': action_type,
                            'change_details': change_details,
                            'source_file': filename,
                            'source_format': source_format
                        }
                        records_to_insert.append(record_data)

                    # 批量插入
                    if records_to_insert:
                        try:
                            cursor.executemany('''
                                INSERT INTO history_log (object_id, log_timestamp, user, action_type, change_details, source_file, source_format)
                                VALUES (:object_id, :log_timestamp, :user, :action_type, :change_details, :source_file, :source_format)
                            ''', records_to_insert)
                            logging.info(f"    Inserted {len(records_to_insert)} records from {filename}")
                        except sqlite3.Error as e:
                            logging.error(f"    Error bulk inserting from {filename}: {e}")
                else:
                    logging.warning(f"    No data found in list within {filename}.")


            except json.JSONDecodeError:
                logging.error(f"    Error decoding JSON from {filename}")
            except Exception as e:
                logging.error(f"    Unexpected error processing {filename}: {e}")
        else:
            # 忽略不匹配 `数字_history.json` 模式的文件，除非它是通用的 history 文件
            if not filename.startswith('history_DTSV_China_'):
                logging.debug(f"  Skipping file (doesn't match ID_history.json pattern): {filename}")

    conn.commit()
    logging.info("Finished processing History files.")


# --- 主程序 ---
if __name__ == "__main__":
    logging.info("Starting ETL process...")

    # 确保 pandas 和 openpyxl 已安装（如果需要处理 Excel）
    try:
        import pandas
        import openpyxl
    except ImportError as ie:
        logging.error(f"Missing required library: {ie}. Please install pandas and openpyxl: pip install pandas openpyxl")
        exit(1)


    create_tables()

    # 处理各个文件夹 (调用更新后的函数)
    process_test_run_files(MR_FOLDER)
    process_defect_files(DEFECT_FOLDER)
    process_history_files(HISTORY_FOLDER)

    # 关闭数据库连接
    if conn:
        # 可以选择在这里执行一些清理或优化操作，例如 VACUUM
        # logging.info("Optimizing database...")
        # cursor.execute("VACUUM;")
        conn.close()
        logging.info(f"Database connection closed. ETL process finished. Database file: '{DB_FILE}'")

    print("\n--- IMPORTANT ---")
    print("The script has finished processing JSON and Excel files.")
    print(f"A SQLite database file should be created/updated at: {DB_FILE}")
    print("Please review the log messages above for any errors or warnings.")
    print("The script attempts to extract data based on common patterns observed in data_processor.py.")
    print("You may need to adjust the JSON key lookups (e.g., 'safe_get', 'safe_get_name')")
    print("and Excel column names ('required_cols_map' in process_history_files)")
    print("if your actual file structures differ significantly.")
    print("Complex derived fields (like FV, Team, FVP) are NOT calculated here; store raw data instead.")
