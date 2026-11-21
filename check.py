#!/usr/bin/env python3
"""
Instant waitlist check (public repo, so GitHub Actions minutes are free).

Every 5 minutes: is there anyone who registered on the waitlist at least LAG_MIN minutes ago, after the last
successful run of the private workflow, and who has NOT messaged us on WhatsApp yet? If so, start the private
workflow «Factive Daily List» with slot=live, which applies every rule and sends the Gallabox template.

PRIVACY: this repository and its logs are public. This script prints counts only — never a name, phone or row.
Data comes from the private sheet gateway; the URL, key and GitHub token are repository secrets.
Secrets: GATEWAY_URL, GATEWAY_KEY, GH_TOKEN (fine-grained, Actions read+write on the private repo only).
Standard library only (no pip step → shorter run).
"""
import os, sys, json, re, datetime, urllib.request, urllib.parse

PRIVATE_REPO = 'Sam96sd/factive-daily-cloud'
WORKFLOW = 'daily.yml'
LAG_MIN = 10          # give the person time to press the WhatsApp button themselves
GAP_MIN = 20          # at most one private run per 20 minutes (its minutes are limited)
KW = datetime.timezone(datetime.timedelta(hours=3))


def http(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8')


def gh(path, body=None):
    h = {'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
         'X-GitHub-Api-Version': '2022-11-28'}
    data = None
    if body is not None:
        data = json.dumps(body).encode(); h['Content-Type'] = 'application/json'
    st, txt = http('https://api.github.com/repos/' + PRIVATE_REPO + path, data, h)
    return st, (json.loads(txt) if txt.strip() else {})


def gateway(mode, **params):
    q = urllib.parse.urlencode({'key': os.environ['GATEWAY_KEY'], 'mode': mode, **params})
    st, txt = http(os.environ['GATEWAY_URL'] + '?' + q, timeout=90)
    j = json.loads(txt)
    if 'error' in j:
        raise RuntimeError('gateway ' + mode + ' returned an error')
    return j.get('rows', [])


def parse_ts(s):
    s = str(s or '').strip()
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.datetime.strptime(s[:19], fmt).replace(tzinfo=KW)
        except ValueError:
            pass
    return None


def iso(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))


def main():
    now = datetime.datetime.now(KW)
    _, runs = gh(f'/actions/workflows/{WORKFLOW}/runs?per_page=10')
    runs = runs.get('workflow_runs', [])
    if any(r['status'] in ('queued', 'in_progress', 'waiting', 'pending', 'requested') for r in runs):
        print('a private run is already queued or running — nothing to do'); return 0
    if runs and now - iso(runs[0]['created_at']) < datetime.timedelta(minutes=GAP_MIN):
        print(f'last private run started less than {GAP_MIN} min ago — next check'); return 0
    # dry runs never move the private cursor, so they don't count. The private run-name carries the slot:
    # live runs take rows at least 10 min old at their start, the 09:00/14:00/20:00 batches 30 min.
    ok = [r for r in runs if r.get('conclusion') == 'success' and 'dry run' not in (r.get('display_title') or '')]
    if ok:
        lag = LAG_MIN if '(live' in (ok[0].get('display_title') or '') else 30
        since = iso(ok[0]['created_at']).astimezone(KW) - datetime.timedelta(minutes=lag)
    else:
        since = now - datetime.timedelta(hours=3)
    since = max(since, now - datetime.timedelta(hours=6))
    edge = now - datetime.timedelta(minutes=LAG_MIN)
    rows = gateway('rows', since=since.strftime('%Y-%m-%d %H:%M:%S'), tail=400)
    ready = []
    for r in rows:
        ts = parse_ts(r[0] if r else '')
        if ts and since < ts <= edge:
            ready.append(re.sub(r'\D', '', str(r[2] if len(r) > 2 else ''))[-8:])
    waiting = sum(1 for r in rows if (parse_ts(r[0] if r else '') or now) > edge)
    if not ready:
        print(f'nobody new old enough (waiting under {LAG_MIN} min: {waiting})'); return 0
    replied = set()
    for r in gateway('replies', days=1):
        l8 = re.sub(r'\D', '', str(r[1] if len(r) > 1 else ''))[-8:] or str(r[2] if len(r) > 2 else '')
        if l8: replied.add(l8)
    fresh = sum(1 for p in ready if p and p not in replied)
    print(f'new registrants: {len(ready)} · already messaged us: {len(ready) - fresh} · to message: {fresh}')
    if not fresh:
        return 0
    st, _ = gh(f'/actions/workflows/{WORKFLOW}/dispatches', {'ref': 'main', 'inputs': {'slot': 'live'}})
    print(f'private run started (HTTP {st})')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:                      # type only: an error message could contain data
        print(f'check failed: {type(e).__name__}')
        sys.exit(1)
