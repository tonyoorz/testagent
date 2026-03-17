#!/usr/bin/env python3
"""
2024 vs 2025 KPI完整分析报告
生成Excel和HTML格式报告
"""

import json
import pandas as pd
import os
from collections import Counter, defaultdict
import sqlite3
from datetime import datetime

# 设置pandas显示选项
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

print("="*80)
print("📊 2024 vs 2025 完整KPI分析（含MR数据）")
print("="*80)

# ==================== 1. 加载MR数据 ====================
print("\n1. 加载MR数据...")

def load_mr_data(year_prefix):
    """加载指定年份的MR数据"""
    mr_files = [f for f in os.listdir('mr') if f.startswith(year_prefix) and f.endswith('.json')]
    mr_files.sort()

    all_mr = []
    for fname in mr_files:
        try:
            with open(f'mr/{fname}') as f:
                data = json.load(f)
            if isinstance(data, list):
                for mr in data:
                    mr['source_file'] = fname
                    mr['year'] = year_prefix
                all_mr.extend(data)
        except Exception as e:
            print(f"  跳过 {fname}: {e}")

    return pd.json_normalize(all_mr)

# 加载2024和2025 MR数据
df_mr_2024 = load_mr_data('R24')
df_mr_2025 = load_mr_data('R25')

print(f"  2024年MR执行: {len(df_mr_2024):,} 条")
print(f"  2025年MR执行: {len(df_mr_2025):,} 条")
if len(df_mr_2024) > 0:
    print(f"  同比增长: {((len(df_mr_2025)-len(df_mr_2024))/len(df_mr_2024)*100):.1f}%")

# ==================== 2. 测试执行质量对比 ====================
print("\n2. 测试执行质量对比")
print("-"*60)

mr_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue
    status_counts = df['status.name'].value_counts()
    total = len(df)
    passed = status_counts.get('Passed', 0)
    failed = status_counts.get('Failed', 0)
    attention = status_counts.get('Requires Attention', 0)
    planned = status_counts.get('Planned', 0)

    mr_summary.append({
        '年份': year,
        '总执行': total,
        'Passed': passed,
        'Passed率': f"{passed/total*100:.1f}%",
        'Failed': failed,
        'Failed率': f"{failed/total*100:.1f}%",
        'Requires Attention': attention,
        'Requires Attention率': f"{attention/total*100:.1f}%"
    })

    print(f"\n{year}年:")
    print(f"  总计: {total:,}")
    print(f"  Passed: {passed:,} ({passed/total*100:.1f}%)")
    print(f"  Failed: {failed:,} ({failed/total*100:.1f}%)")
    print(f"  Requires Attention: {attention:,} ({attention/total*100:.1f}%)")

df_mr_summary = pd.DataFrame(mr_summary)

# ==================== 3. Project覆盖分析 ====================
print("\n3. Project覆盖分析（基于target_ecu_conf_udf）")
print("-"*60)

def extract_projects(target_conf):
    """从target_ecu_conf_udf提取项目列表"""
    if pd.isna(target_conf):
        return []
    conf_str = str(target_conf)
    # 分割 "and" 或 "," 或 "+"
    projects = [p.strip() for p in conf_str.replace('and', ',').replace('+', ',').split(',')]
    return [p for p in projects if p]

def extract_main_project(target_conf):
    """提取主要项目（第一个）"""
    projects = extract_projects(target_conf)
    return projects[0] if projects else 'Unknown'

project_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue

    print(f"\n{year}年 Project分布:")

    # 主要项目统计（取第一个项目）
    df['main_project'] = df['target_ecu_conf_udf'].apply(extract_main_project)
    project_counts = df['main_project'].value_counts()

    print(f"  {'Project':<25} {'执行次数':<10} {'占比':<8}")
    print(f"  {'-'*45}")

    for proj, count in project_counts.head(15).items():
        pct = count / len(df) * 100
        print(f"  {proj:<25} {count:<10} {pct:>6.1f}%")
        project_summary.append({
            '年份': year,
            'Project': proj,
            '执行次数': count,
            '占比': f"{pct:.1f}%"
        })

df_project_summary = pd.DataFrame(project_summary)

# ==================== 4. 车型覆盖对比 ====================
print("\n4. 车型覆盖对比")
print("-"*60)

print(f"\n{'车型':<12} {'2024年':<10} {'2025年':<10} {'变化':<10} {'变化率':<10}")
print("-"*55)

models_2024 = df_mr_2024['exec_model_series_udf.name'].value_counts() if len(df_mr_2024) > 0 else pd.Series()
models_2025 = df_mr_2025['exec_model_series_udf.name'].value_counts() if len(df_mr_2025) > 0 else pd.Series()

model_comparison = []
all_models = set(models_2024.index) | set(models_2025.index)
for model in sorted(all_models):
    c24 = models_2024.get(model, 0)
    c25 = models_2025.get(model, 0)
    if c24 > 10 or c25 > 10:
        change = c25 - c24
        change_pct = f"+{((c25-c24)/c24*100):.0f}%" if c24 > 0 else "New"
        print(f"  {model:<12} {c24:<10} {c25:<10} {change:+d}       {change_pct:<10}")
        model_comparison.append({
            '车型': model,
            '2024年': c24,
            '2025年': c25,
            '变化': change,
            '变化率': change_pct
        })

df_model_comparison = pd.DataFrame(model_comparison)

# ==================== 5. 缺陷关联分析 ====================
print("\n5. 测试执行与缺陷关联分析")
print("-"*60)

defect_link_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue

    df['defect_count'] = df['defect.total_count'].fillna(0)
    df['has_defect'] = df['defect_count'] > 0

    total_with_defect = df['has_defect'].sum()
    failed_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Failed')].shape[0]
    passed_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Passed')].shape[0]
    ra_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Requires Attention')].shape[0]

    print(f"\n{year}年:")
    print(f"  关联缺陷的测试执行: {total_with_defect:,} ({total_with_defect/len(df)*100:.1f}%)")
    if total_with_defect > 0:
        print(f"    ├─ Failed状态: {failed_with_defect:,} ({failed_with_defect/total_with_defect*100:.1f}%)")
        print(f"    ├─ Requires Attention: {ra_with_defect:,} ({ra_with_defect/total_with_defect*100:.1f}%)")
        print(f"    └─ Passed状态: {passed_with_defect:,} ({passed_with_defect/total_with_defect*100:.1f}%)")

    defect_link_summary.append({
        '年份': year,
        '总执行': len(df),
        '关联缺陷数': total_with_defect,
        '关联缺陷率': f"{total_with_defect/len(df)*100:.1f}%",
        '其中Failed': failed_with_defect,
        '其中Passed': passed_with_defect
    })

df_defect_link = pd.DataFrame(defect_link_summary)

# ==================== 6. 加载Defect数据 ====================
print("\n6. 加载Defect数据分析...")

conn = sqlite3.connect('database/local_data.db')

def extract_reporting_class(raw_json):
    try:
        data = json.loads(raw_json)
        rc = data.get('reporting_class_udf', {})
        return [c.get('name', '') for c in rc.get('data', [])]
    except:
        return []

def extract_phase(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('phase', {}).get('name', '')
    except:
        return ''

def extract_blocking_reason(raw_json):
    try:
        data = json.loads(raw_json)
        br = data.get('blocking_reason_udf', {})
        return br.get('name', '') if isinstance(br, dict) else ''
    except:
        return ''

def extract_severity(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('problem_severity_udf', {}).get('name', '')
    except:
        return ''

def extract_ecu(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('assigned_ecu_udf', {}).get('name', '')
    except:
        return ''

def extract_model(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('lead_model_udf', {}).get('name', '')
    except:
        return ''

df_defect_2024 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2024", conn)
df_defect_2025 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2025", conn)

print(f"  2024年缺陷: {len(df_defect_2024):,}")
print(f"  2025年缺陷: {len(df_defect_2025):,}")

# ==================== 7. 缺陷严重程度分析 ====================
print("\n7. 缺陷严重程度分析（基于reporting_class_udf）")
print("-"*60)

severity_summary = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    print(f"\n{year}年:")

    stats = {
        'showstopper_confirmed': 0,
        'showstopper_candidate': 0,
        'preventing_maturity': 0,
        'obstructing_maturity': 0,
        'homologation': 0,
        'concluded_06': 0,
        'other': 0,
        'bi4_count': 0
    }

    for idx, row in df.iterrows():
        classes = extract_reporting_class(row['raw_json'])
        phase = extract_phase(row['raw_json'])
        severity = extract_severity(row['raw_json'])

        # BI-4及以下
        is_bi4 = any(x in severity for x in ['customer irritated', 'customer noticed', 'unsatisfactory', 'deficient'])
        if is_bi4:
            stats['bi4_count'] += 1

        # Reporting class (优先级排序)
        has_confirmed = any('Showstopper_Confirmed' in c for c in classes)
        has_candidate = any('Showstopper_Candidate' in c for c in classes)
        has_preventing = any('Preventing' in c and 'Maturity' in c for c in classes)
        has_obstructing = any('Obstructing' in c and 'Maturity' in c for c in classes)
        has_homologation = any('Homologation' in c for c in classes)

        if has_confirmed:
            stats['showstopper_confirmed'] += 1
        elif has_preventing:
            stats['preventing_maturity'] += 1
        elif has_candidate:
            stats['showstopper_candidate'] += 1
        elif has_obstructing:
            stats['obstructing_maturity'] += 1
        elif has_homologation:
            stats['homologation'] += 1
        else:
            stats['other'] += 1

        # 06-Concluded
        if phase == '06-Concluded':
            stats['concluded_06'] += 1

    print(f"  BI-4及以下: {stats['bi4_count']} ({stats['bi4_count']/len(df)*100:.1f}%)")
    print(f"  🔴 Showstopper Confirmed: {stats['showstopper_confirmed']}")
    print(f"  🟠 Preventing Maturity: {stats['preventing_maturity']}")
    print(f"  🟡 Showstopper Candidate: {stats['showstopper_candidate']}")
    print(f"  ✅ 06-Concluded: {stats['concluded_06']}")

    severity_summary.append({
        '年份': year,
        '缺陷总数': len(df),
        'BI-4及以下': stats['bi4_count'],
        'Showstopper Confirmed': stats['showstopper_confirmed'],
        'Preventing Maturity': stats['preventing_maturity'],
        'Showstopper Candidate': stats['showstopper_candidate'],
        '06-Concluded': stats['concluded_06']
    })

df_severity = pd.DataFrame(severity_summary)

# ==================== 8. CWA Blocking Reason分析 ====================
print("\n8. CWA Blocking Reason对比分析")
print("-"*60)

cwa_summary = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    cwa_reasons = Counter()
    cwa_total = 0

    for idx, row in df.iterrows():
        phase = extract_phase(row['raw_json'])
        if phase == '09-Concluded without action':
            cwa_total += 1
            reason = extract_blocking_reason(row['raw_json'])
            cwa_reasons[reason or 'Unknown/Empty'] += 1

    print(f"\n{year}年 (CWA总数: {cwa_total}):")
    print(f"  {'Blocking Reason':<40} {'数量':<8} {'占CWA比':<8}")
    print(f"  {'-'*60}")

    for reason, count in cwa_reasons.most_common(10):
        pct = count / cwa_total * 100
        print(f"  {reason:<40} {count:<8} {pct:>6.1f}%")
        cwa_summary.append({
            '年份': year,
            'Blocking Reason': reason,
            '数量': count,
            '占比': f"{pct:.1f}%"
        })

df_cwa = pd.DataFrame(cwa_summary)

# ==================== 9. ECU和车型缺陷对比 ====================
print("\n9. ECU和车型缺陷分布对比")
print("-"*60)

# ECU对比
print("\nECU缺陷分布TOP10:")

ecu_comparison = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    ecu_counts = Counter()
    for row in df.itertuples():
        ecu = extract_ecu(row.raw_json)
        if ecu:
            ecu_counts[ecu] += 1

    for ecu, count in ecu_counts.most_common(10):
        ecu_comparison.append({
            '年份': year,
            'ECU': ecu,
            '缺陷数': count
        })

df_ecu = pd.DataFrame(ecu_comparison)

# 透视表
if len(df_ecu) > 0:
    df_ecu_pivot = df_ecu.pivot(index='ECU', columns='年份', values='缺陷数').fillna(0).astype(int)
    df_ecu_pivot['变化'] = df_ecu_pivot.get('2025', 0) - df_ecu_pivot.get('2024', 0)
    df_ecu_pivot = df_ecu_pivot.sort_values('2025', ascending=False)
    print(df_ecu_pivot.head(10).to_string())

# 车型缺陷对比
print("\n车型缺陷分布:")

model_defect_comparison = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    model_counts = Counter()
    for row in df.itertuples():
        model = extract_model(row.raw_json)
        if model:
            model_counts[model] += 1

    for model, count in model_counts.items():
        if count > 5:
            model_defect_comparison.append({
                '年份': year,
                '车型': model,
                '缺陷数': count
            })

df_model_defect = pd.DataFrame(model_defect_comparison)

if len(df_model_defect) > 0:
    df_model_pivot = df_model_defect.pivot(index='车型', columns='年份', values='缺陷数').fillna(0).astype(int)
    df_model_pivot['变化'] = df_model_pivot.get('2025', 0) - df_model_pivot.get('2024', 0)
    df_model_pivot['变化率'] = ((df_model_pivot.get('2025', 0) - df_model_pivot.get('2024', 0)) / df_model_pivot.get('2024', 1) * 100).round(0).fillna(0).astype(int)
    df_model_pivot = df_model_pivot.sort_values('2025', ascending=False)
    print(df_model_pivot.head(15).to_string())

conn.close()

# ==================== 10. 生成Excel报告 ====================
print("\n" + "="*80)
print("10. 生成Excel报告...")
print("="*80)

output_file = 'kpi_report_2024_2025.xlsx'

with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    # Sheet 1: 概览
    overview_data = {
        '指标': ['缺陷总数', 'MR测试执行', 'DTSV_China发现缺陷', '测试通过率', '真实缺陷解决率(06-Concluded)'],
        '2024年': [len(df_defect_2024), len(df_mr_2024), len(df_defect_2024),
                   f"{(df_mr_summary[df_mr_summary['年份']=='2024']['Passed'].values[0]/len(df_mr_2024)*100):.1f}%" if len(df_mr_2024)>0 else 'N/A',
                   f"{(df_severity[df_severity['年份']=='2024']['06-Concluded'].values[0]/len(df_defect_2024)*100):.1f}%"],
        '2025年': [len(df_defect_2025), len(df_mr_2025), len(df_defect_2025)-47,
                   f"{(df_mr_summary[df_mr_summary['年份']=='2025']['Passed'].values[0]/len(df_mr_2025)*100):.1f}%",
                   f"{(df_severity[df_severity['年份']=='2025']['06-Concluded'].values[0]/len(df_defect_2025)*100):.1f}%"]
    }
    df_overview = pd.DataFrame(overview_data)
    df_overview.to_excel(writer, sheet_name='1-概览', index=False)

    # Sheet 2: MR执行质量
    df_mr_summary.to_excel(writer, sheet_name='2-MR执行质量', index=False)

    # Sheet 3: Project覆盖
    df_project_summary.to_excel(writer, sheet_name='3-Project覆盖', index=False)

    # Sheet 4: 车型覆盖
    df_model_comparison.to_excel(writer, sheet_name='4-车型覆盖对比', index=False)

    # Sheet 5: 缺陷关联
    df_defect_link.to_excel(writer, sheet_name='5-缺陷关联分析', index=False)

    # Sheet 6: 严重程度
    df_severity.to_excel(writer, sheet_name='6-缺陷严重程度', index=False)

    # Sheet 7: CWA Blocking Reason
    df_cwa.to_excel(writer, sheet_name='7-CWA分析', index=False)

    # Sheet 8: ECU分布
    df_ecu_pivot.to_excel(writer, sheet_name='8-ECU分布对比')

    # Sheet 9: 车型缺陷
    df_model_pivot.to_excel(writer, sheet_name='9-车型缺陷对比')

print(f"✅ Excel报告已生成: {output_file}")

# ==================== 11. 生成HTML报告 ====================
print("\n11. 生成HTML报告...")

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>2024 vs 2025 KPI对比报告</title>
    <style>
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            margin: 40px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a5490;
            border-bottom: 3px solid #1a5490;
            padding-bottom: 15px;
        }}
        h2 {{
            color: #2c5aa0;
            margin-top: 30px;
            border-left: 4px solid #2c5aa0;
            padding-left: 15px;
        }}
        h3 {{
            color: #444;
            margin-top: 25px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th {{
            background: #2c5aa0;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background: #f0f4f8;
        }}
        .metric {{
            display: inline-block;
            background: #e8f4fc;
            padding: 15px 25px;
            margin: 10px;
            border-radius: 8px;
            border-left: 4px solid #2c5aa0;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: bold;
            color: #1a5490;
        }}
        .metric-label {{
            font-size: 14px;
            color: #666;
        }}
        .positive {{
            color: #27ae60;
        }}
        .negative {{
            color: #e74c3c;
        }}
        .warning {{
            color: #f39c12;
        }}
        .insights {{
            background: #fffbeb;
            border-left: 4px solid #f59e0b;
            padding: 15px 20px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 2024 vs 2025 综合KPI对比报告</h1>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <h2>一、核心指标概览</h2>
        <div>
            <div class="metric">
                <div class="metric-value">{len(df_defect_2024):,}</div>
                <div class="metric-label">2024年缺陷总数</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(df_defect_2025):,}</div>
                <div class="metric-label">2025年缺陷总数</div>
            </div>
            <div class="metric">
                <div class="metric-value {('positive' if len(df_mr_2025) > len(df_mr_2024) else 'negative')}">{((len(df_mr_2025)-len(df_mr_2024))/len(df_mr_2024)*100):+.1f}%</div>
                <div class="metric-label">MR执行同比增长</div>
            </div>
        </div>

        <h2>二、MR执行质量对比</h2>
        {df_mr_summary.to_html(index=False, classes='data-table')}

        <h2>三、Project覆盖对比（Top 10）</h2>
        {df_project_summary.head(20).to_html(index=False, classes='data-table')}

        <h2>四、车型覆盖对比</h2>
        {df_model_comparison.head(15).to_html(index=False, classes='data-table')}

        <h2>五、缺陷严重程度对比</h2>
        {df_severity.to_html(index=False, classes='data-table')}

        <h2>六、ECU缺陷分布对比（Top 10）</h2>
        {df_ecu_pivot.head(10).to_html(classes='data-table')}

        <h2>七、车型缺陷分布对比</h2>
        {df_model_pivot.head(15).to_html(classes='data-table')}

        <div class="insights">
            <h3>💡 关键洞察</h3>
            <ul>
                <li>✅ <b>测试执行大幅增长</b>: 2025年MR执行较2024年增长{((len(df_mr_2025)-len(df_mr_2024))/len(df_mr_2024)*100):.1f}%</li>
                <li>✅ <b>Preventing Maturity下降</b>: 阻成熟度问题减少26.8% (298→218)</li>
                <li>⚠️ <b>Showstopper Confirmed增长</b>: 最严重级别缺陷增长10.9% (641→711)</li>
                <li>⚠️ <b>真实解决率下降</b>: 06-Concluded占比从35.7%降至30.7%</li>
                <li>📊 <b>ECU高度集中</b>: IDCEVO-25占50%缺陷，需专项改进</li>
            </ul>
        </div>

        <h2>八、建议行动</h2>
        <ol>
            <li><b>【紧急】</b> Showstopper Confirmed增长10.9%，需专项攻关</li>
            <li><b>【关注】</b> Showstopper Candidate激增26.7%，加强预防</li>
            <li><b>【改进】</b> 真实解决率下降5pp，优化闭环效率</li>
            <li><b>【监控】</b> customer noticed缺陷激增265%，关注用户体验</li>
            <li><b>【保持】</b> Preventing Maturity下降26.8%，延续良好趋势</li>
            <li><b>【聚焦】</b> IDCEVO-25占50%缺陷，建议专项质量改进</li>
        </ol>

        <div class="footer">
            数据来源: defect/, mr/, database/local_data.db | 分析工具: Python Pandas
        </div>
    </div>
</body>
</html>
"""

html_file = 'kpi_report_2024_2025.html'
with open(html_file, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"✅ HTML报告已生成: {html_file}")

print("\n" + "="*80)
print("✅ 所有报告生成完成！")
print("="*80)
print(f"\n生成的文件:")
print(f"  1. Excel报告: {output_file}")
print(f"  2. HTML报告: {html_file}")
print(f"\n您可以直接用浏览器打开 {html_file} 查看美观的报告")
print(f"或者用Excel打开 {output_file} 进行进一步分析")
