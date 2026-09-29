"""Scoped stdio MCP adapter for the local ClawCare team API (no dependencies)."""
import argparse
import http.client
import json
from pathlib import Path
import re
import sys

from team_api import strict_object

LIMIT = 65536
FIELDS = {
    'create': ['resource', 'objective', 'acceptance'],
    'inspect': ['id'],
    'claim': ['id', 'revision', 'ttl'],
    'renew': ['id', 'revision', 'session', 'ttl'],
    'progress': ['id', 'revision', 'session', 'request_id', 'report'],
    'handoff': ['id', 'revision', 'session', 'request_id', 'report'],
}


def schema(operation):
    properties = {}
    for field in FIELDS[operation]:
        properties[field] = {'type': 'string'}
        if field in ('revision', 'ttl'):
            properties[field] = {'type': 'integer', 'minimum': 0}
        if field == 'report':
            lists = ('completed', 'remaining', 'blockers', 'verification',
                     'checkpoint_refs', 'recovery_notes')
            props = {k: {'type': 'array', 'items': {'type': 'string'}} for k in lists}
            if operation == 'handoff':
                props['next_work_order'] = {'anyOf': [
                    {'type': 'null'}, {'type': 'object', 'properties': {
                        'objective': {'type': 'string'}, 'acceptance': {'type': 'string'}},
                        'required': ['objective', 'acceptance'], 'additionalProperties': False}]}
            properties[field] = {'type': 'object', 'properties': props,
                                 'required': list(props), 'additionalProperties': False}
    return {'type': 'object', 'properties': properties,
            'required': FIELDS[operation], 'additionalProperties': False}


def result(value, error=False):
    return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=True)}],
            'isError': error}


class Bridge:
    def __init__(self, port, workspace, project, token_file):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid local port')
        for slug in (workspace, project):
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', slug):
                raise ValueError('Invalid workspace or project')
        with Path(token_file).open('r', encoding='utf-8') as f:
            self.token = f.read(128).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', self.token):
            raise ValueError('Invalid credential file')
        self.port, self.workspace, self.project = port, workspace, project
        self.initialized = False

    def call(self, name, args):
        operation = name.removeprefix('clawcare_') if isinstance(name, str) else ''
        if name != 'clawcare_' + operation or operation not in FIELDS:
            return result({'error': 'Tool not permitted'}, True)
        if not isinstance(args, dict) or set(args) != set(FIELDS[operation]):
            return result({'error': 'Unexpected or missing arguments'}, True)
        body = json.dumps({**args, 'operation': operation, 'project_id': self.project},
                          allow_nan=False).encode('utf-8')
        if len(body) > LIMIT:
            return result({'error': 'Request exceeds bounds'}, True)
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            connection.request('POST', f'/v1/workspaces/{self.workspace}/commands', body,
                               {'Authorization': 'Bearer ' + self.token,
                                'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return result({'error': 'Response exceeds bounds; inspect locally'}, True)
            # Do not follow redirects or forward authorization to another endpoint.
            if response.status != 200:
                return result({'error': 'Team API rejected command', 'status': response.status,
                               'next': 'Inspect state before retrying a write'}, True)
            return result(json.loads(raw))
        except (OSError, ValueError, http.client.HTTPException):
            return result({'error': 'Team API unavailable or invalid response',
                           'next': 'Inspect state before retrying a write'}, True)
        finally:
            connection.close()

    def dispatch(self, request):
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
            return {'jsonrpc': '2.0', 'id': None,
                    'error': {'code': -32600, 'message': 'Invalid request'}}
        if 'id' not in request:
            return None
        ident = request['id']
        method, params = request.get('method'), request.get('params', {})
        error, value = None, None
        if not isinstance(params, dict):
            error = {'code': -32602, 'message': 'Invalid parameters'}
        elif method == 'initialize':
            version = params.get('protocolVersion')
            if version not in ('2024-11-05', '2025-03-26', '2025-06-18'):
                version = '2025-06-18'
            value = {'protocolVersion': version, 'capabilities': {'tools': {}},
                     'serverInfo': {'name': 'clawcare-team', 'version': '0.3.1'}}
            self.initialized = True
        elif method == 'ping':
            value = {}
        elif not self.initialized:
            error = {'code': -32000, 'message': 'Initialize first'}
        elif method == 'tools/list':
            value = {'tools': [{'name': 'clawcare_' + op,
                'description': f'{op.title()} a ClawCare work order. Coordination only; no external execution. '
                               'Record only observed evidence. Never claim approval or verification without evidence.',
                'inputSchema': schema(op)} for op in FIELDS]}
        elif method == 'tools/call':
            value = self.call(params.get('name'), params.get('arguments', {}))
        else:
            error = {'code': -32601, 'message': 'Method not supported'}
        return {'jsonrpc': '2.0', 'id': ident, **({'error': error} if error else {'result': value})}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--workspace', required=True)
    p.add_argument('--project', default='default')
    p.add_argument('--token-file', required=True)
    args = p.parse_args()
    try:
        bridge = Bridge(args.port, args.workspace, args.project, args.token_file)
    except (OSError, ValueError):
        print('ClawCare MCP configuration or credential unavailable.', file=sys.stderr)
        return 1
    while True:
        line = sys.stdin.buffer.readline(LIMIT + 1)
        if not line:
            return 0
        if len(line) > LIMIT:
            print('ClawCare MCP input exceeds bounds.', file=sys.stderr)
            return 1
        try:
            request = json.loads(line, object_pairs_hook=strict_object,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            response = bridge.dispatch(request)
        except (ValueError, TypeError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None,
                        'error': {'code': -32700, 'message': 'Invalid JSON request'}}
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main())
