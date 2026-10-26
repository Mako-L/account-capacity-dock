#!/usr/bin/env python3
"""Live view of running coding agents: what each works on, its steps and its subagents.

Sources, cheapest first:
- Herdr's agent list: every agent pane, its status and terminal title.
- Claude Code: ~/.claude/sessions/<pid>.json ties a process to its transcript; the transcript
  holds the current tool calls, the task list and the subagents.
- Codex: the rollout file the codex process has open, with its plan and tool calls.
- Reports an agent writes itself with `mako-capacity agents report "step" --done 2 --total 5`.
- An optional observer: a small model that reads the latest transcript events of a working
  agent and names its task and steps, when the agent keeps no task list itself.
Nothing here changes an agent; it only reads files, ps output and Herdr's socket.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

from platform_paths import cache_dir

HOME = Path.home()
CLAUDE = Path(os.environ.get('CLAUDE_CONFIG_DIR', HOME / '.claude'))
CODEX = Path(os.environ.get('CODEX_HOME', HOME / '.codex'))
SNAPSHOT = cache_dir() / 'agents.json'
TAIL = 1_500_000  # bytes read from the end of a transcript; long sessions grow past 50 MB
RUNNING = 45      # seconds since a subagent's last write while it still counts as running
RECENT = 15 * 60  # finished subagents stay listed this long
SUB_RECENT = 6 * 3600  # finished subagents of a live session stay in its tree this long
SUB_LIMIT = 30     # newest top-level subagents kept per agent
SUB_TAIL = 200_000  # bytes read from the end of a subagent transcript


def setup_dir():
    return Path(os.environ.get('MAKO_CAPACITY_HOME', HOME / '.mako-capacity'))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def setting(key, default=''):
    return os.environ.get(key) or read_json(setup_dir() / 'settings.json').get(key) or default


def clip(text, size=90):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= size else text[:size - 1].rstrip() + '…'


def tail_events(path, size=TAIL):
    """The JSON lines at the end of a file, oldest first."""
    try:
        with open(path, 'rb') as handle:
            length = handle.seek(0, 2)
            handle.seek(max(0, length - size))
            if length > size:
                handle.readline()
            data = handle.read()
    except OSError:
        return []
    events = []
    for line in data.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


# ---- Processes and panes ----------------------------------------------------

def herdr_agents():
    if not os.environ.get('HERDR_SOCKET_PATH') and not shutil.which('herdr'):
        return []
    try:
        out = subprocess.run(['herdr', 'agent', 'list'], capture_output=True, text=True, timeout=5).stdout
        return json.loads(out)['result']['agents']
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return []


def pane_of(pids):
    """HERDR_PANE_ID from each process's environment."""
    pids = [str(p) for p in pids]
    if not pids:
        return {}
    found = {}
    if sys.platform.startswith('linux'):
        for pid in pids:
            try:
                env = Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
            except OSError:
                continue
            for item in env:
                if item.startswith(b'HERDR_PANE_ID='):
                    found[int(pid)] = item.split(b'=', 1)[1].decode()
        return found
    try:
        out = subprocess.run(['ps', 'eww', '-o', 'pid=,command=', '-p', ','.join(pids)],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    for line in out.splitlines():
        match = re.search(r'\sHERDR_PANE_ID=(\S+)', line)
        if match:
            found[int(line.split()[0])] = match.group(1)
    return found


def codex_processes():
    try:
        out = subprocess.run(['pgrep', '-x', 'codex'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(line) for line in out.split()]


def open_rollout(pid):
    try:
        out = subprocess.run(['lsof', '-p', str(pid), '-Fn'], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    files = [line[1:] for line in out.splitlines() if line.startswith('n') and '/rollout-' in line and line.endswith('.jsonl')]
    return files[-1] if files else None


def latest_rollout(cwd):
    """The newest Codex rollout started in this folder, for a Codex that has no file open."""
    files = sorted((CODEX / 'sessions').glob('*/*/*/rollout-*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:30]:
        try:
            with open(path) as handle:
                meta = json.loads(handle.readline()).get('payload', {})
        except (OSError, ValueError):
            continue
        if meta.get('cwd') == cwd:
            return str(path)
    return None


# ---- Claude Code ------------------------------------------------------------

def tool_step(name, data):
    """One short line for a tool call, like a person would say it."""
    data = data if isinstance(data, dict) else {}
    base = lambda key: Path(str(data.get(key, ''))).name
    if name == 'Bash':
        return clip(data.get('description') or data.get('command'), 70)
    if name in ('Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        return f'{ {"MultiEdit": "Edit"}.get(name, name)} {base("file_path") or base("notebook_path")}'.strip()
    if name in ('Grep', 'Glob'):
        return clip(f'Search {data.get("pattern", "")}', 70)
    if name in ('Agent', 'Task'):
        return clip(f'Subagent: {data.get("description") or data.get("name") or ""}', 70)
    if name == 'Skill':
        return f'Skill {data.get("skill", "")}'
    if name == 'WebFetch':
        return clip(f'Fetch {data.get("url", "")}', 70)
    if name == 'WebSearch':
        return clip(f'Search the web: {data.get("query", "")}', 70)
    if name.startswith('mcp__'):
        return name.split('__')[-1].replace('_', ' ').capitalize()
    return name


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text')
    return ''


def stamp(event):
    value = event.get('timestamp')
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def workflow_meta(script):
    """The name, description and phase titles from a workflow script's meta block."""
    head = script[:4000]
    pick = lambda key: (re.search(key + r"\s*:\s*(['\"`])(.*?)\1", head, re.S) or [None, None, None])[2]
    phases = re.search(r'phases\s*:\s*\[(.*?)\]\s*,?\s*\}', head, re.S)
    titles = re.findall(r"title\s*:\s*(['\"`])(.*?)\1", phases.group(1)) if phases else []
    return {'name': pick('name'), 'description': clip(pick('description'), 90), 'phases': [t[1] for t in titles][:12]}


def read_claude(events):
    """Task, steps, current tool calls and recent activity from Claude Code transcript events."""
    found = {'title': None, 'prompt': None, 'todos': None, 'pending': {}, 'activity': [], 'last_text': None, 'workflows': {}}
    tasks, launches = {}, {}
    for event in events:
        kind = event.get('type')
        if kind == 'ai-title':
            found['title'] = event.get('aiTitle')
        message = event.get('message') or {}
        content = message.get('content')
        if kind == 'user' and not event.get('isSidechain'):
            words = text_of(content).strip()
            if words and not event.get('isMeta') and not words.startswith(('<', 'Another Claude session', 'Stop hook feedback', '[Request interrupted', 'Caveat:')):
                found['prompt'] = clip(words, 160)
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    call = found['pending'].pop(block.get('tool_use_id'), None)
                    result = event.get('toolUseResult')
                    run = re.search(r'workflows/(wf_[0-9a-f-]+)', text_of(block.get('content')))
                    if run and block.get('tool_use_id') in launches:
                        found['workflows'][run.group(1)] = launches[block['tool_use_id']]
                    if call and call[0] == 'TaskCreate' and isinstance(result, dict) and result.get('task'):
                        tasks[str(result['task'].get('id'))] = {'title': call[1].get('subject'), 'active': call[1].get('activeForm'), 'status': 'pending'}
        if kind != 'assistant' or not isinstance(content, list):
            continue
        at = stamp(event)
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'text' and block.get('text', '').strip():
                found['last_text'] = clip(block['text'], 160)
                found['activity'].append({'at': at, 'text': clip(block['text'], 90), 'kind': 'say'})
            if block.get('type') != 'tool_use':
                continue
            name, data = block.get('name', ''), block.get('input') or {}
            found['pending'][block.get('id')] = (name, data, at)
            found['activity'].append({'at': at, 'text': tool_step(name, data), 'kind': 'tool'})
            if name == 'Workflow' and isinstance(data.get('script'), str):
                launches[block.get('id')] = workflow_meta(data['script'])
            if name == 'TodoWrite' and isinstance(data.get('todos'), list):
                found['todos'] = [{'title': t.get('content'), 'active': t.get('activeForm'), 'status': t.get('status')} for t in data['todos']]
            if name == 'TaskUpdate' and str(data.get('taskId')) in tasks:
                task = tasks[str(data['taskId'])]
                task['status'] = data.get('status') or task['status']
                task['title'] = data.get('subject') or task['title']
    if tasks and not found['todos']:
        found['todos'] = [t for t in tasks.values() if t['status'] != 'deleted']
    found['activity'] = found['activity'][-8:]
    return found


def task_files(session):
    """Claude's own task list, kept in ~/.claude/tasks/<session or team>/<id>.json."""
    items = []
    for folder in (CLAUDE / 'tasks' / session, CLAUDE / 'tasks' / f'session-{session[:8]}'):
        for path in sorted(folder.glob('*.json'), key=lambda p: (len(p.stem), p.stem)):
            task = read_json(path)
            if task.get('subject') and task.get('status') != 'deleted':
                items.append({'title': task['subject'], 'active': task.get('activeForm'), 'status': task.get('status'), 'owner': task.get('owner')})
    return items


def started_at(path, stat):
    return getattr(stat, 'st_birthtime', None) or stat.st_ctime


def as_steps(todos):
    return [{'title': clip(t.get('active') if t.get('status') == 'in_progress' and t.get('active') else t.get('title'), 70),
             'status': {'completed': 'done', 'in_progress': 'active'}.get(t.get('status'), t.get('status') if t.get('status') in ('done', 'active') else 'pending')}
            for t in todos or [] if t.get('title')]


def with_progress(item, steps, guess=None):
    """Steps and progress for a subagent. A finished one has every step done and shows 100%."""
    if not item['running']:
        steps = [dict(step, status='done') for step in steps]
    item['steps'] = steps
    if not item['running']:
        item['progress'] = 100
    elif steps:
        item['progress'] = round(100 * sum(step['status'] == 'done' for step in steps) / len(steps))
    else:
        item['progress'] = guess
    return item


def workflow_node(folder, children, finished, journal, meta):
    """One node per workflow run. Its steps are the phases, from the script's meta block or the journal."""
    phases = list(meta.get('phases') or [])
    for event in journal:
        if event.get('type') == 'started' and event.get('phase') and event['phase'] not in phases:
            phases.append(event['phase'])
    started = {}
    for event in journal:
        if event.get('type') == 'started' and event.get('agentId'):
            started.setdefault(event.get('phase') or '', []).append('agent-' + event['agentId'])
    running = any(c['running'] for c in children)
    steps, score = [], 0.0
    for phase in phases:
        ids = started.get(phase, [])
        done = sum(i in finished for i in ids)
        if not ids:
            status = 'pending'
        elif done == len(ids) and not any(c['running'] and c.get('phase') == phase for c in children):
            status, score = 'done', score + 1
        else:
            status, score = 'active', score + done / len(ids)
        steps.append({'title': clip(phase, 60), 'status': status})
    total = sum(len(ids) for ids in started.values())
    count = f'{len(finished)} of {total} agents done' if total else f'{len(children)} agents'
    return {
        'id': folder.name, 'name': meta.get('name') or 'Workflow', 'kind': 'workflow',
        'description': meta.get('description') or count, 'summary': count, 'model': '',
        'running': running, 'step': next((c['step'] for c in children if c['running']), None), 'said': None,
        'activity': [], 'updated': max(c['updated'] for c in children), 'started': children[0]['started'],
        'children': children, 'steps': steps,
        'progress': round(100 * score / len(phases)) if phases else (round(100 * len(finished) / total) if total else None),
    }


def subagent_tree(transcript, now, parse, workflows=None, observed=None, watch=None):
    """Every subagent of a session as a tree, oldest first so the order never moves.

    Nested subagents name their parent in the meta file. Workflow agents sit under one node per run,
    grouped by phase. Each transcript is parsed once per change, so a finished subagent costs one stat call.
    Running subagents without a task list go into `watch` for the observer."""
    root = Path(transcript[:-len('.jsonl')]) / 'subagents'
    if not root.is_dir():
        return []
    nodes, parents = {}, {}

    def node(path, label=None, phase=None, finished=False, keep=False):
        try:
            # A workflow keeps all its agents, so its card counts every phase.
            if not keep and now - path.stat().st_mtime > SUB_RECENT:
                return None
        except OSError:
            return None
        found, changed = parse(str(path), read_claude, SUB_TAIL)
        if found is None:
            return None
        meta = read_json(path.with_name(path.stem + '.meta.json'))
        running = now - changed < RUNNING and not finished
        pending = found.get('pending') or []
        activity = found.get('activity') or []
        item = {
            'id': path.stem, 'name': label or meta.get('name') or meta.get('agentType') or 'Subagent',
            'description': clip(meta.get('description') or found.get('title'), 80),
            'model': (meta.get('model') or '').replace('[1m]', '').replace('inherit', ''),
            'running': running, 'step': (pending[-1] if pending else None) if running else None,
            'said': found.get('last_text'), 'activity': activity[-4:], 'updated': changed,
            'started': started_at(path, os.stat(path)), 'children': [], 'kind': 'agent', 'phase': phase,
        }
        steps = as_steps(found.get('todos'))
        if steps:
            return with_progress(item, steps)
        report = read_json(observed / f'sub-{path.stem}.json').get('result') if observed else None
        if running and watch is not None:
            watch.append((item, str(path), found))
        return with_progress(item, (report or {}).get('steps') or [], (report or {}).get('progress'))

    for path in root.glob('agent-*.jsonl'):
        item = node(path)
        if item:
            nodes[item['id']] = item
            parent = read_json(path.with_name(path.stem + '.meta.json')).get('parentAgentId')
            if parent:
                parents[item['id']] = 'agent-' + parent
    for folder in root.glob('workflows/wf_*'):
        try:
            if now - (folder / 'journal.jsonl').stat().st_mtime > SUB_RECENT and now - folder.stat().st_mtime > SUB_RECENT:
                continue
        except OSError:
            continue
        journal = tail_events(folder / 'journal.jsonl', 400_000)
        labels = {'agent-' + e['agentId']: (e.get('label'), e.get('phase')) for e in journal if e.get('type') == 'started' and e.get('agentId')}
        finished = {'agent-' + e['agentId'] for e in journal if e.get('type') == 'result' and e.get('agentId')}
        children = [c for c in (node(path, *labels.get(path.stem, (None, None)), finished=path.stem in finished, keep=True)
                                for path in folder.glob('agent-*.jsonl')) if c]
        if not children:
            continue
        children.sort(key=lambda c: c['started'])
        meta = (workflows or {}).get(folder.name)
        if not meta:
            # Claude Code keeps each run's script beside the session, named <workflow>-<run>.js.
            script = next(iter(root.parent.glob(f'workflows/scripts/*-{folder.name}.js')), None)
            try:
                meta = workflow_meta(script.read_text()[:4000]) if script else {}
            except OSError:
                meta = {}
            if workflows is not None and meta:
                workflows[folder.name] = meta
        nodes[folder.name] = workflow_node(folder, children, finished, journal, meta)
    for child, parent in parents.items():
        if parent in nodes and child in nodes:
            nodes[parent]['children'].append(nodes[child])
    top = [n for key, n in nodes.items() if parents.get(key) not in nodes]
    for item in nodes.values():
        item['children'].sort(key=lambda c: c['started'])
    top.sort(key=lambda n: n['started'])
    return top[-SUB_LIMIT:]


def claude_sessions():
    sessions = []
    for path in (CLAUDE / 'sessions').glob('*.json'):
        data = read_json(path)
        pid = data.get('pid')
        if not pid or not data.get('sessionId'):
            continue
        try:
            os.kill(pid, 0)
        except (OSError, TypeError):
            continue
        sessions.append(data)
    return sessions


def transcript_of(session, cwd):
    # Claude names the project folder after the start folder, with every other character as '-'.
    direct = CLAUDE / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', cwd) / f'{session}.jsonl'
    if direct.exists():
        return str(direct)
    matches = list((CLAUDE / 'projects').glob(f'*/{session}.jsonl'))
    return str(matches[0]) if matches else None


# ---- Codex ------------------------------------------------------------------

def read_codex(events):
    found = {'title': None, 'prompt': None, 'todos': None, 'pending': {}, 'activity': [], 'last_text': None}
    for event in events:
        payload = event.get('payload') or {}
        kind = payload.get('type')
        at = stamp(event)
        if kind == 'user_message' and payload.get('message'):
            found['prompt'] = clip(payload['message'], 160)
        if kind == 'message' and payload.get('role') == 'user':
            words = ' '.join(b.get('text', '') for b in payload.get('content') or [] if isinstance(b, dict) and b.get('type') == 'input_text').strip()
            if words and not words.startswith('<'):
                found['prompt'] = clip(words, 160)
        if kind in ('agent_message',) and payload.get('message'):
            found['last_text'] = clip(payload['message'], 160)
            found['activity'].append({'at': at, 'text': clip(payload['message'], 90), 'kind': 'say'})
        if kind in ('function_call', 'custom_tool_call'):
            name = payload.get('name', '')
            try:
                data = json.loads(payload.get('arguments') or '{}')
            except ValueError:
                data = {}
            if name == 'update_plan' and isinstance(data.get('plan'), list):
                found['todos'] = [{'title': s.get('step'), 'status': s.get('status')} for s in data['plan']]
                continue
            command = data.get('command') or payload.get('input') or ''
            text = clip(' '.join(command) if isinstance(command, list) else command, 70) or name
            found['pending'][payload.get('call_id')] = (name, data, at)
            found['activity'].append({'at': at, 'text': text, 'kind': 'tool'})
        if kind in ('function_call_output', 'custom_tool_call_output'):
            found['pending'].pop(payload.get('call_id'), None)
    found['activity'] = found['activity'][-8:]
    return found


# ---- Reports and the observer ------------------------------------------------

def report_path(pane):
    return setup_dir() / 'agents' / 'reports' / (pane.replace(':', '_').replace('/', '_') + '.json')


def write_report(step, task=None, done=None, total=None, clear=False):
    pane = os.environ.get('HERDR_PANE_ID') or f'pid-{os.getppid()}'
    path = report_path(pane)
    if clear:
        path.unlink(missing_ok=True)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = read_json(path)
    path.write_text(json.dumps({
        'task': task or previous.get('task'), 'step': step, 'done': done, 'total': total, 'at': time.time(),
    }) + '\n')
    return path


def observer_key():
    key = setting('PROXY_API_KEY')
    if key:
        return key
    config = Path(setting('CLAUDE_PROXY_DIR', HOME / 'claude-proxy')).expanduser() / 'config.yaml'
    text = config.read_text() if config.exists() else ''
    found = re.search(r'^\s*api-keys:\s*\n\s*-\s*["\']?([^"\'\s#]+)', text, re.M)
    return found.group(1) if found else ''


def proxy_base():
    return setting('PROXY_URL').rstrip('/') or 'http://127.0.0.1:' + str(setting('CLAUDE_PROXY_PORT', '8317'))


OBSERVER_PROMPT = """You watch a coding agent at work and keep a short report of its job.
You get your last report and only the events since then. Update the report.
Reply with JSON only:
{"task": "<the whole job, at most 8 words>",
 "now": "<what it does this minute, at most 10 words>",
 "steps": [{"title": "<at most 6 words>", "status": "done|active|pending"}],
 "progress": <0-100, your estimate for the whole job>}
Give 3 to 6 steps in order: done ones, the active one, then the likely next ones.
Keep step titles from your last report when they still fit, so the list stays stable.
Write in Simplified Technical English: plain words, active voice, simple present tense,
one fact per line, no "-ing" openings, British spelling. Example: "Run the payment tests"."""

OBSERVER_MODEL = 'claude-haiku-5-5'


def observe(agent, events_text):
    body = json.dumps({
        'model': setting('AGENT_OBSERVER_MODEL', OBSERVER_MODEL), 'max_tokens': 300,
        # Haiku 5.5 thinks by default and would spend the whole budget on it; the report needs none.
        'thinking': {'type': 'disabled'},
        'system': OBSERVER_PROMPT,
        'messages': [{'role': 'user', 'content': events_text}],
    }).encode()
    request = urllib.request.Request(proxy_base() + '/v1/messages', data=body, method='POST', headers={
        'content-type': 'application/json', 'x-api-key': observer_key(), 'anthropic-version': '2023-06-01',
        'Authorization': 'Bearer ' + observer_key(),
    })
    with urllib.request.urlopen(request, timeout=40) as response:
        reply = json.load(response)
    text = ''.join(b.get('text', '') for b in reply.get('content', []) if b.get('type') == 'text')
    found = re.search(r'\{.*\}', text, re.S)
    result = json.loads(found.group(0)) if found else {}
    steps = [{'title': clip(s.get('title'), 60), 'status': s.get('status') if s.get('status') in ('done', 'active', 'pending') else 'pending'}
             for s in result.get('steps', []) if isinstance(s, dict) and s.get('title')][:6]
    if not result.get('task') and not steps:
        raise ValueError('the observer reply held no report')
    progress = result.get('progress')
    return {'task': clip(result.get('task'), 70), 'now': clip(result.get('now'), 80), 'steps': steps,
            'progress': max(0, min(100, int(progress))) if isinstance(progress, (int, float)) else None,
            'tokens': (reply.get('usage') or {}).get('input_tokens', 0) + (reply.get('usage') or {}).get('output_tokens', 0)}


def observer_input(agent, found, previous):
    """Only what changed: the last report and the events after it. A busy agent costs a few hundred tokens a minute."""
    since = previous.get('last_event') or 0
    events = [e for e in found.get('activity', []) if not since or (e.get('at') or 0) > since]
    lines = [f'Agent: {agent["agent"]} in {Path(agent["cwd"]).name or agent["cwd"]}']
    report = previous.get('result')
    if report:
        lines.append('Your last report: ' + json.dumps({k: report.get(k) for k in ('task', 'now', 'steps', 'progress')}))
    if found.get('prompt') and (not report or found['prompt'] != previous.get('prompt')):
        lines.append(f'Request from the person: {found["prompt"]}')
    lines.append('New events, oldest first:')
    for item in events:
        lines.append(('- says: ' if item['kind'] == 'say' else '- runs: ') + item['text'])
    return '\n'.join(lines)[:3000], events


# ---- Snapshot ----------------------------------------------------------------

def collect(run_observer=False):
    now = time.time()
    previous = read_json(SNAPSHOT)
    cache = previous.get('parsed', {})
    observed_dir = setup_dir() / 'agents' / 'observer'
    panes = {a['pane_id']: a for a in herdr_agents()}
    sessions = claude_sessions()
    codex = codex_processes()
    # A process keeps its pane for life, so ps runs only for processes not seen before.
    known = {int(pid): pane for pid, pane in previous.get('pids', {}).items()}
    wanted = [s['pid'] for s in sessions] + codex
    by_pid = {pid: known[pid] for pid in wanted if pid in known}
    found_now = pane_of([pid for pid in wanted if pid not in known])
    by_pid.update(found_now)
    by_pid.update({pid: None for pid in wanted if pid not in by_pid})
    transcripts = previous.get('transcripts', {})
    agents, parsed, used_panes, rollouts, watch = [], {}, set(), {}, []
    # Workflow names and phases come from the Workflow call, which may be older than the transcript tail.
    workflows = dict(list(previous.get('workflows', {}).items())[-100:])

    def base(pane, info):
        return {
            'id': pane, 'pane': pane if pane in panes else None, 'agent': info.get('agent', 'claude'),
            'name': info.get('name') or Path(info.get('cwd', '')).name or info.get('agent'),
            'status': info.get('agent_status', 'idle'), 'title': info.get('terminal_title_stripped'),
            'cwd': info.get('cwd', ''), 'project': Path(info.get('cwd', '')).name, 'focused': info.get('focused', False),
            'workspace': info.get('workspace_id'), 'tab': info.get('tab_id'),
        }

    def parse(path, reader, size=TAIL):
        """Parse a transcript tail once per change; idle agents cost one stat call."""
        try:
            stat = os.stat(path)
        except OSError:
            return None, None
        key = f'{stat.st_size}:{stat.st_mtime}'
        if cache.get(path, {}).get('key') == key:
            parsed[path] = cache[path]
            return cache[path]['found'], stat.st_mtime
        found = reader(tail_events(path, size))
        found['pending'] = [tool_step(n, d) for n, d, _ in found['pending'].values()][-3:]
        parsed[path] = {'key': key, 'found': found}
        return found, stat.st_mtime

    def finish(agent, found, updated, transcript, steps_extra=None):
        found = found or {}
        report = read_json(report_path(agent['pane'] or agent['id']))
        if report and now - report.get('at', 0) > 6 * 3600:
            report = {}
        todos = steps_extra or found.get('todos') or []
        steps = as_steps(todos)
        pending = found.get('pending') or []
        now_step = pending[-1] if pending and agent['status'] == 'working' else None
        agent.update({
            'task': found.get('title') or agent['title'], 'prompt': found.get('prompt'), 'now': now_step,
            'said': found.get('last_text'), 'steps': steps, 'activity': found.get('activity', []),
            'updated': updated, 'source': 'tasks' if steps else 'activity', 'transcript': transcript,
        })
        observed = read_json(observed_dir / f'{agent["session"]}.json') if agent.get('session') else {}
        if observed.get('result') and not steps and now - observed.get('at', 0) < 3600:
            result = observed['result']
            agent.update({'steps': result.get('steps') or [], 'progress': result.get('progress'), 'source': 'observer',
                          'task': result.get('task') or agent['task']})
            agent['now'] = agent['now'] or (result.get('now') if agent['status'] == 'working' else None)
        if report:
            agent.update({'task': report.get('task') or agent['task'], 'now': report.get('step') or agent['now'], 'source': 'report'})
            if report.get('total'):
                agent['progress'] = round(100 * (report.get('done') or 0) / report['total'])
                agent['stepCount'] = [report.get('done') or 0, report['total']]
        if agent['steps'] and agent.get('progress') is None:
            done = sum(1 for s in agent['steps'] if s['status'] == 'done')
            agent['progress'] = round(100 * done / len(agent['steps']))
            agent['stepCount'] = [done, len(agent['steps'])]
        agent.setdefault('progress', None)
        return agent

    for session in sessions:
        pane = by_pid.get(session['pid'])
        info = panes.get(pane) or {'agent': 'claude', 'cwd': session.get('cwd', ''), 'name': session.get('name'),
                                   'agent_status': 'working' if session.get('status') == 'busy' else 'idle'}
        if pane in used_panes:
            continue
        used_panes.add(pane)
        agent = base(pane or f'pid-{session["pid"]}', info)
        agent['session'] = session['sessionId']
        transcript = transcripts.get(session['sessionId'])
        if not transcript or not os.path.exists(transcript):
            transcript = transcripts[session['sessionId']] = transcript_of(session['sessionId'], session.get('cwd', ''))
        found, updated = parse(transcript, read_claude) if transcript else (None, None)
        agent = finish(agent, found, updated, transcript, task_files(session['sessionId']))
        for run, meta in ((found or {}).get('workflows') or {}).items():
            workflows[run] = meta
        agent['subagents'] = subagent_tree(transcript, now, parse, workflows, observed_dir, watch) if transcript else []
        agents.append(agent)

    for pid in codex:
        pane = by_pid.get(pid)
        owner = next((a for a in agents if pane and a['pane'] == pane), None)
        info = panes.get(pane) or {}
        # lsof costs about 0.4 s, so each process's open rollout is looked up at most once a minute.
        known_rollout = previous.get('rollouts', {}).get(str(pid))
        if known_rollout and now - known_rollout[1] < 60 and os.path.exists(known_rollout[0]):
            rollout = known_rollout[0]
        else:
            rollout = open_rollout(pid)
        if rollout:
            rollouts[str(pid)] = [rollout, known_rollout[1] if known_rollout and known_rollout[0] == rollout and now - known_rollout[1] < 60 else now]
        rollout = rollout or (latest_rollout(info.get('cwd')) if info.get('agent') == 'codex' else None)
        found, updated = parse(rollout, read_codex) if rollout else (None, None)
        if owner and owner['agent'] != 'codex':
            # A Codex started by another agent, for example `codex exec` as a reviewer.
            owner['subagents'].append({'id': f'codex-{pid}', 'name': 'Codex', 'description': (found or {}).get('prompt'),
                                       'model': '', 'running': True, 'step': ((found or {}).get('pending') or [None])[-1],
                                       'said': (found or {}).get('last_text'), 'activity': ((found or {}).get('activity') or [])[-4:],
                                       'updated': updated or now, 'started': updated or now, 'children': [], 'kind': 'codex'})
            continue
        if pane in used_panes or (not pane and not rollout):
            continue
        used_panes.add(pane)
        agent = base(pane or f'pid-{pid}', info or {'agent': 'codex', 'cwd': '', 'agent_status': 'working'})
        agent['session'] = Path(rollout).stem if rollout else None
        agent = finish(agent, found, updated, rollout)
        agent['subagents'] = []
        agents.append(agent)

    for pane, info in panes.items():
        if pane not in used_panes:
            agent = finish(base(pane, info), None, None, None)
            agent['subagents'] = []
            agents.append(agent)

    if run_observer and setting('AGENT_OBSERVER', '1') != '0':
        run_observers(agents, parsed, observed_dir, now)
        run_sub_observers(watch, parsed, observed_dir, now)
        for agent in agents:
            if agent.get('session') and agent['source'] == 'activity':
                result = read_json(observed_dir / f'{agent["session"]}.json').get('result')
                if result:
                    agent.update({'steps': result.get('steps') or [], 'progress': result.get('progress'), 'source': 'observer',
                                  'task': result.get('task') or agent['task']})

    # Agents keep the order in which they first appeared, so a refresh never moves them.
    seen = {key: at for key, at in previous.get('seen', {}).items() if any(a['id'] == key for a in agents)}
    for agent in agents:
        seen.setdefault(agent['id'], now)
    agents.sort(key=lambda a: (seen[a['id']], a['id']))
    live = {s['sessionId'] for s in sessions}
    snapshot = {'at': now, 'agents': agents, 'seen': seen, 'rollouts': rollouts, 'workflows': workflows, 'observer': setting('AGENT_OBSERVER', '1') != '0', 'parsed': parsed,
                'pids': {str(pid): pane for pid, pane in by_pid.items()},
                'transcripts': {k: v for k, v in transcripts.items() if k in live}}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    # The dock and the GPUIX app both run this, so each writer gets its own temporary file.
    temporary = SNAPSHOT.with_suffix(f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(snapshot))
    temporary.replace(SNAPSHOT)
    return snapshot


def run_observers(agents, parsed, folder, now):
    """Ask the small model about working agents that keep no task list.

    Each agent at most once a minute, only after new events, and only with those events."""
    folder.mkdir(parents=True, exist_ok=True)
    jobs = []
    for agent in agents:
        transcript = agent.get('transcript')
        if agent['status'] != 'working' or agent['source'] in ('tasks', 'report') or not transcript or not agent.get('session'):
            continue
        path = folder / f'{agent["session"]}.json'
        previous = read_json(path)
        key = parsed.get(transcript, {}).get('key')
        if previous.get('key') == key or now - previous.get('at', 0) < 60:
            continue
        found = parsed[transcript]['found']
        text, events = observer_input(agent, found, previous)
        if not events:
            continue
        jobs.append((path, key, previous, found, text, events))
    if not jobs:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(observe, None, text): job for job in jobs[:6] for text in [job[4]]}
        for future in concurrent.futures.as_completed(futures):
            path, key, previous, found, _, events = futures[future]
            record = {'at': now, 'key': key, 'prompt': found.get('prompt'), 'last_event': max(e.get('at') or 0 for e in events)}
            try:
                result = future.result()
                record['result'] = result
                record['tokens'] = previous.get('tokens', 0) + result.pop('tokens', 0)
            except Exception as error:  # the proxy may be down; the view keeps the plain activity
                record.update({'result': previous.get('result'), 'error': str(error)[:200], 'tokens': previous.get('tokens', 0)})
            path.write_text(json.dumps(record) + '\n')


def run_sub_observers(watch, parsed, folder, now):
    """Steps for running subagents that keep no task list. Each at most every 90 s, only after new
    events, four per round, and with the same short incremental input as the agents."""
    jobs = []
    for item, path, found in watch:
        record_path = folder / f'sub-{item["id"]}.json'
        previous = read_json(record_path)
        key = parsed.get(path, {}).get('key')
        if previous.get('key') == key or now - previous.get('at', 0) < 90:
            continue
        text, events = observer_input({'agent': f'subagent "{item["description"] or item["name"]}"', 'cwd': ''}, found, previous)
        if events:
            jobs.append((record_path, key, previous, found, text, events))
    if not jobs:
        return
    folder.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(observe, None, job[4]): job for job in jobs[:4]}
        for future in concurrent.futures.as_completed(futures):
            path, key, previous, found, _, events = futures[future]
            record = {'at': now, 'key': key, 'prompt': found.get('prompt'), 'last_event': max(e.get('at') or 0 for e in events)}
            try:
                result = future.result()
                record['tokens'] = previous.get('tokens', 0) + result.pop('tokens', 0)
                record['result'] = result
            except Exception as error:
                record.update({'result': previous.get('result'), 'error': str(error)[:200], 'tokens': previous.get('tokens', 0)})
            path.write_text(json.dumps(record) + '\n')


def text(snapshot):
    for agent in snapshot['agents']:
        steps = agent.get('stepCount')
        running = sum(s['running'] for s in agent['subagents'])
        yield (f'{agent["status"]:8} {agent["name"][:24]:24} {clip(agent.get("task"), 50):50} '
               f'{f"{steps[0]}/{steps[1]}" if steps else "":5} {agent.get("now") or ""}'
               + (f'  [{running} subagents running]' if running else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--observe', action='store_true', help='also ask the small model about working agents')
    parser.add_argument('--print', action='store_true', help='print the snapshot as text')
    args = parser.parse_args()
    snapshot = collect(args.observe)
    if args.print:
        for line in text(snapshot):
            print(line)


if __name__ == '__main__':
    main()
