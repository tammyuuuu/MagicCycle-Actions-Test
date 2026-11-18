"""Build report-backed research records, keeping reviewed summaries tied to source hashes."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('research_monitor')


def collect(snapshot=False):
    definitions = json.loads((ROOT / 'projects.json').read_text(encoding='utf8'))
    projects = []
    for definition in definitions:
        project = dict(definition)
        reports = []
        sources = set()
        changed = False
        for number, original in enumerate(project['reports']):
            source = Path(original)
            saved = ROOT / 'reports' / f'{project["id"]}-{number}.md'
            if snapshot and source.exists():
                saved.parent.mkdir(exist_ok=True)
                saved.write_bytes(source.read_bytes())
            available = source if source.exists() else saved
            if not available.exists():
                raise ValueError(f'Missing report for {project["title"]}: {original}')
            content = available.read_text(encoding='utf8')
            digest = hashlib.sha256(available.read_bytes()).hexdigest()
            reviewed = hashlib.sha256(saved.read_bytes()).hexdigest()
            changed = changed or digest != reviewed
            reports.append({'original': original, 'snapshot': saved.as_posix(), 'sha256': digest,
                            'title': content.splitlines()[0].lstrip('# ').strip(), 'content': content})
            sources.update(re.findall(r'https?://[^\s<>）]+', content))
        # Only complete, explicit links from the reports become source links.
        sources = sorted({s.split(')')[0].rstrip('。，；;、') for s in sources})
        project.update(reports=reports, sources=sources, source_changed=changed)
        state_files = [Path(folder) / 'research_status.json' for folder in project['folders']]
        for state_file in state_files:
            if state_file.exists():
                state = json.loads(state_file.read_text(encoding='utf8'))
                project['status'] = {'running': '研究中', 'completed': '阶段完成', 'waiting': '等待验证', 'blocked': '受阻'}.get(state.get('status'), project['status'])
                project['progress'] = state.get('reason', project['progress'])
                project['next_action'] = state.get('next_action', project['next_action'])
        if changed:
            project.update(status='待复核', progress='原始报告已更新，以下摘要对应上次已复核版本。',
                           next_action='对照更新后的原始报告，复核结论与研究状态。', focus=True)
        date_matches = re.findall(r'202\d[-—]\d{2}[-—]\d{2}|202\d年\d{1,2}月\d{1,2}日', reports[0]['content'][:2000])
        filename_date = re.search(r'(202\d)(\d{2})(\d{2})', reports[0]['original'])
        project['report_date'] = date_matches[0] if date_matches else ('-'.join(filename_date.groups()) if filename_date else '日期见报告')
        projects.append(project)
    return projects


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot-reviewed', action='store_true')
    projects = collect(parser.parse_args().snapshot_reviewed)
    (ROOT / 'catalog.json').write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding='utf8')
    print(f'Indexed {len(projects)} report-backed studies')
