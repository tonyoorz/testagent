import json
import importlib.util

spec = importlib.util.spec_from_file_location('td_mod', 'download/testcase_downloader.py')
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)

s = td.get_authenticated_session('cookie', None, 'cookie.txt')
query = '"(subtype IN \'defect\',\'feature\',\'story\';run_covered_content_relation={id IN \'19261830\',\'2491711\'})"'
fields = ['id','name','subtype','parent{id,name,subtype}','run_covered_content_relation{id}']
res = td.fetch_octane_data(s, td.EP_WORK_ITEMS, fields, query, limit_per_page=100, order_by='id')
print('COUNT', len(res))
print('FIRST', json.dumps(res[0], ensure_ascii=False)[:1200] if res else 'NONE')
