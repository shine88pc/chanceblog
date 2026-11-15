# -*- coding: utf-8 -*-
"""알림 워크플로(ai-request.yml)가 주어진 R 번호 커밋에 대해 끝났는지 웹 페이지로 확인(api 호출 0회). 사용: python check_notify.py R-211"""
import re, sys, time, importlib.util
spec = importlib.util.spec_from_file_location('vp', 'C:/work/ai/scratch/verify_pause.py')
vp = importlib.util.module_from_spec(spec); spec.loader.exec_module(vp)
tag = sys.argv[1]
deadline = time.time() + 110
last = None
while time.time() < deadline:
    page = vp.fetch(f"{vp.BASE}/actions/workflows/ai-request.yml")
    for m in re.finditer(r'"runNumber":(\d+),"id":"(\d+)"', page):
        seg = page[m.start(): m.start() + 1500]
        title = re.search(r'"title":"([^"]*)"', seg)
        if title and tag in title.group(1):
            status = re.search(r'"status":"([A-Z_]+)"', seg).group(1)
            concl = re.search(r'"conclusion":"([A-Z_]+)"', seg)
            dur = re.search(r'"timing":\{"kind":"[A-Z_]+","text":"([^"]*)"', seg)
            last = (m.group(2), status, concl.group(1) if concl else None, dur.group(1) if dur else '', m.group(1))
            break
    if last and last[1] == 'WORKFLOW_RUN_STATUS_COMPLETED':
        ann = vp.annotations(last[0])
        print('run #%s %s %s %s | annotations: %s' % (last[4], last[1].replace('WORKFLOW_RUN_STATUS_', ''), (last[2] or '').replace('WORKFLOW_RUN_CONCLUSION_', ''), last[3], ann[:160]))
        break
    time.sleep(8)
else:
    print('아직 끝나지 않음:', last)
