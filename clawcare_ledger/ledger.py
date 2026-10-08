from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$')


def identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError('Use an opaque non-secret identifier, not a URL or free text')
    return value


def canonical(value) -> str:
    # Dictionary order is immaterial; list order, case, and string whitespace are
    # meaningful. Do not guess whether a provider considers two queries equivalent.
    def check(v):
        if isinstance(v, dict):
            if any(not isinstance(k, str) for k in v):
                raise ValueError('JSON object keys must be strings')
            for x in v.values(): check(x)
        elif isinstance(v, list):
            for x in v: check(x)
        elif v is not None and type(v) not in (str, int, float, bool):
            raise ValueError('Only JSON values are supported')
    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError('Expected a finite nonnegative number')
    return value


@dataclass(frozen=True)
class Scope:
    tenant: str
    account: str
    access_context: str
    permission_revision: str

    def key(self):
        return digest({k: identifier(v) for k, v in asdict(self).items()})


@dataclass(frozen=True)
class Actor:
    agent: str
    device: str
    work_order: str

    def data(self):
        return {k: identifier(v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class Lookup:
    provider: str
    operation: str
    adapter_version: str
    parameters: dict

    def key(self, scope: Scope):
        if not isinstance(self.parameters, dict):
            raise ValueError('parameters must be an object')
        return digest({'version': 1, 'scope': scope.key(),
                       'provider': identifier(self.provider),
                       'operation': identifier(self.operation),
                       'adapter': identifier(self.adapter_version), 'parameters': self.parameters})


@dataclass(frozen=True)
class Evidence:
    reference: str
    origin: str
    source_fingerprint: str
    content_sha256: str
    observed_at: float

    @classmethod
    def from_source(cls, reference, source_url, content_sha256, observed_at):
        # Persist only the origin and a one-way fingerprint. Even URL paths can
        # carry secrets. Userinfo, query, fragment, and path are never retained.
        url = urlsplit(source_url)
        if url.scheme != 'https' or not url.hostname:
            raise ValueError('Evidence source must be HTTPS')
        host = url.hostname.lower()
        origin = 'https://' + ('[' + host + ']' if ':' in host else host)
        if url.port and url.port != 443: origin += ':' + str(url.port)
        return cls(identifier(reference), origin, hashlib.sha256(source_url.encode()).hexdigest(), content_sha256, observed_at)

    def data(self):
        identifier(self.reference)
        url = urlsplit(self.origin)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError('Only HTTPS origins can be persisted')
        for hash_value in (self.source_fingerprint, self.content_sha256):
            if not re.fullmatch('[0-9a-f]{64}', hash_value): raise ValueError('Expected SHA-256')
        url.port  # Validate malformed/out-of-range ports
        number(self.observed_at)
        return asdict(self)


@dataclass(frozen=True)
class Claim:
    state: str
    lookup_key: str
    action_id: str | None = None
    execution_token: str | None = None
    result: dict | None = None
    lease_expires_at: float | None = None
    lease_expired: bool = False


class Conflict(RuntimeError):
    pass


class Ledger:
    """SQLite single-host coordination. Never use a copied DB as shared state."""

    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = str(path)
        if not self.path or self.path == ':memory:': raise ValueError('Use a persistent database path')
        self.clock = clock
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if Path(self.path).is_symlink(): raise ValueError('Database symlinks are not supported')
        else:
            os.close(fd)
        with self._db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (version INTEGER NOT NULL);
            INSERT INTO metadata SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM metadata);
            CREATE TABLE IF NOT EXISTS actions (
              id TEXT PRIMARY KEY, scope TEXT NOT NULL, lookup_key TEXT NOT NULL,
              provider TEXT NOT NULL, operation TEXT NOT NULL, adapter TEXT NOT NULL,
              actor TEXT NOT NULL, state TEXT NOT NULL, token_hash TEXT NOT NULL,
              started REAL NOT NULL, lease_until REAL NOT NULL, finished REAL,
              outcome_code TEXT, credits REAL, billing TEXT NOT NULL DEFAULT 'unknown',
              completion_hash TEXT, billing_revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS billing_receipts (
              scope TEXT NOT NULL, receipt_id TEXT NOT NULL, action_id TEXT NOT NULL,
              credits REAL NOT NULL, PRIMARY KEY(scope,receipt_id));
            CREATE UNIQUE INDEX IF NOT EXISTS one_pending ON actions(scope, lookup_key) WHERE state='pending';
            CREATE TABLE IF NOT EXISTS results (
              id TEXT PRIMARY KEY, scope TEXT NOT NULL, lookup_key TEXT NOT NULL,
              action_id TEXT NOT NULL, result_ref TEXT NOT NULL, evidence TEXT NOT NULL,
              created REAL NOT NULL, expires REAL NOT NULL,
              result_kind TEXT NOT NULL, derived_from TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS result_lookup ON results(scope, lookup_key, created DESC);
            CREATE TABLE IF NOT EXISTS events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL,
              lookup_key TEXT NOT NULL, action_id TEXT, kind TEXT NOT NULL,
              at REAL NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL);
            ''')
            if db.execute('SELECT version FROM metadata').fetchone()[0] != 1:
                raise RuntimeError('Unsupported ledger schema version')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA busy_timeout=30000')
            yield db
        finally: db.close()

    @contextmanager
    def _transaction(self, *, write=True):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def _event(self, db, scope, key, action, kind, actor, details=None):
        db.execute('INSERT INTO events(scope,lookup_key,action_id,kind,at,actor,details) VALUES(?,?,?,?,?,?,?)',
                   (scope, key, action, kind, self.clock(), canonical(actor.data()), canonical(details or {})))

    def _view(self, db, scope, key, now=None):
        action = db.execute('SELECT * FROM actions WHERE scope=? AND lookup_key=? ORDER BY rowid DESC LIMIT 1', (scope, key)).fetchone()
        row = db.execute('SELECT * FROM results WHERE scope=? AND lookup_key=? ORDER BY rowid DESC LIMIT 1', (scope, key)).fetchone()
        if now is None: now = self.clock()
        result = None
        if row:
            result = {k: row[k] for k in ('id', 'action_id', 'result_ref', 'created', 'expires', 'result_kind')}
            result['evidence'] = json.loads(row['evidence'])
            result['derived_from'] = json.loads(row['derived_from'])
            result['fresh'] = now < row['expires']
        if action and action['state'] == 'pending':
            return Claim('pending', key, action['id'], result=result, lease_expires_at=action['lease_until'], lease_expired=now >= action['lease_until'])
        # A failed refresh is a visible failure, even if an old result exists.
        if action and action['state'] == 'failed': return Claim('failed', key, action['id'], result=result)
        if result: return Claim('cached_fresh' if result['fresh'] else 'cached_stale', key, row['action_id'], result=result)
        return Claim('missing', key)

    def inspect(self, scope: Scope, lookup: Lookup):
        with self._transaction(write=False) as db:
            return self._view(db, scope.key(), lookup.key(scope))

    def claim(self, scope: Scope, lookup: Lookup, actor: Actor, *, refresh=False, retry_failed=False, lease_seconds=300):
        number(lease_seconds, positive=True)
        sk, key = scope.key(), lookup.key(scope)
        actor.data()
        with self._transaction() as db:
            now = self.clock()
            view = self._view(db, sk, key, now)
            if view.state == 'pending':
                self._event(db, sk, key, view.action_id, 'inflight_join', actor)
                return view
            if view.state == 'cached_fresh' and not refresh:
                self._event(db, sk, key, view.action_id, 'cache_hit', actor)
                return view
            if view.state == 'failed' and not retry_failed:
                self._event(db, sk, key, view.action_id, 'failure_seen', actor)
                return view
            aid, token = secrets.token_hex(16), secrets.token_hex(32)
            db.execute('''INSERT INTO actions(id,scope,lookup_key,provider,operation,adapter,actor,state,token_hash,started,lease_until)
                          VALUES(?,?,?,?,?,?,?,'pending',?,?,?)''',
                       (aid, sk, key, lookup.provider, lookup.operation, lookup.adapter_version, canonical(actor.data()),
                        hashlib.sha256(token.encode()).hexdigest(), now, now + lease_seconds))
            self._event(db, sk, key, aid, 'execution_claimed', actor, {'refresh': bool(refresh), 'retry_failed': bool(retry_failed)})
            return Claim('pending', key, aid, token, view.result, now + lease_seconds)

    def _owned(self, db, scope, action_id, token):
        row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (scope.key(), action_id)).fetchone()
        if not row or not secrets.compare_digest(row['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            raise Conflict('Unknown action or invalid ownership')
        return row

    def renew(self, scope, action_id, token, actor, *, lease_seconds=300):
        number(lease_seconds, positive=True)
        with self._transaction() as db:
            row = self._owned(db, scope, action_id, token)
            if row['state'] != 'pending': raise Conflict('Action already finished')
            db.execute('UPDATE actions SET lease_until=? WHERE id=?', (self.clock() + lease_seconds, action_id))
            self._event(db, scope.key(), row['lookup_key'], action_id, 'lease_renewed', actor)

    def complete(self, scope, action_id, token, actor, *, result_ref, evidence, ttl_seconds, credits=None, result_kind='structured', derived_from=()):
        identifier(result_ref)
        if result_kind not in ('full_page', 'derived_answer', 'structured', 'search_results'):
            raise ValueError('Unsupported result kind')
        derived_from = [identifier(ref) for ref in derived_from]
        number(ttl_seconds)
        if credits is not None: number(credits)
        evidence_data = [e.data() for e in evidence]
        if not evidence_data: raise ValueError('A reusable result needs evidence provenance')
        payload = {'result_ref': result_ref, 'evidence': evidence_data, 'ttl_seconds': ttl_seconds, 'credits': credits, 'result_kind': result_kind, 'derived_from': derived_from}
        fingerprint = digest(payload)
        with self._transaction() as db:
            row = self._owned(db, scope, action_id, token)
            if row['state'] != 'pending':
                if row['state'] == 'succeeded' and row['completion_hash'] == fingerprint:
                    self._event(db, scope.key(), row['lookup_key'], action_id, 'completion_replayed', actor)
                    return db.execute('SELECT id FROM results WHERE action_id=?', (action_id,)).fetchone()[0]
                raise Conflict('Conflicting or fenced completion')
            now, rid = self.clock(), secrets.token_hex(16)
            if any(e['observed_at'] > now for e in evidence_data):
                raise ValueError('Evidence cannot be observed in the future')
            expires = min(e['observed_at'] for e in evidence_data) + ttl_seconds
            db.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (rid, scope.key(), row['lookup_key'], action_id, result_ref, canonical(evidence_data), now, expires, result_kind, canonical(derived_from)))
            db.execute("UPDATE actions SET state='succeeded',finished=?,outcome_code='ok',credits=?,billing=?,completion_hash=? WHERE id=?",
                       (now, credits, 'reported' if credits is not None else 'unknown', fingerprint, action_id))
            self._event(db, scope.key(), row['lookup_key'], action_id, 'succeeded', actor, {'result_id': rid})
            return rid

    def fail(self, scope, action_id, token, actor, *, code, credits=None):
        identifier(code)
        if credits is not None: number(credits)
        fingerprint = digest({'code': code, 'credits': credits})
        with self._transaction() as db:
            row = self._owned(db, scope, action_id, token)
            if row['state'] != 'pending':
                if row['state'] == 'failed' and row['completion_hash'] == fingerprint: return
                raise Conflict('Conflicting or fenced failure')
            db.execute("UPDATE actions SET state='failed',finished=?,outcome_code=?,credits=?,billing=?,completion_hash=? WHERE id=?",
                       (self.clock(), code, credits, 'reported' if credits is not None else 'unknown', fingerprint, action_id))
            self._event(db, scope.key(), row['lookup_key'], action_id, 'failed', actor, {'code': code})

    def abandon_expired(self, scope, lookup, actor):
        """Explicit reconciliation only. Expiry does NOT prove no provider charge."""
        with self._transaction() as db:
            view = self._view(db, scope.key(), lookup.key(scope), self.clock())
            if view.state != 'pending' or not view.lease_expired: raise Conflict('No expired action')
            db.execute("UPDATE actions SET state='failed',finished=?,outcome_code='abandoned_unknown' WHERE id=?", (self.clock(), view.action_id))
            self._event(db, scope.key(), view.lookup_key, view.action_id, 'abandoned_unknown', actor)

    def reconcile_billing(self, scope, action_id, actor, *, receipt_id, credits, expected_revision):
        """Record authoritative total credits for one action, never an increment.

        Call only from a trusted billing adapter with a stable redacted receipt ID.
        This does not turn a failed/abandoned result into a reusable success.
        """
        identifier(receipt_id)
        number(credits)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Expected a nonnegative integer revision')
        with self._transaction() as db:
            sk = scope.key()
            receipt = db.execute('SELECT * FROM billing_receipts WHERE scope=? AND receipt_id=?', (sk, receipt_id)).fetchone()
            if receipt:
                if receipt['action_id'] == action_id and receipt['credits'] == credits: return
                raise Conflict('Receipt was already used with different data')
            row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (sk, action_id)).fetchone()
            if not row or row['state'] == 'pending' or row['billing_revision'] != expected_revision:
                raise Conflict('Unknown, pending, or concurrently reconciled action')
            db.execute('INSERT INTO billing_receipts VALUES(?,?,?,?)', (sk, receipt_id, action_id, credits))
            db.execute("UPDATE actions SET credits=?,billing='reported',billing_revision=billing_revision+1 WHERE id=?", (credits, action_id))
            self._event(db, sk, row['lookup_key'], action_id, 'billing_reconciled', actor,
                        {'receipt_id': receipt_id, 'previous_credits': row['credits'], 'credits': credits,
                         'revision': expected_revision + 1})

    def dashboard(self, scope: Scope):
        """Caller MUST authenticate and derive scope server-side before calling."""
        with self._transaction(write=False) as db:
            rows = db.execute('SELECT * FROM actions WHERE scope=? ORDER BY rowid', (scope.key(),)).fetchall()
            actions = []
            for row in rows:
                action = {k: row[k] for k in ('id', 'lookup_key', 'provider', 'operation', 'adapter', 'state', 'started', 'finished', 'lease_until', 'outcome_code', 'credits', 'billing', 'billing_revision')}
                action['actor'] = json.loads(row['actor'])
                actions.append(action)
            events = []
            for row in db.execute('SELECT * FROM events WHERE scope=? ORDER BY sequence', (scope.key(),)):
                event = dict(row)
                del event['scope']
                event['actor'], event['details'] = json.loads(event['actor']), json.loads(event['details'])
                events.append(event)
            now = self.clock()
            views = [asdict(self._view(db, scope.key(), key, now)) for key in dict.fromkeys(a['lookup_key'] for a in actions)]
            by_provider = {}
            for a in actions:
                billing = by_provider.setdefault(a['provider'], {'reported_credits': 0, 'unknown_action_count': 0})
                billing['reported_credits'] += a['credits'] or 0
                billing['unknown_action_count'] += a['billing'] == 'unknown'
            return {'schema_version': 1, 'lookups': views, 'actions': actions, 'events': events,
                    'billing': {'by_provider': by_provider,
                                'unknown_action_count': sum(a['billing'] == 'unknown' for a in actions),
                                'currency_cost': None, 'estimated_savings': None}}
