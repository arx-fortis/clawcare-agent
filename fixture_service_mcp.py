"""Read-only local stdio MCP projection of synthetic ClawCare service evidence."""
import argparse
import json
import sqlite3
import sys

from control import Denied
from fixture_service import ReadView, strict_object

LIMIT = 65536
TOOLS = {
    'clawcare_health': {},
    'clawcare_work_order_status': {'order_id': {'type': 'string', 'maxLength': 80}},
    'clawcare_failure_records': {},
    'clawcare_workload_status': {},
}


def result(value, error=False):
    return {'content': [{'type': 'text', 'text': json.dumps(value, sort_keys=True)}], 'isError': error}


class Bridge:
    def __init__(self, view):
        self.view = view
        self.initialized = False

    def call(self, name, arguments):
        if name not in TOOLS or not isinstance(arguments, dict) or set(arguments) != set(TOOLS[name]):
            return result({'error': 'Read-only tool or arguments not permitted'}, True)
        try:
            if name == 'clawcare_health':
                value = self.view.health()
            elif name == 'clawcare_workload_status':
                value = self.view.workload_status()
            elif name == 'clawcare_failure_records':
                value = self.view.failure_records()
            else:
                value = self.view.work_order_status(arguments['order_id'])
            return result(value)
        except (Denied, ValueError, OSError, sqlite3.Error):
            return result({'error': 'Local synthetic evidence unavailable'}, True)

    def dispatch(self, request):
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request'}}
        if 'id' not in request:
            return None
        ident = request['id']
        if isinstance(ident, (dict, list, bool)):
            return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid request ID'}}
        method, params = request.get('method'), request.get('params', {})
        error, value = None, None
        if not isinstance(params, dict):
            error = {'code': -32602, 'message': 'Invalid parameters'}
        elif method == 'initialize':
            version = params.get('protocolVersion')
            if version not in ('2024-11-05', '2025-03-26', '2025-06-18'):
                version = '2025-06-18'
            self.initialized = True
            value = {'protocolVersion': version, 'capabilities': {'tools': {}},
                     'serverInfo': {'name': 'clawcare-fixture-readonly', 'version': '0.1.0-candidate'}}
        elif method == 'ping':
            value = {}
        elif not self.initialized:
            error = {'code': -32000, 'message': 'Initialize first'}
        elif method == 'tools/list':
            value = {'tools': [{'name': name,
                'description': 'Read local SYNTHETIC fixture evidence. No repair authority. Last recorded evidence is not current liveness.',
                'inputSchema': {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False},
                'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}}
                for name, fields in TOOLS.items()]}
        elif method == 'tools/call':
            name = params.get('name')
            value = self.call(name, params.get('arguments', {})) if isinstance(name, str) else result({'error': 'Invalid tool name'}, True)
        else:
            error = {'code': -32601, 'message': 'Method not supported'}
        return {'jsonrpc': '2.0', 'id': ident, **({'error': error} if error else {'result': value})}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    args = p.parse_args()
    try:
        bridge = Bridge(ReadView(args.root))
    except (Denied, OSError, ValueError):
        print('Synthetic fixture evidence unavailable.', file=sys.stderr)
        return 2
    while True:
        raw = sys.stdin.buffer.readline(LIMIT + 1)
        if not raw:
            return 0
        if len(raw) > LIMIT:
            print('Input exceeds bounds.', file=sys.stderr)
            return 2
        try:
            request = json.loads(raw, object_pairs_hook=strict_object,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            response = bridge.dispatch(request)
        except (ValueError, TypeError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON'}}
        if response is not None:
            print(json.dumps(response, allow_nan=False), flush=True)


if __name__ == '__main__':
    sys.exit(main())
