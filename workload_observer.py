"""Bounded, read-only Linux memory observations and an isolated artifact demo.

No resource reservation, process control, gateway access or safety guarantee.
The demo alone writes files, in its own automatically removed temporary directory.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import time


MAX_BYTES = (1 << 64) - 1
MAX_ANCESTORS = 64


def _bounded_text(path, limit):
    """Bound bytes and reject devices/FIFOs; never write a kernel interface."""
    flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('NOT_A_REGULAR_FILE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('INPUT_TOO_LARGE')
        return raw.decode('ascii')
    finally:
        os.close(fd)


def parse_memory_value(text, allow_max=False):
    """Parse a cgroup v2 byte counter. None means explicit unlimited, not unknown."""
    value = text.strip()
    if allow_max and value == 'max':
        return None
    if not re.fullmatch(r'[0-9]{1,20}', value):
        raise ValueError('INVALID_MEMORY_VALUE')
    value = int(value)
    if value > MAX_BYTES:
        raise ValueError('INVALID_MEMORY_VALUE')
    return value


def parse_meminfo(text):
    """Require genuine MemAvailable, never substitute MemFree or cached sums."""
    values = {}
    for line in text.splitlines():
        name = line.partition(':')[0]
        if name not in ('MemTotal', 'MemAvailable'):
            continue
        if name in values:
            raise ValueError('DUPLICATE_MEMINFO_FIELD')
        match = re.fullmatch(r'(MemTotal|MemAvailable):\s+([0-9]{1,20})\s+kB\s*', line)
        if not match:
            raise ValueError('INVALID_MEMINFO_FIELD')
        value = int(match[2]) * 1024
        if value > MAX_BYTES:
            raise ValueError('INVALID_MEMINFO_FIELD')
        values[name] = value
    if set(values) != {'MemTotal', 'MemAvailable'}:
        raise ValueError('MISSING_MEMINFO_FIELD')
    if not 0 <= values['MemAvailable'] <= values['MemTotal'] or not values['MemTotal']:
        raise ValueError('INCONSISTENT_MEMINFO')
    return {'total_bytes': values['MemTotal'], 'available_bytes': values['MemAvailable']}


def _absolute_path(value):
    if not value.startswith('/') or '\x00' in value or any(
            part in ('.', '..') for part in value.split('/')):
        raise ValueError('INVALID_CGROUP_PATH')
    if value.endswith(' (deleted)'):
        raise ValueError('DELETED_CGROUP')
    return PurePosixPath(value)


def _unescape_mount(value):
    escapes = {'040': ' ', '011': '\t', '012': '\n', '134': '\\'}
    if re.search(r'\\(?!040|011|012|134)', value):
        raise ValueError('INVALID_MOUNT_ESCAPE')
    return re.sub(r'\\(040|011|012|134)', lambda match: escapes[match[1]], value)


def discover_cgroup(cgroup_text, mountinfo_text):
    """Resolve self membership against a covering v2 mount, with no path guessing."""
    entries = [line[3:] for line in cgroup_text.splitlines() if line.startswith('0::')]
    if len(entries) != 1:
        raise ValueError('CGROUP_V2_MEMBERSHIP_UNAVAILABLE')
    member = _absolute_path(entries[0])
    candidates = []
    for line in mountinfo_text.splitlines():
        before, separator, after = line.partition(' - ')
        if not separator or after.split()[:1] != ['cgroup2']:
            continue
        fields = before.split()
        if len(fields) < 6:
            raise ValueError('INVALID_CGROUP_MOUNT')
        root = _absolute_path(_unescape_mount(fields[3]))
        mount = _absolute_path(_unescape_mount(fields[4]))
        try:
            relative = member.relative_to(root)
        except ValueError:
            continue
        candidates.append((len(root.parts), str(mount), root, relative))
    if not candidates:
        raise ValueError('CGROUP_V2_MOUNT_UNAVAILABLE')
    # Prefer the widest visible ancestry; equivalent bind mounts are harmless.
    _, mount, root, relative = sorted(candidates, key=lambda row: row[:2])[0]
    mount = Path(mount)
    leaf = mount.joinpath(*relative.parts)
    return {'member': str(member), 'mount_root': str(root), 'mount': str(mount),
            'leaf': str(leaf)}


class LinuxMemoryObserver:
    """Observe this process's namespace, never an arbitrary worker's namespace.

    A non-default proc_root is for deterministic fixture tests and is labeled
    synthetic. The default reads real Linux interfaces and is labeled false.
    Missing root memory interfaces deliberately remain unknown, including on
    systems where their absence is normal; absence never proves no limit.
    """
    def __init__(self, proc_root='/proc', clock=time.time):
        self.proc_root = Path(proc_root)
        self.clock = clock
        # Normalize separators so Windows does not classify the default as a fixture.
        self.synthetic = self.proc_root.as_posix() != '/proc'

    def collect(self):
        started = time.monotonic()
        observed_at = self.clock()
        result = {'synthetic': self.synthetic, 'source': 'fixture_paths' if self.synthetic else 'linux_procfs',
                  'observed_at': observed_at, 'status': 'unknown', 'scope': 'unknown',
                  'available_bytes': None, 'total_bytes': None,
                  'host': {'status': 'unknown'}, 'cgroup': {'status': 'unknown'},
                  'errors': [], 'safety_guarantee': False}
        if type(observed_at) not in (int, float) or not math.isfinite(observed_at) or observed_at < 0:
            result['observed_at'] = None
            result['errors'].append('INVALID_CLOCK')
        if not self.synthetic and not sys.platform.startswith('linux'):
            result['errors'].append('UNSUPPORTED_PLATFORM')
            result['collection_seconds'] = time.monotonic() - started
            return result
        try:
            result['host'] = dict(status='observed', **parse_meminfo(
                _bounded_text(self.proc_root / 'meminfo', 128 * 1024)))
        except (OSError, ValueError, UnicodeError):
            result['errors'].append('HOST_MEMORY_UNAVAILABLE_OR_INVALID')
        try:
            membership = _bounded_text(self.proc_root / 'self/cgroup', 16 * 1024)
            mounts = _bounded_text(self.proc_root / 'self/mountinfo', 512 * 1024)
            location = discover_cgroup(membership, mounts)
            group = dict(status='unknown', **location, ancestors=[], ancestry_visibility='visible_mount_only')
            result['cgroup'] = group
            leaf, mount = Path(location['leaf']), Path(location['mount'])
            paths = [leaf]
            while paths[-1] != mount:
                if len(paths) >= MAX_ANCESTORS:
                    raise ValueError('CGROUP_ANCESTRY_TOO_DEEP')
                paths.append(paths[-1].parent)
            for path in paths:
                current = parse_memory_value(_bounded_text(path / 'memory.current', 128))
                limit = parse_memory_value(_bounded_text(path / 'memory.max', 128), allow_max=True)
                group['ancestors'].append({'path': str(path), 'current_bytes': current,
                                           'max_bytes': limit, 'unlimited': limit is None,
                                           'headroom_bytes': None if limit is None else max(0, limit - current)})
            # Migration/remount during sampling invalidates the combined evidence.
            if (membership != _bounded_text(self.proc_root / 'self/cgroup', 16 * 1024) or
                    mounts != _bounded_text(self.proc_root / 'self/mountinfo', 512 * 1024)):
                raise ValueError('CGROUP_LOCATION_CHANGED')
            group['status'] = 'observed'
        except (OSError, ValueError, UnicodeError):
            result['errors'].append('CGROUP_MEMORY_UNAVAILABLE_OR_INVALID')
        if not result['errors']:
            finite = [entry for entry in result['cgroup']['ancestors'] if not entry['unlimited']]
            total = min([result['host']['total_bytes']] + [entry['max_bytes'] for entry in finite])
            available = min([result['host']['available_bytes']] + [entry['headroom_bytes'] for entry in finite])
            if total <= 0:
                result['errors'].append('ZERO_VISIBLE_CAPACITY')
            else:
                result.update(status='observed', scope='host_and_visible_cgroup_v2',
                              total_bytes=total, available_bytes=min(total, available))
        result['collection_seconds'] = time.monotonic() - started
        return result


def submit_memory_observation(engine, observation):
    """Forward unknown too, so a failed read cannot leave old evidence usable.

    This explicit adapter records observations only; it does not authorize or
    dispatch any workload. Keep the full observation as provenance separately.
    """
    known = observation.get('status') == 'observed'
    return engine.observe_memory(observation.get('observed_at'),
                                 observation.get('available_bytes') if known else None,
                                 observation.get('total_bytes') if known else None)


def run_bounded_demo(items=3, item_bytes=4096, observer=None):
    """Real tiny local work, verified separately by reading each written artifact.

    Never stress memory or launch/terminate processes. The observer does not
    govern this deliberately tiny test; UNKNOWN is recorded without pretending
    a protected workload was admitted. This is not a production workload trial.
    """
    if type(items) is not int or not 1 <= items <= 16:
        raise ValueError('items must be 1..16')
    if type(item_bytes) is not int or not 1 <= item_bytes <= 65536:
        raise ValueError('item_bytes must be 1..65536')
    observer = observer or LinuxMemoryObserver()
    events = []
    with tempfile.TemporaryDirectory(prefix='clawcare-observer-') as directory:
        for index in range(items):
            payload = bytes([index]) * item_bytes
            expected = hashlib.sha256(payload).hexdigest()
            path = Path(directory) / ('item-%02d.bin' % index)
            with path.open('xb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            del payload
            # A separate read/hash validates bytes; a heartbeat or existence
            # check by itself is never counted as a completed unit.
            with path.open('rb') as source:
                actual = source.read(item_bytes + 1)
            verified = len(actual) == item_bytes and hashlib.sha256(actual).hexdigest() == expected
            if not verified:
                raise RuntimeError('ARTIFACT_VERIFICATION_FAILED')
            del actual
            events.append({'synthetic': False, 'kind': 'artifact_verified',
                           'progress_seq': index + 1, 'item': path.name,
                           'bytes_verified': item_bytes, 'sha256': expected,
                           'memory': observer.collect()})
    return {'synthetic': False, 'workload': 'isolated_temporary_artifact_demo',
            'items_verified': items, 'temporary_artifacts_removed': True,
            'memory_governed': False, 'production_safety_demonstrated': False,
            'events': events}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='write and verify a tiny temporary workload')
    parser.add_argument('--items', type=int, default=3, help='demo items (1..16), 4096 bytes each')
    args = parser.parse_args(argv)
    if not 1 <= args.items <= 16:
        parser.error('--items must be 1..16')
    if args.items != 3 and not args.demo:
        parser.error('--items requires --demo')
    result = run_bounded_demo(args.items) if args.demo else LinuxMemoryObserver().collect()
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
