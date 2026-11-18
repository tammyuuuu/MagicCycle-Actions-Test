import json
import re
from pathlib import Path
from datetime import datetime, timezone


def collect():
    projects = []
    for root in ('stock_research', 'tenbagger_research', 'investor_holdings_research'):
        for folder in sorted(Path(root).glob('*/')):
            if folder.name.startswith(('vendor', '__', '.', 'cloud_results')):
                continue
            files = [p for p in folder.glob('*') if p.is_file()]
            if not files:
                continue
            state_file = folder / 'research_status.json'
            state = json.loads(state_file.read_text(encoding='utf8')) if state_file.exists() else {}
            status = {'running': '运行中', 'completed': '已完成', 'waiting': '待验证'}.get(state.get('status'), '待验证')
            if not state and any(p.name in ('audit.json', 'verification.json') for p in files) and any(p.name in ('results.csv', 'summary.json') for p in files):
                status = '已完成'
                state['reason'] = '已有结果和审计产物，研究批次已产出；结论有效性见审计'
            sources = set()
            for p in files:
                if p.suffix in ('.json', '.md', '.py') and p.stat().st_size < 500000:
                    sources.update(re.findall(r'https?://[^\s"<>\)]+', p.read_text(encoding='utf8', errors='replace')))
            projects.append({'title': folder.name, 'path': folder.as_posix(), 'status': status,
                             'reason': state.get('reason', '已发现研究产物，待核验完成条件'),
                             'files': len(files), 'sources': sorted(sources)[:10],
                             'artifacts': [p.as_posix() for p in files if p.suffix in ('.md', '.json', '.csv')][:12],
                             'updated_at': datetime.fromtimestamp(max(p.stat().st_mtime for p in files), timezone.utc).isoformat()})
    return projects


if __name__ == '__main__':
    Path('research_monitor/catalog.json').write_text(json.dumps(collect(), ensure_ascii=False, indent=2), encoding='utf8')
