#!/usr/bin/env python3
"""
Long Runner Analysis Tool
=========================
分析history数据中ticket的phase变更时间，计算各阶段耗时统计

功能:
1. 分析单个ticket的phase duration
2. 批量分析所有tickets的phase duration
3. 生成统计报告和CSV导出
4. 计算平均耗时、最大最小值等统计信息

使用方法:
python longrunner_analysis.py                    # 运行完整分析
python longrunner_analysis.py --ticket 2135182  # 分析单个ticket
python longrunner_analysis.py --summary         # 只显示汇总报告
"""

import json
import os
import sqlite3
import hashlib
import argparse
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed


def _default_octane_db_path() -> str:
    env_db_path = os.environ.get("OCTANE_DB_PATH")
    if env_db_path:
        return env_db_path

    rebuilt_path = os.path.join("database", "local_data_rebuilt.db")
    if os.path.exists(rebuilt_path):
        return rebuilt_path

    return os.path.join("database", "local_data.db")


def _load_history_data(ticket_id: str, history_folder: str = "history") -> Optional[Dict]:
    """数据库优先获取历史数据，文件兜底。"""
    source_mode = os.environ.get("OCTANE_DATA_SOURCE", "db_only").strip().lower()
    try:
        from data_processor import get_history_data as _dp_get_history_data
        data = _dp_get_history_data(ticket_id, history_folder)
        if data:
            return data
    except Exception:
        pass

    if source_mode == "db_only":
        return None

    history_file = os.path.join(history_folder, f"{ticket_id}_history.json")
    if not os.path.exists(history_file):
        return None

    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _get_ticket_ids_from_db() -> List[str]:
    db_path = _default_octane_db_path()
    if not db_path or not os.path.exists(db_path):
        return []

    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute("SELECT defect_id FROM octane_defect_histories").fetchall()
        finally:
            conn.close()
        return [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
    except Exception:
        return []

# ========================================
# Phase Analysis Core Functions
# ========================================

def extract_phase_changes(history_data: Dict) -> List[Dict]:
    """
    从history数据中提取phase变更记录
    """
    phase_changes = []
    
    for entry in history_data.get('data', []):
        timestamp = entry.get('timestamp')
        change_set = entry.get('change_set', [])
        
        for change in change_set:
            if change.get('field_name') == 'phase':
                phase_changes.append({
                    'timestamp': timestamp,
                    'from_phase': change.get('old_value_text'),
                    'to_phase': change.get('value_text'),
                    'user_name': entry.get('user_name'),
                    'action': entry.get('action')
                })
    
    # 按时间排序（从最早到最新）
    phase_changes.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '')
    
    return phase_changes

def calculate_phase_duration(phase_changes: List[Dict]) -> List[Dict]:
    """
    计算每个phase的持续时间（小时）
    """
    durations = []
    
    for i in range(len(phase_changes)):
        current_change = phase_changes[i]
        
        # 计算从上一个phase到当前phase的时间间隔
        if i > 0:
            prev_timestamp = phase_changes[i-1]['timestamp']
            current_timestamp = current_change['timestamp']
            
            if prev_timestamp and current_timestamp:
                # 解析时间戳
                prev_time = datetime.fromisoformat(prev_timestamp.replace('Z', '+00:00'))
                current_time = datetime.fromisoformat(current_timestamp.replace('Z', '+00:00'))
                
                # 计算时间差（小时）
                time_diff = current_time - prev_time
                hours = time_diff.total_seconds() / 3600
                
                durations.append({
                    'from_phase': phase_changes[i-1]['to_phase'] if i > 0 else current_change['from_phase'],
                    'to_phase': current_change['to_phase'],
                    'duration_hours': round(hours, 2),
                    'start_time': prev_timestamp,
                    'end_time': current_timestamp,
                    'changed_by': current_change['user_name']
                })
    
    return durations


def _parse_iso_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
    except Exception:
        return None


def build_phase_segments(
    history_data: Dict,
    ticket_meta: Optional[Dict] = None,
    now: Optional[datetime] = None,
) -> List[Dict]:
    """Build per-phase timeline segments from history data."""
    phase_changes = extract_phase_changes(history_data)
    if not phase_changes:
        return []

    ticket_meta = ticket_meta or {}
    ticket_id = str(ticket_meta.get('ticket_id') or '')
    ticket_name = str(ticket_meta.get('ticket_name') or f'Ticket {ticket_id}' if ticket_id else 'Unknown Ticket')
    current_time = now or datetime.now().astimezone()
    segments = []

    for index, change in enumerate(phase_changes):
        start_dt = _parse_iso_timestamp(change.get('timestamp'))
        if start_dt is None:
            continue

        next_change = phase_changes[index + 1] if index + 1 < len(phase_changes) else None
        next_dt = _parse_iso_timestamp(next_change.get('timestamp')) if next_change else None
        is_open_segment = next_dt is None
        end_dt = next_dt or current_time

        duration_hours = round(max((end_dt - start_dt).total_seconds(), 0) / 3600, 2)
        segments.append({
            'ticket_id': ticket_id,
            'ticket_name': ticket_name,
            'phase': change.get('to_phase'),
            'from_phase': change.get('from_phase'),
            'to_phase': change.get('to_phase'),
            'start_time': start_dt.isoformat(),
            'end_time': end_dt.isoformat(),
            'duration_hours': duration_hours,
            'duration_days': round(duration_hours / 24, 2),
            'is_open_segment': is_open_segment,
            'changed_by': change.get('user_name'),
        })

    return segments

def analyze_ticket_phases(ticket_id: str, history_folder: str = 'history') -> Dict:
    """
    分析指定ticket的phase变更时间
    """
    try:
        history_data = _load_history_data(ticket_id, history_folder)
        if not history_data:
            return {'error': f'History data not found for ticket {ticket_id}'}

        found_in_functions = set()
        phase02_found_in_functions = set()
        for entry in history_data.get("data", []) or []:
            change_set = entry.get("change_set", []) or []
            moved_to_phase02 = False
            for change in change_set:
                if change.get("field_name") != "phase":
                    continue
                to_phase = change.get("value_text") or change.get("valueName") or ""
                to_phase = str(to_phase).strip()
                if to_phase.startswith("02-"):
                    moved_to_phase02 = True
                    break

            for change in change_set:
                if change.get("field_name") != "product_areas":
                    continue
                field_label = str(change.get("field_label") or "").strip().lower()
                if field_label and "found" in field_label and "function" in field_label:
                    val = change.get("value_text") or change.get("valueName") or ""
                    val = str(val).strip()
                    if val:
                        found_in_functions.add(val)
                        if moved_to_phase02:
                            phase02_found_in_functions.add(val)
        
        # 提取phase变更
        phase_changes = extract_phase_changes(history_data)
        
        if not phase_changes:
            return {'error': f'No phase changes found for ticket {ticket_id}'}
        
        # 计算持续时间
        durations = calculate_phase_duration(phase_changes)
        
        # 计算总时间
        total_hours = sum(d['duration_hours'] for d in durations)
        
        return {
            'ticket_id': ticket_id,
            'phase_changes': phase_changes,
            'phase_durations': durations,
            'found_in_functions': sorted(found_in_functions),
            'phase02_found_in_functions': sorted(phase02_found_in_functions),
            'total_duration_hours': round(total_hours, 2),
            'total_duration_days': round(total_hours / 24, 2)
        }
        
    except Exception as e:
        return {'error': f'Error processing ticket {ticket_id}: {str(e)}'}


_CACHE_VERSION = 3
_TICKET_ANALYSIS_CACHE = {}
_TICKET_ANALYSIS_CACHE_LOCK = threading.Lock()


def _history_file_fingerprint(history_file: str) -> Optional[Dict]:
    try:
        st = os.stat(history_file)
        return {"mtime_ns": int(st.st_mtime_ns), "size": int(st.st_size)}
    except OSError:
        return None


def _history_db_fingerprint(ticket_id: str) -> Optional[Dict]:
    db_path = _default_octane_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT payload_json FROM octane_defect_histories WHERE defect_id = ?",
                (str(ticket_id),),
            ).fetchone()
        finally:
            conn.close()

        if not row or not row[0]:
            return None

        payload_text = str(row[0])
        return {
            "hash": hashlib.md5(payload_text.encode("utf-8")).hexdigest(),
            "size": len(payload_text),
            "source": "db",
        }
    except Exception:
        return None


def _cache_file_path(cache_dir: str, ticket_id: str) -> str:
    safe_ticket_id = str(ticket_id).strip()
    return os.path.join(cache_dir, f"{safe_ticket_id}.json")


def analyze_ticket_phases_cached(
    ticket_id: str,
    history_folder: str = "history",
    cache_dir: Optional[str] = None,
    use_cache: bool = True,
) -> Dict:
    if not use_cache:
        return analyze_ticket_phases(ticket_id, history_folder)

    history_file = os.path.join(history_folder, f"{ticket_id}_history.json")
    fingerprint = _history_db_fingerprint(ticket_id)
    if fingerprint is None:
        file_fp = _history_file_fingerprint(history_file)
        if file_fp is not None:
            fingerprint = {
                "hash": f"{file_fp['mtime_ns']}:{file_fp['size']}",
                "size": int(file_fp["size"]),
                "source": "file",
            }
    if fingerprint is None:
        return analyze_ticket_phases(ticket_id, history_folder)

    cache_key = (str(ticket_id), str(fingerprint.get("source")), str(fingerprint.get("hash")), int(fingerprint.get("size", 0)))
    with _TICKET_ANALYSIS_CACHE_LOCK:
        cached = _TICKET_ANALYSIS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if cache_dir:
        cache_file = _cache_file_path(cache_dir, ticket_id)
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if (
                payload.get("cache_version") == _CACHE_VERSION
                and str(payload.get("source_hash", "")) == str(fingerprint.get("hash", ""))
                and int(payload.get("source_size", -1)) == int(fingerprint.get("size", -1))
                and payload.get("ticket_id") == str(ticket_id)
                and "phase_durations" in payload
            ):
                result = {
                    "ticket_id": str(ticket_id),
                    "phase_durations": payload.get("phase_durations") or [],
                    "found_in_functions": payload.get("found_in_functions") or [],
                    "phase02_found_in_functions": payload.get("phase02_found_in_functions") or [],
                    "total_duration_hours": payload.get("total_duration_hours", 0),
                    "total_duration_days": payload.get("total_duration_days", 0),
                }
                with _TICKET_ANALYSIS_CACHE_LOCK:
                    _TICKET_ANALYSIS_CACHE[cache_key] = result
                return result
        except OSError:
            pass
        except Exception:
            pass

    result = analyze_ticket_phases(ticket_id, history_folder)
    if "error" in result:
        return result

    minimal_result = {
        "ticket_id": str(result.get("ticket_id") or ticket_id),
        "phase_durations": result.get("phase_durations") or [],
        "found_in_functions": result.get("found_in_functions") or [],
        "phase02_found_in_functions": result.get("phase02_found_in_functions") or [],
        "total_duration_hours": result.get("total_duration_hours", 0),
        "total_duration_days": result.get("total_duration_days", 0),
    }

    with _TICKET_ANALYSIS_CACHE_LOCK:
        _TICKET_ANALYSIS_CACHE[cache_key] = minimal_result

    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = _cache_file_path(cache_dir, ticket_id)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "cache_version": _CACHE_VERSION,
                        "ticket_id": str(ticket_id),
                        "source_hash": str(fingerprint.get("hash", "")),
                        "source_size": int(fingerprint.get("size", 0)),
                        "phase_durations": minimal_result["phase_durations"],
                        "found_in_functions": minimal_result["found_in_functions"],
                        "phase02_found_in_functions": minimal_result["phase02_found_in_functions"],
                        "total_duration_hours": minimal_result["total_duration_hours"],
                        "total_duration_days": minimal_result["total_duration_days"],
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    return minimal_result

def print_phase_analysis(result: Dict):
    """
    打印phase分析结果
    """
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    
    ticket_id = result['ticket_id']
    print(f"\n=== Phase Analysis for Ticket {ticket_id} ===")
    
    print("\nPhase Changes Timeline:")
    for i, change in enumerate(result['phase_changes']):
        print(f"{i+1}. {change['timestamp']} - {change['from_phase']} → {change['to_phase']} (by {change['user_name']})")
    
    print("\nPhase Durations:")
    for duration in result['phase_durations']:
        print(f"  {duration['from_phase']} → {duration['to_phase']}: {duration['duration_hours']} hours ({duration['duration_hours']/24:.1f} days)")
    
    print(f"\nTotal Duration: {result['total_duration_hours']} hours ({result['total_duration_days']} days)")

# ========================================
# Bulk Analysis Functions
# ========================================

def get_all_ticket_ids(history_folder: str = 'history') -> List[str]:
    """
    获取所有有history文件的ticket ID
    """
    ticket_ids_db = _get_ticket_ids_from_db()
    if ticket_ids_db:
        return sorted(set(ticket_ids_db))

    if os.environ.get("OCTANE_DATA_SOURCE", "db_only").strip().lower() == "db_only":
        return []

    ticket_ids = []
    if not os.path.exists(history_folder):
        return ticket_ids

    for filename in os.listdir(history_folder):
        if filename.endswith('_history.json'):
            ticket_id = filename.replace('_history.json', '')
            ticket_ids.append(ticket_id)
    return sorted(ticket_ids)

def bulk_analyze_phases(
    ticket_ids: List[str],
    history_folder: str = "history",
    show_progress: bool = True,
    max_workers: int = 1,
    cache_dir: Optional[str] = None,
    use_cache: bool = True,
    return_all_results: bool = True,
    return_duration_records: bool = False,
    return_ticket_meta: bool = False,
) -> Dict:
    """
    批量分析所有ticket的phase duration
    """
    all_results = [] if return_all_results else None
    all_durations = defaultdict(list)  # phase_name -> [duration1, duration2, ...]
    all_duration_records = defaultdict(list) if return_duration_records else None
    ticket_meta = {} if return_ticket_meta else None
    successful_analyses = 0
    failed_analyses = 0
    
    total = len(ticket_ids)
    if show_progress:
        print(f"开始分析 {total} 个tickets...", flush=True)
    progress_step = max(1, total // 20) if total > 0 else 1
    
    def _analyze_one(tid: str) -> Dict:
        return analyze_ticket_phases_cached(tid, history_folder, cache_dir=cache_dir, use_cache=use_cache)

    if max_workers and int(max_workers) > 1 and total > 1:
        mw = int(max_workers)
        with ThreadPoolExecutor(max_workers=mw) as executor:
            future_to_tid = {executor.submit(_analyze_one, ticket_id): ticket_id for ticket_id in ticket_ids}
            futures = list(future_to_tid.keys())
            for i, fut in enumerate(as_completed(futures), start=1):
                if show_progress and (i == 1 or i % progress_step == 0 or i == total):
                    print(f"进度: {i}/{total}", flush=True)

                ticket_id = future_to_tid.get(fut)
                result = fut.result()
                if "error" in result:
                    failed_analyses += 1
                    continue

                successful_analyses += 1
                if all_results is not None:
                    all_results.append(result)
                if ticket_meta is not None and ticket_id is not None:
                    ticket_meta[str(ticket_id)] = result.get("found_in_functions") or result.get("phase02_found_in_functions") or []

                for duration in result.get("phase_durations", []):
                    phase_transition = f"{duration['from_phase']} → {duration['to_phase']}"
                    all_durations[phase_transition].append(duration["duration_hours"])
                    if all_duration_records is not None:
                        all_duration_records[phase_transition].append(
                            {
                                "ticket_id": str(ticket_id) if ticket_id is not None else None,
                                "from_phase": duration.get("from_phase"),
                                "to_phase": duration.get("to_phase"),
                                "duration_hours": duration.get("duration_hours"),
                                "start_time": duration.get("start_time"),
                                "end_time": duration.get("end_time"),
                                "changed_by": duration.get("changed_by"),
                            }
                        )
    else:
        for i, ticket_id in enumerate(ticket_ids):
            if show_progress and (i == 0 or (i + 1) % progress_step == 0 or (i + 1) == total):
                print(f"进度: {i+1}/{total}", flush=True)

            result = _analyze_one(ticket_id)
            if "error" in result:
                failed_analyses += 1
                continue

            successful_analyses += 1
            if all_results is not None:
                all_results.append(result)
            if ticket_meta is not None:
                ticket_meta[str(ticket_id)] = result.get("found_in_functions") or result.get("phase02_found_in_functions") or []

            for duration in result.get("phase_durations", []):
                phase_transition = f"{duration['from_phase']} → {duration['to_phase']}"
                all_durations[phase_transition].append(duration["duration_hours"])
                if all_duration_records is not None:
                    all_duration_records[phase_transition].append(
                        {
                            "ticket_id": str(ticket_id),
                            "from_phase": duration.get("from_phase"),
                            "to_phase": duration.get("to_phase"),
                            "duration_hours": duration.get("duration_hours"),
                            "start_time": duration.get("start_time"),
                            "end_time": duration.get("end_time"),
                            "changed_by": duration.get("changed_by"),
                        }
                    )
    
    if show_progress:
        print(f"分析完成! 成功: {successful_analyses}, 失败: {failed_analyses}", flush=True)
    
    return {
        'all_results': all_results,
        'phase_durations': dict(all_durations),
        'phase_duration_records': dict(all_duration_records) if all_duration_records is not None else None,
        'ticket_meta': ticket_meta,
        'successful_count': successful_analyses,
        'failed_count': failed_analyses
    }

def calculate_phase_statistics(phase_durations: Dict[str, List[float]]) -> Dict:
    """
    计算每个phase transition的统计信息
    """
    statistics = {}
    
    for phase_transition, durations in phase_durations.items():
        if durations:
            statistics[phase_transition] = {
                'count': len(durations),
                'avg_hours': round(sum(durations) / len(durations), 2),
                'avg_days': round(sum(durations) / len(durations) / 24, 2),
                'min_hours': round(min(durations), 2),
                'max_hours': round(max(durations), 2),
                'median_hours': round(sorted(durations)[len(durations)//2], 2)
            }
    
    return statistics

def print_phase_statistics(statistics: Dict):
    """
    打印phase统计报告
    """
    print("\n" + "="*80)
    print("2025年所有Tickets Phase Duration 统计报告")
    print("="*80)
    
    # 按平均时间排序
    sorted_phases = sorted(statistics.items(), key=lambda x: x[1]['avg_hours'], reverse=True)
    
    print(f"\n{'Phase Transition':<40} {'Count':<8} {'Avg(Hours)':<12} {'Avg(Days)':<10} {'Min(H)':<8} {'Max(H)':<8} {'Median(H)':<10}")
    print("-" * 100)
    
    for phase_transition, stats in sorted_phases:
        print(f"{phase_transition:<40} {stats['count']:<8} {stats['avg_hours']:<12} {stats['avg_days']:<10} {stats['min_hours']:<8} {stats['max_hours']:<8} {stats['median_hours']:<10}")
    
    # 总体统计
    total_transitions = sum(stats['count'] for stats in statistics.values())
    overall_avg = sum(stats['avg_hours'] * stats['count'] for stats in statistics.values()) / total_transitions if total_transitions > 0 else 0
    
    print(f"\n总计phase transitions: {total_transitions}")
    print(f"加权平均耗时: {overall_avg:.2f} hours ({overall_avg/24:.2f} days)")

def save_to_csv(statistics: Dict, filename: str = 'phase_statistics_2025.csv'):
    """
    保存统计结果到CSV文件
    """
    try:
        import pandas as pd
        data = []
        for phase_transition, stats in statistics.items():
            data.append({
                'Phase_Transition': phase_transition,
                'Count': stats['count'],
                'Avg_Hours': stats['avg_hours'],
                'Avg_Days': stats['avg_days'],
                'Min_Hours': stats['min_hours'],
                'Max_Hours': stats['max_hours'],
                'Median_Hours': stats['median_hours']
            })
        
        df = pd.DataFrame(data)
        df = df.sort_values('Avg_Hours', ascending=False)
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"\n统计结果已保存到: {filename}")
    except ImportError:
        # 手动保存CSV
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("Phase_Transition,Count,Avg_Hours,Avg_Days,Min_Hours,Max_Hours,Median_Hours\n")
            sorted_phases = sorted(statistics.items(), key=lambda x: x[1]['avg_hours'], reverse=True)
            for phase_transition, stats in sorted_phases:
                f.write(f"\"{phase_transition}\",{stats['count']},{stats['avg_hours']},{stats['avg_days']},{stats['min_hours']},{stats['max_hours']},{stats['median_hours']}\n")
        print(f"\n统计结果已保存到: {filename}")

def create_summary_report(statistics: Dict):
    """
    创建phase duration汇总报告
    """
    print("\n" + "="*60)
    print("2025年 TOP 10 最耗时的Phase Transitions")
    print("="*60)
    
    # 按平均时间排序，取前10
    sorted_phases = sorted(statistics.items(), key=lambda x: x[1]['avg_hours'], reverse=True)[:10]
    
    for i, (phase, stats) in enumerate(sorted_phases, 1):
        print(f"{i:2d}. {phase}")
        print(f"    平均耗时: {stats['avg_hours']:.1f}小时 ({stats['avg_days']:.1f}天)")
        print(f"    样本数量: {stats['count']} 个tickets")
        print(f"    耗时范围: {stats['min_hours']:.1f}h - {stats['max_hours']:.1f}h")
        print()
    
    # 主要阶段统计
    print("\n" + "="*60)
    print("主要Phase耗时统计 (样本量 > 100)")
    print("="*60)
    
    major_phases = [(k, v) for k, v in statistics.items() if v['count'] > 100]
    major_phases.sort(key=lambda x: x[1]['avg_hours'], reverse=True)
    
    for phase, stats in major_phases:
        print(f"• {phase}")
        print(f"  平均: {stats['avg_hours']:.1f}h ({stats['avg_days']:.1f}天), 样本: {stats['count']}")
    
    # 整体统计
    total_transitions = sum(stats['count'] for stats in statistics.values())
    overall_avg = sum(stats['avg_hours'] * stats['count'] for stats in statistics.values()) / total_transitions
    
    print(f"\n总体统计:")
    print(f"• 分析了 {len(statistics)} 种phase transitions")
    print(f"• 总计 {total_transitions:,} 个phase transitions")
    print(f"• 整体加权平均耗时: {overall_avg:.1f}小时 ({overall_avg/24:.1f}天)")

# ========================================
# Main Functions
# ========================================

def run_full_analysis(history_folder: str = 'history'):
    """
    运行完整的批量分析
    """
    # 获取所有ticket IDs
    print("获取所有ticket IDs...")
    ticket_ids = get_all_ticket_ids(history_folder)
    print(f"找到 {len(ticket_ids)} 个tickets")
    
    # 批量分析
    bulk_results = bulk_analyze_phases(ticket_ids, history_folder)
    
    # 计算统计信息
    print("计算统计信息...")
    statistics = calculate_phase_statistics(bulk_results['phase_durations'])
    
    # 打印报告
    print_phase_statistics(statistics)
    
    # 保存到CSV
    save_to_csv(statistics)
    
    # 生成汇总报告
    create_summary_report(statistics)
    
    return statistics

def run_single_ticket_analysis(ticket_id: str, history_folder: str = 'history'):
    """
    分析单个ticket
    """
    result = analyze_ticket_phases(ticket_id, history_folder)
    print_phase_analysis(result)
    return result

def run_summary_only(history_folder: str = 'history'):
    """
    只运行汇总报告（如果CSV文件存在）
    """
    csv_file = 'phase_statistics_2025.csv'
    if os.path.exists(csv_file):
        print("从现有CSV文件读取统计数据...")
        statistics = {}
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[1:]  # 跳过header
                for line in lines:
                    parts = line.strip().split(',')
                    if len(parts) >= 7:
                        phase_name = parts[0].strip('"')
                        statistics[phase_name] = {
                            'count': int(parts[1]),
                            'avg_hours': float(parts[2]),
                            'avg_days': float(parts[3]),
                            'min_hours': float(parts[4]),
                            'max_hours': float(parts[5]),
                            'median_hours': float(parts[6])
                        }
            create_summary_report(statistics)
        except Exception as e:
            print(f"读取CSV文件失败: {e}")
            print("运行完整分析...")
            return run_full_analysis(history_folder)
    else:
        print("CSV文件不存在，运行完整分析...")
        return run_full_analysis(history_folder)

def main():
    """
    主函数：处理命令行参数并执行相应功能
    """
    parser = argparse.ArgumentParser(
        description="Long Runner Analysis Tool - 分析ticket phase duration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python longrunner_analysis.py                    # 运行完整分析
  python longrunner_analysis.py --ticket 2135182  # 分析单个ticket
  python longrunner_analysis.py --summary         # 只显示汇总报告
  python longrunner_analysis.py --folder ./data   # 指定history文件夹
        """
    )
    
    parser.add_argument('--ticket', '-t', help='分析指定的ticket ID')
    parser.add_argument('--summary', '-s', action='store_true', help='只显示汇总报告')
    parser.add_argument('--folder', '-f', default='history', help='history文件夹路径 (默认: history)')
    
    args = parser.parse_args()
    
    print("Long Runner Analysis Tool")
    print("=" * 40)
    
    try:
        if args.ticket:
            # 分析单个ticket
            print(f"分析单个ticket: {args.ticket}")
            run_single_ticket_analysis(args.ticket, args.folder)
        elif args.summary:
            # 只显示汇总报告
            run_summary_only(args.folder)
        else:
            # 运行完整分析
            run_full_analysis(args.folder)
    except KeyboardInterrupt:
        print("\n\n分析被用户中断")
    except Exception as e:
        print(f"\n执行错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
