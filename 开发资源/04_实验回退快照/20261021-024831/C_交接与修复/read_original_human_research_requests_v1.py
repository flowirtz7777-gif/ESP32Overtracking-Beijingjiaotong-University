"""Read-only retrieval of human research requests, excluding recurring heartbeat replays."""
import json
import re
from pathlib import Path
SOURCE=Path(r'C:\Users\Admin\.codex\sessions\2026\06\13\rollout-2026-06-13T13-07-15-019ebf60-7584-7591-980b-75cc8eea8471.jsonl')
DEST=Path(__file__).resolve().parent/'original_human_research_requests.readonly_extract.json'
keywords=re.compile(r'计划|规划|S[1-5]|M[12]|实验|目标|阈值|对照|基线|报告|纠错|真实|贝叶斯|机器学习|敏感性')
requests=[]
users=0
with SOURCE.open('r',encoding='utf-8') as stream:
    for number,line in enumerate(stream,1):
        try: item=json.loads(line)
        except json.JSONDecodeError: continue
        payload=item.get('payload',{})
        if item.get('type')!='response_item' or payload.get('type')!='message' or payload.get('role')!='user': continue
        text='\n'.join(piece.get('text','') for piece in payload.get('content',[]) if isinstance(piece,dict))
        if '<heartbeat>' in text or '# AGENTS.md instructions' in text or '<environment_context>' in text: continue
        users+=1
        if not keywords.search(text): continue
        requests.append(dict(source_line=number,time=item.get('timestamp'),text=text))
DEST.write_text(json.dumps(dict(source=str(SOURCE),read_only_history_access=True,
    scientific_files_or_automation_modified=False,human_messages=users,matching_requests=requests),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(human_messages=users,relevant_requests=len(requests),saved_to=str(DEST)),ensure_ascii=False))
for i,record in enumerate(requests):
    message=record['text'].replace('\n',' ')
    print(f"[{i}] line={record['source_line']} time={record['time']} {message[:650]}")
