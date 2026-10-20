"""Retrieve selected original final answers around human planning changes; no research data reads."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'original_human_research_requests.readonly_extract.json').read_text(encoding='utf-8'))
selected={9,12,13,14,26,27,30,34,35,36,37}
targets={data['matching_requests'][i]['source_line']:i for i in selected}
pending=None
answers=[]
with Path(data['source']).open('r',encoding='utf-8') as stream:
    for number,line in enumerate(stream,1):
        if number in targets: pending=targets[number]
        if pending is None: continue
        try: item=json.loads(line)
        except json.JSONDecodeError: continue
        p=item.get('payload',{})
        if item.get('type')=='response_item' and p.get('type')=='message' and p.get('role')=='assistant' and (p.get('channel')=='final' or p.get('phase')=='final_answer'):
            content='\n'.join(c.get('text','') for c in p.get('content',[]) if isinstance(c,dict))
            if content:
                answers.append(dict(request_index=pending,line=number,time=item.get('timestamp'),text=content))
                pending=None
(HERE/'original_selected_planning_answers.readonly_extract.json').write_text(json.dumps(answers,ensure_ascii=False,indent=2),encoding='utf-8')
for item in answers:
    print(f"REQUEST[{item['request_index']}] ANSWER line={item['line']} time={item['time']} chars={len(item['text'])}\n{item['text'][:3800]}\n")

