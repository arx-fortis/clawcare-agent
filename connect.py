"""Initialize user-owned ClawCare coordination; never accepts model API keys."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from team_api import Credentials, TeamService
from team_mcp import Bridge

PACKAGE = Path(__file__).resolve().parent


def private_directory(destination):
    destination = Path(destination).expanduser().resolve()
    if destination == PACKAGE or PACKAGE in destination.parents:
        raise ValueError('Choose a private data directory outside the downloaded package')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    if os.name == 'nt':
        # Path is an environment value, never interpolated into PowerShell code.
        script = '''$ErrorActionPreference='Stop'
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$acl=New-Object Security.AccessControl.DirectorySecurity
$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true,$false)
$rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
$acl.AddAccessRule($rule)
$dir=New-Object System.IO.DirectoryInfo($env:CLAWCARE_PRIVATE_DIRECTORY)
$dir.SetAccessControl($acl)
$actual=$dir.GetAccessControl()
if(-not $actual.AreAccessRulesProtected){throw 'Inheritance still enabled'}
$rules=$actual.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier])
if($rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $sid.Value -or $rules[0].AccessControlType -ne 'Allow'){throw 'Unexpected directory access'}
'''
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                       env={**os.environ, 'CLAWCARE_PRIVATE_DIRECTORY': str(destination)},
                       check=True, capture_output=True, timeout=30)
    else:
        destination.chmod(0o700)
    return destination


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def initialize(destination, workspace, player, port=8765, mode='openclaw'):
    Credentials.workspace(workspace)
    if not isinstance(player, str) or not player.strip() or len(player) > 80:
        raise ValueError('Player must be 1..80 characters')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    if mode not in ('openclaw', 'manual'):
        raise ValueError('Unsupported connection mode')
    root = private_directory(destination)
    service = TeamService(root)
    # Separate principals avoid giving the model the human owner's authority.
    identities = [('operator', player, 'human-console', 'owner'),
                  ('agent', player + ':agent', 'openclaw-clawcare', 'worker')]
    for name, principal, agent, role in identities:
        token = service.credentials.provision(workspace, principal, agent, role, 86400)
        credential = root / (name + '.token')
        with credential.open('x', encoding='utf-8') as stream:
            stream.write(token)
        write_json(root / (name + '.json'), {'port': port, 'workspace': workspace,
                   'project': 'default', 'token_file': str(credential)})
    write_json(root / 'connection.json', {'schema': 1, 'mode': mode,
        'model_credentials': 'owned and configured by user in their existing runtime',
        'model_fallback': 'none', 'provider_requests_by_control_plane': False,
        'operator_principal': player, 'agent_principal': player + ':agent'})
    if mode == 'openclaw':
        write_json(root / 'openclaw-mcp.json', {'mcp': {'servers': {'clawcare_team': {
            'command': sys.executable,
            'args': [str(PACKAGE / 'team_mcp.py'), '--port', str(port),
                     '--workspace', workspace, '--token-file', str(root / 'agent.token')]
        }}}})
    return root


def operator_command(profile_path, request_path):
    # Explicit human-operated CLI only. Never expose this owner profile to MCP.
    import http.client
    profile = json.loads(Path(profile_path).read_text(encoding='utf-8'))
    bridge = Bridge(profile['port'], profile['workspace'], profile['project'], profile['token_file'])
    with Path(request_path).open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Request exceeds bounds')
    body = json.loads(raw)
    if not isinstance(body, dict) or ('project_id' in body and body['project_id'] != bridge.project):
        raise ValueError('Invalid request or project mismatch')
    if body.get('operation') not in ('workspace_info', 'project_create', 'member_update'):
        body['project_id'] = bridge.project
    connection = http.client.HTTPConnection('127.0.0.1', bridge.port, timeout=15)
    try:
        connection.request('POST', f'/v1/workspaces/{bridge.workspace}/commands', json.dumps(body),
                           {'Authorization': 'Bearer ' + bridge.token, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Response exceeds bounds')
        if response.status != 200:
            raise ValueError(f'Command rejected ({response.status}); inspect state before retrying')
        return json.loads(data)
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--data-dir', required=True)
    init.add_argument('--workspace', required=True)
    init.add_argument('--player', required=True)
    init.add_argument('--port', type=int, default=8765)
    init.add_argument('--mode', choices=['openclaw', 'manual'], default='openclaw')
    command = sub.add_parser('command')
    command.add_argument('--profile', required=True)
    command.add_argument('--request', required=True, help='JSON request file; no secrets')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            root = initialize(args.data_dir, args.workspace, args.player, args.port, args.mode)
            print(f'Private ClawCare workspace created: {root}')
            print('No model key requested, read, saved or supplied. No model fallback exists.')
            print('Start team_api.py with --root pointing to that directory and the selected port.')
            print('Credentials expire in 24 hours. Keep operator.json and operator.token away from agents.')
            if args.mode == 'openclaw':
                print('Merge only the generated mcp server entry into your existing OpenClaw configuration.')
                print('Your existing model/provider configuration remains authoritative and unchanged.')
        else:
            print(json.dumps(operator_command(args.profile, args.request), indent=2))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('Setup or command failed. Check paths, permissions, API availability and credential expiry. Existing data was not replaced.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
