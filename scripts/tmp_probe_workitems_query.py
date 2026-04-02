import json
import importlib.util

spec = importlib.util.spec_from_file_location('td_mod', 'download/testcase_downloader.py')
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)

s = td.get_authenticated_session('cookie', None, 'cookie.txt')
if not s:
    print('AUTH_FAIL')
    raise SystemExit(1)

query = '"(subtype IN \'defect\',\'feature\',\'story\';run_covered_content_relation={id IN \'19261830\',\'2491711\'})"'
res = td.fetch_octane_data(s, td.EP_WORK_ITEMS, ['id','name','subtype','parent{id,name,subtype}'], query, limit_per_page=200, order_by='id')
print('COUNT', len(res))
print('SAMPLE', json.dumps(res[:3], ensure_ascii=False)[:800])
