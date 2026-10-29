#!/usr/bin/env python3
"""Write demo accounts and agents for screenshots: python3 scripts/demo_data.py [folder=/tmp/demo]

Every name, email and number here is made up. The screenshots in docs/ use only this data.
Then: cd gpuix-app && bun screenshot.ts /tmp/demo/snapshot.json dock,accounts,settings,agents
"""
import json
import sys
import time
from pathlib import Path

H, D = 3600, 86400
now = time.time()
out = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/demo')


def window(label, used, reset_hours, cost=None, tokens=None, plan=None, used_up=None):
    length = 5 * H if label == '5-hour' else 7 * D
    start = now + reset_hours * H - length
    w = {'label': label, 'used': used, 'resetAt': now + reset_hours * H}
    if cost is not None:
        w['spent'] = {'tokens': tokens, 'costUsd': cost, **({'planPercent': plan} if plan is not None else {})}
    elapsed = now - start
    # The same pace rule as collector.window_usage.
    if 0 < used < 100 and elapsed > 0:
        left = elapsed * (100 - used) / used
        w['fullIn'] = left if now + left < w['resetAt'] else None
        w['atReset'] = None if w['fullIn'] else round(used * length / elapsed)
    if used_up:
        w['usedUpIn'] = used_up * H
    return w


def usage(cost, tokens, scope='account'):
    return {'inputTokens': tokens * 0.004, 'outputTokens': tokens * 0.006, 'cacheReadTokens': tokens * 0.93,
            'cacheWriteTokens': tokens * 0.06, 'tokens': tokens, 'costUsd': cost, 'unpricedModels': 0,
            'scope': scope, 'status': 'live', 'fetchedAt': now, 'message': '', 'estimated': False}


def account(i, provider, title, email, windows, plan='', status='live', message='', cost=None, tokens=None, source='CLI proxy'):
    a = {'id': f'demo-{i}', 'provider': provider, 'email': email, 'title': title, 'plan': plan, 'source': source,
         'status': status, 'message': message, 'fetchedAt': now, 'nextPollAt': now + 300, 'onDemandUsd': None,
         'windows': windows}
    if provider == 'Claude' and status == 'live':
        a['subscription'] = {'name': 'Max 20x', 'monthlyUsd': 200}
    if cost is not None:
        a['localUsage'] = usage(cost, tokens)
    return a


accounts = [
    account(1, 'Claude', 'studio', 'studio@example.com', [
        window('5-hour', 22, 3.1, 18.40, 31e6), window('Weekly', 38, 109, 164.20, 288e6, plan=356)], cost=41.87, tokens=48.2e6),
    account(2, 'Claude', 'research', 'research@example.com', [
        window('5-hour', 64, 1.3, 61.10, 104e6), window('Weekly', 81, 46, 402.75, 690e6, plan=873)], cost=96.30, tokens=170e6),
    account(3, 'Claude', 'side-project', 'side@example.com', [
        window('5-hour', 100, 0.5, 74.90, 121e6), window('Weekly', 100, 14, 512.60, 905e6, plan=1111, used_up=34)],
        status='rateLimited', message='At limit', cost=88.12, tokens=150e6),
    account(4, 'Claude', 'archive', 'archive@example.com', [], status='loginRequired', message='Sign in again in the provider app or proxy.'),
    account(5, 'Codex', 'Pro Max', 'builder@example.com', [window('Weekly', 12, 149, 22.15, 41e6)], plan='Pro Max', cost=9.80, tokens=17e6),
    account(6, 'Codex', 'Pro', 'reviewer@example.com', [
        window('5-hour', 47, 2.4, 6.30, 12e6), window('Weekly', 73, 59, 51.90, 96e6)], plan='Pro', cost=14.60, tokens=26e6),
    account(7, 'Cursor', 'cursor', 'dev@example.com', [
        {'label': 'Cursor Models', 'used': 28, 'resetAt': now + 400 * H},
        {'label': 'Other Models', 'used': 9, 'resetAt': now + 400 * H},
        {'label': 'Grok Bot', 'used': 3, 'resetAt': now + 20 * H}], plan='Pro', source='Cursor CLI'),
]
accounts[6]['localUsage'] = usage(3.25, 5.1e6, scope='provider')


def tokens(cost, week):
    return {'input': cost * 900, 'output': cost * 1600, 'cacheRead': cost * 52000, 'cacheWrite': cost * 4100, 'cost': cost, 'weekPercent': week}


def step(title, status, took=None, since=None):
    s = {'title': title, 'status': status}
    if took:
        s['took'] = took
    if since:
        s['since'] = now - since
    return s


def sub(id, name, description, running=False, idle=False, minutes=12, step_now=None, steps=(), cost=1.0, children=(), kind='agent', phase=None, summary=None, model='sonnet'):
    done = sum(s['status'] == 'done' for s in steps)
    return {'id': id, 'name': name, 'description': description, 'model': model, 'running': running, 'idle': idle,
            'step': step_now, 'updated': now - (20 if running else minutes * 60 / 3), 'started': now - minutes * 60,
            'said': None, 'activity': [], 'children': list(children), 'kind': kind, 'phase': phase, 'summary': summary,
            'steps': list(steps), 'progress': round(100 * done / len(steps)) if steps else (None if running else 100),
            'usage': tokens(cost, round(cost / 22, 1))}


checkout_subs = [
    sub('s1', 'code-reviewer', 'Review retry logic for races', running=True, minutes=6, step_now='Read src/queue/worker.ts', cost=2.84, steps=[
        step('Find every retry path', 'done', took=95), step('Check the lock around retries', 'done', took=140),
        step('Read the worker loop', 'active', since=110), step('Write findings', 'pending')],
        children=[sub('s1a', 'fork', 'Check the lock around retries', minutes=3, cost=0.41, steps=[step('Read lock.ts', 'done', took=48), step('Trace callers', 'done', took=71)])]),
    sub('wf1', 'payment-tests', 'Run the payment test matrix', running=True, minutes=9, kind='workflow', summary='3 of 5 agents done', cost=4.12,
        step_now='tests:refunds', steps=[step('Build', 'done', took=180), step('Unit', 'done', took=210), step('Integration', 'active', since=150)],
        # Running first, then finished, then idle: the order agents.py gives.
        children=[sub('w2', 'tests:refunds', 'Refund tests', running=True, minutes=2, cost=0.7, phase='Integration', step_now='Run refunds.spec.ts'),
                  sub('w1', 'tests:api', 'API tests', minutes=4, cost=0.9, phase='Unit')]),
    sub('s2', 'Explore', 'Find where webhooks are verified', minutes=18, cost=0.66, model='haiku', steps=[
        step('Search for signature checks', 'done', took=40), step('Read the webhook router', 'done', took=65)]),
    sub('s3', 'docs-writer', 'Draft the release note', idle=True, minutes=41, cost=0.38, steps=[step('Draft the note', 'done', took=210)]),
]


def agent(id, name, status, task, progress, steps, subs=(), cost=0.0, week=0.0, minutes=30, now_step=None, agent='claude', tab=None):
    own = tokens(cost, week)
    total = tokens(cost + sum(s['usage']['cost'] for s in subs), round(week + sum(s['usage']['weekPercent'] for s in subs), 1))
    done = sum(s['status'] == 'done' for s in steps)
    return {'id': id, 'pane': id, 'agent': agent, 'name': name, 'tabName': tab, 'status': status, 'title': task,
            'cwd': f'/work/{name}', 'project': name, 'task': task, 'prompt': None, 'now': now_step, 'said': None,
            'steps': steps, 'activity': [], 'updated': now - 15, 'started': now - minutes * 60, 'source': 'tasks',
            'progress': progress, 'stepCount': [done, len(steps)] if steps else None, 'subagents': list(subs),
            'usage': own, 'totalUsage': total}


agents = [
    agent('w1:p1', 'checkout-api', 'working', 'Add webhook handling for failed payments', 60, [
        step('Read the payment routes', 'done', took=240), step('Add the webhook handler', 'done', took=1260),
        step('Review retries with a subagent', 'active', since=380), step('Run the payment tests', 'pending'), step('Open the pull request', 'pending')],
        checkout_subs, cost=18.42, week=8.4, minutes=52, now_step='Subagent: Review retry logic for races', tab='payments'),
    agent('w2:p1', 'design-system', 'working', 'Define dark mode colour tokens', 25, [
        step('List every colour in use', 'done', took=410), step('Define the tokens', 'active', since=95),
        step('Swap the old values', 'pending'), step('Check contrast', 'pending')], cost=6.10, week=2.8, minutes=21,
        now_step='Edit tokens.css', agent='codex'),
    agent('w3:p1', 'mobile-app', 'blocked', 'Fix the login crash on Android', 67, [
        step('Reproduce the crash', 'done', took=520), step('Find the null token', 'done', took=330), step('Ask before the schema change', 'active', since=240)],
        cost=9.75, week=4.4, minutes=38, now_step='Waiting for your answer'),
    agent('w4:p1', 'docs-site', 'done', 'Rewrite the install guide', 100, [
        step('Read the old guide', 'done', took=180), step('Write the new steps', 'done', took=900), step('Check every link', 'done', took=120)],
        cost=3.20, week=1.5, minutes=25),
    agent('w5:p1', 'infra', 'idle', 'Bump the Node version', None, [], cost=0.0, week=0.0, minutes=90),
]
for a in agents:
    if a['status'] == 'done':
        a['updated'] = a['started'] + 20 * 60

(out / 'home/.mako-capacity').mkdir(parents=True, exist_ok=True)
(out / 'snapshot.json').write_text(json.dumps({'updatedAt': now, 'accounts': accounts, 'hidden': [], 'warning': ''}, indent=1))
(out / 'agents.json').write_text(json.dumps({'at': now, 'agents': agents, 'observer': True}, indent=1))
settings = out / 'home/.mako-capacity/settings.json'
if not settings.exists():
    settings.write_text(json.dumps({'SHOW_IDLE_AGENTS': '1'}))
print('wrote', out)
