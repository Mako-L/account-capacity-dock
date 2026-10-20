#!/usr/bin/env python3
"""Install and operate the host dock and its optional account proxies."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get('MAKO_CAPACITY_HOME', Path.home() / '.mako-capacity')).expanduser().resolve()
SETTINGS = STATE / 'settings.json'


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def need(command):
    if not shutil.which(command):
        raise RuntimeError(f'Missing {command}. See README.md prerequisites.')


def native_tools():
    if platform.system() != 'Darwin' or settings().get('NATIVE_UI') == 'rust':
        need('cargo')
    if platform.system() == 'Darwin':
        if int(platform.mac_ver()[0].split('.')[0]) < 14:
            raise RuntimeError('The macOS build requires macOS 14 or newer.')
        run('xcrun', '--find', 'clang', stdout=subprocess.DEVNULL)


def settings():
    return json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}


def paths():
    saved = settings()
    return {key: str(Path(os.environ.get(key, saved.get(key, STATE / name))).expanduser().resolve())
            for key, name in [('CLAUDE_PROXY_DIR', 'claude-proxy')]}


def write_new(path, content):
    # Re-running setup preserves keys, credentials, and user configuration.
    try:
        with path.open('x') as stream:
            stream.write(content)
        path.chmod(0o600)
    except FileExistsError:
        pass


def initialize():
    os.umask(0o077)
    dirs = paths()
    claude = Path(dirs['CLAUDE_PROXY_DIR'])
    for folder in [STATE, claude, claude / 'auths', claude / 'logs']:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_urlsafe(32)
    write_new(claude / 'client-key', key + '\n')
    key = (claude / 'client-key').read_text().strip()
    write_new(claude / 'management.env', 'MANAGEMENT_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
    write_new(claude / 'config.yaml', f'''config-version: 8
server:
  host: ""
  port: 8317
management:
  allow-remote: true
  secret-key: ""
  disable-control-panel: false
  disable-auto-update-panel: true
access:
  api-keys:
    - "{key}"
oauth:
  auth-dir: "/root/.cli-proxy-api"
routing:
  strategy: round-robin
  session-affinity: true
  session-affinity-ttl: "1h"
''')
    saved = settings()
    saved.update(dirs)
    # CURSOR_DIR, and CODEX_PROXY_DIR for a legacy Codex Proxy inventory, are read-only paths.
    for key in ('CURSOR_DIR', 'CODEX_PROXY_DIR'):
        if os.environ.get(key):
            saved[key] = str(Path(os.environ[key]).expanduser().resolve())
    saved['CLAUDE_PROXY_PORT'] = os.environ.get('CLAUDE_PROXY_PORT', saved.get('CLAUDE_PROXY_PORT', '8317'))
    SETTINGS.write_text(json.dumps(saved, indent=2) + '\n')
    SETTINGS.chmod(0o600)
    print(f'Configuration: {STATE}', flush=True)


def remote():
    """The proxy URL when CLIProxyAPI runs on another machine, else an empty string."""
    return settings().get('PROXY_URL', '').rstrip('/')


def management(path, body=None):
    request = urllib.request.Request(
        remote() + '/v0/management/' + path, data=None if body is None else json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + settings().get('PROXY_MANAGEMENT_KEY', ''),
                 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Proxy refused {path.split("?")[0]} (HTTP {error.code}); check the management key.') from error
    except (OSError, ValueError) as error:
        raise RuntimeError(f'Proxy at {remote()} is not reachable: {error}') from error


def use_proxy(url, key):
    """Save a remote proxy (or 'local' for Docker), then check that the management API answers."""
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    saved = settings()
    if url == 'local':
        saved.pop('PROXY_URL', None)
        saved.pop('PROXY_MANAGEMENT_KEY', None)
    else:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('Proxy URL must look like https://host:8317')
        if not key:
            raise ValueError('A remote proxy needs its management key (--key).')
        saved.update(PROXY_URL=url.rstrip('/'), PROXY_MANAGEMENT_KEY=key)
    previous = SETTINGS.read_text() if SETTINGS.exists() else '{}\n'
    SETTINGS.write_text(json.dumps(saved, indent=2) + '\n')
    SETTINGS.chmod(0o600)
    if url == 'local':
        print('Using the local Docker proxy.')
        return
    try:
        files = management('auth-files').get('files', [])
    except RuntimeError:
        SETTINGS.write_text(previous)  # Keep the last working proxy when the new one fails.
        raise
    print(f'Using {remote()}: {len(files)} logins found.')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        print('Warning: plain http sends account tokens unencrypted; use https or an SSH tunnel.')


def remote_login(provider):
    """Sign in through the remote proxy's OAuth flow: open the link, then paste the callback URL."""
    start = management(('anthropic' if provider == 'claude' else 'codex') + '-auth-url?is_webui=true')
    print('Open this link and sign in:\n' + start['url'])
    webbrowser.open(start['url'])
    print('The browser then fails to load a localhost page. That is expected.')
    callback = input('Paste the full URL from the address bar: ').strip()
    management('oauth-callback', {'provider': 'anthropic' if provider == 'claude' else 'codex',
                                  'redirect_url': callback})
    for _ in range(30):
        status = management('get-auth-status?state=' + urllib.parse.quote(start['state'])).get('status')
        if status != 'wait':
            break
        time.sleep(1)
    if status != 'ok':
        raise RuntimeError(f'Login did not finish (status {status}).')
    print('Signed in. The dock shows the account on its next refresh.')


def docker():
    need('docker')
    run('docker', 'compose', 'version', stdout=subprocess.DEVNULL)
    run('docker', 'info', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def compose(*args):
    env = dict(os.environ)
    env.update({k: str(v) for k, v in settings().items()})
    env.update(paths())
    # Explicit shell overrides take precedence over persisted settings.
    env.update(os.environ)
    run('docker', 'compose', '--project-directory', ROOT, '-f', ROOT / 'deploy/compose.yaml', *args, env=env)


def install_app():
    native_tools()
    use_swift = platform.system() == 'Darwin' and settings().get('NATIVE_UI') != 'rust'
    if use_swift:
        run(ROOT / 'build.sh')
    else:
        run('cargo', 'build', '--locked', '--release', '--manifest-path', ROOT / 'native/Cargo.toml')
    executable = ROOT / 'native/target/release' / ('mako-capacity.exe' if os.name == 'nt' else 'mako-capacity')
    if platform.system() == 'Darwin':
        destination = Path.home() / 'Applications/Mako Capacity.app'
        if use_swift:
            run('ditto', ROOT / 'build/Mako Capacity.app', destination)
        (destination / 'Contents/MacOS').mkdir(parents=True, exist_ok=True)
        if not use_swift:
            shutil.copy2(executable, destination / 'Contents/MacOS/MakoCapacity')
        info = plistlib.loads((ROOT / 'Info.plist').read_bytes())
        if not use_swift:
            info.pop('CFBundleIconFile', None)
        info['CFBundleVersion'] = '2'
        info['CFBundleShortVersionString'] = '0.2.0'
        (destination / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        shutil.copytree(ROOT / 'Resources', destination / 'Contents/Resources', dirs_exist_ok=True)
        run('codesign', '--force', '--deep', '--sign', '-', destination)
    else:
        destination = STATE / 'bin' / executable.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(executable, destination)
        shutil.copytree(ROOT / 'Resources', STATE / 'licenses', dirs_exist_ok=True)
    bindir = Path.home() / '.local/bin'
    bindir.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        launcher = bindir / 'mako-capacity.cmd'
        launcher.write_text('@echo off\n"' + sys.executable + '" "' + str(ROOT / 'scripts/capacity.py') + '" %*\n')
    else:
        launcher = bindir / 'mako-capacity'
        launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(ROOT / 'scripts/capacity.py')) + ' "$@"\n')
        launcher.chmod(0o755)
    print(f'Installed {destination}\nCLI: {launcher} (add ~/.local/bin to PATH).', flush=True)


def install_codeburn():
    need('node')
    need('npm')
    node = str(Path(shutil.which('node')).resolve())
    version = subprocess.check_output([node, '--version'], text=True).strip().lstrip('v')
    major, minor = map(int, version.split('.')[:2])
    if (major, minor) < (22, 13):
        raise RuntimeError('CodeBurn requires Node.js 22.13 or newer. Install it from https://nodejs.org/')
    prefix = STATE / 'dependencies'
    package = prefix / 'node_modules/codeburn'
    installed = json.loads((package / 'package.json').read_text()).get('version') if (package / 'package.json').exists() else None
    if installed != '0.9.25':
        run(shutil.which('npm'), 'install', '--prefix', prefix, '--no-audit', '--no-fund', 'codeburn@0.9.25')
    saved = settings()
    saved['CODEBURN_COMMAND'] = [node, str(package / 'dist/cli.js')]
    saved['PYTHON_COMMAND'] = sys.executable
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    SETTINGS.write_text(json.dumps(saved, indent=2) + '\n')
    SETTINGS.chmod(0o600)


def start_app():
    if platform.system() == 'Darwin':
        app = Path.home() / 'Applications/Mako Capacity.app'
        if not app.exists():
            install_app()
        run('open', app)
    else:
        app = STATE / 'bin' / ('mako-capacity.exe' if os.name == 'nt' else 'mako-capacity')
        if not app.exists():
            install_app()
        subprocess.Popen([str(app)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    install = commands.add_parser('install', help='initialize proxies, install dock and CLI, start everything')
    install.add_argument('--rust-ui', action='store_true', help='use the portable Rust UI on macOS too')
    install.add_argument('--app-only', action='store_true', help='use existing proxy sources without starting Docker')
    install.add_argument('--proxy-url', help='use a CLIProxyAPI on another machine instead of Docker')
    install.add_argument('--key', default=os.environ.get('PROXY_MANAGEMENT_KEY', ''), help='its management key')
    commands.add_parser('init', help='generate proxy configuration without starting anything')
    commands.add_parser('up', help='start proxies and open installed dock')
    commands.add_parser('down', help='remove this stack’s containers; keep account data and app')
    commands.add_parser('status', help='show proxy container status')
    commands.add_parser('doctor', help='check macOS, build tools, Docker, and configured paths')
    commands.add_parser('open', help='open the dock')
    proxy = commands.add_parser('proxy', help='use a CLIProxyAPI on another machine, or "local" for Docker')
    proxy.add_argument('url', help='for example https://server:8317, or local')
    proxy.add_argument('--key', default=os.environ.get('PROXY_MANAGEMENT_KEY', ''), help='the remote management key')
    logs = commands.add_parser('logs', help='show the last 100 proxy log lines')
    logs.add_argument('service', nargs='?', choices=['claude-proxy'])
    login = commands.add_parser('login', help='add a provider account')
    login.add_argument('provider', choices=['claude', 'codex', 'cursor'])
    args = parser.parse_args()
    if args.command == 'install' and args.proxy_url:
        use_proxy(args.proxy_url, args.key)
    if args.command == 'proxy':
        use_proxy(args.url, args.key)
    elif args.command == 'init':
        initialize()
    elif args.command == 'install':
        if args.rust_ui:
            STATE.mkdir(parents=True, exist_ok=True)
            saved = settings()
            saved['NATIVE_UI'] = 'rust'
            SETTINGS.write_text(json.dumps(saved, indent=2) + '\n')
        native_tools()
        install_codeburn()
        local = not args.app_only and not remote()
        if local:
            docker()
            initialize()
        install_app()
        if local:
            compose('up', '-d')
        start_app()
        print('Add accounts: mako-capacity login claude / codex / cursor')
    elif args.command in ('up', 'down', 'status', 'logs') and remote():
        if args.command == 'up':
            start_app()
        print(f'The proxy runs at {remote()}; manage it on that machine.')
    elif args.command == 'up':
        native_tools()
        docker()
        initialize()
        compose('up', '-d')
        start_app()
    elif args.command == 'open':
        start_app()
    elif args.command in ('down', 'status', 'logs'):
        docker()
        if not SETTINGS.exists():
            raise RuntimeError('Run ./capacity init or install first.')
        if args.command == 'logs':
            compose('logs', '--tail', '100', *([args.service] if args.service else []))
        else:
            compose('down' if args.command == 'down' else 'ps')
    elif args.command == 'doctor' and remote():
        native_tools()
        print(f'Proxy {remote()}: {len(management("auth-files").get("files", []))} logins.')
    elif args.command == 'doctor':
        native_tools()
        docker()
        if not SETTINGS.exists():
            raise RuntimeError('No setup yet. Run ./capacity install.')
        for key, value in paths().items():
            if not Path(value).is_dir():
                raise RuntimeError(f'Missing {key}: {value}')
            print(f'{key}: {value}')
        command = settings().get('CODEBURN_COMMAND')
        if not command or not all(Path(part).is_file() for part in command):
            raise RuntimeError('CodeBurn dependency missing. Run ./capacity install.')
        run(*command, '--version')
        compose('config', '--quiet')
        print('Native build tools, CodeBurn, Docker daemon, and Compose configuration are ready.')
    elif args.provider == 'cursor':
        need('cursor-agent')
        run(shutil.which('cursor-agent'), 'login', env=dict(os.environ, **({'AGENT_CLI_CREDENTIAL_STORE': 'file'} if platform.system() != 'Darwin' else {})))
    elif remote():
        remote_login(args.provider)
    else:
        docker()
        initialize()
        # Temporary container publishes the OAuth callback, then removes itself.
        # CLIProxyAPI serves both Claude and Codex logins.
        callback, flag = ('54545', '-claude-login') if args.provider == 'claude' else ('1455', '-codex-login')
        compose('run', '--rm', '-p', f'127.0.0.1:{callback}:{callback}', 'claude-proxy',
                './CLIProxyAPI', '-config', '/CLIProxyAPI/config.yaml', flag, '-no-browser')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f'mako-capacity: {error}', file=sys.stderr)
        sys.exit(1)
