#!/usr/bin/env python3
"""
Automatic WhatsApp (Gallabox) to new accounts that did not pay — Samer 26/11/2026.

Replaces the dashboard's own reminder (Gallabox templates pending_payment_male/female, full Latin name, two buttons)
with two plain messages that use the first name:
  • TRIED  — a subscription that is not Paid (Pending/Canceled/Expired), ~TRIED_MIN (35) min after it was created
             → factive_paylist_tried_m / _f («شفت إنك حاولت تشترك وما اكتملت عملية الدفع…»).
  • ACCT   — an account with no subscription at all, ACCT_MIN (60) min after it was created
             → factive_paylist_acct_m / _f («شفت إنك سويت حساب بموقعنا وما كملت اشتراكك…»).
Skipped: paid since, deleted/test accounts, no phone, US numbers (+1, Meta blocks marketing there),
and Latin names we cannot write in Arabic (names_ar.json) — those stay for customer service in «لم يكمل الدفع».
One message of each kind per person per KEEP_DAYS (7) days.

State: .paysend-state.json = {hmac(kind:client_id): sent_at}, kept between runs in the Actions cache (never committed).
The HMAC key is the GATEWAY_KEY secret, so the file holds no ids, names or numbers.
Catch-up window: WINDOW_MIN (120) min, so a missed run is picked up by the next one.

PRIVACY: this repository and its logs are public. Prints counts only — never a name, phone or e-mail.
Secrets: DASH_EMAIL, DASH_PASSWORD, GATEWAY_KEY, GB_API_KEY, GB_API_SECRET, GB_CHANNEL_ID.
Switches (repo variables): PAYSEND_TRIED, PAYSEND_ACCT ('1' = send). Standard library only.
"""
import os, sys, json, re, hmac, hashlib, datetime, urllib.request, urllib.error
from pathlib import Path

import paylist as P            # login(), pages(), when(), digits(), is_test(), first_name()

TRIED_MIN = int(os.environ.get('PAYSEND_TRIED_MIN', '35'))
ACCT_MIN = int(os.environ.get('PAYSEND_ACCT_MIN', '60'))
WINDOW_MIN = int(os.environ.get('PAYSEND_WINDOW_MIN', '120'))
KEEP_DAYS = 7
# When the dashboard's old reminder templates were deleted (repo variable PAYSEND_OLD_OFF, ISO time). A dashboard
# reminder recorded before this moment really went out, so that attempt gets no second message from us.
OLD_OFF = datetime.datetime.fromisoformat(os.environ.get('PAYSEND_OLD_OFF') or '2100-01-01T00:00:00+00:00')
DRY = '--dry-run' in sys.argv
STATE = Path(os.environ.get('PAYSEND_STATE', '.paysend-state.json'))
GB_API = 'https://server.gallabox.com/devapi'
NAMES_URL = 'https://sam96sd.github.io/WhatsAppSendingTool/names_ar.json'
TPL = {('tried', 'M'): 'factive_paylist_tried_m', ('tried', 'F'): 'factive_paylist_tried_f',
       ('acct', 'M'): 'factive_paylist_acct_m', ('acct', 'F'): 'factive_paylist_acct_f'}
AR = re.compile(r'[؀-ۿ]')


def on(kind):
    return os.environ.get('PAYSEND_' + kind.upper(), '0').strip() == '1'


# ----------------------------------------------------------------------------- names (same rules as gallabox.first_name_ar)
_NAMES, _FAM = None, set()


def names():
    global _NAMES, _FAM
    if _NAMES is None:
        try:
            raw = json.loads(urllib.request.urlopen(NAMES_URL, timeout=30).read().decode('utf-8'))
        except Exception:
            raw = {}
        _NAMES = {k.lower(): v for k, v in raw.items() if not k.startswith('_')}
        _FAM = {re.sub(r'[^a-z0-9]', '', str(x).lower()) for x in raw.get('_عائلات', [])}
    return _NAMES


def key(tok):
    return re.sub(r'[^a-z0-9]', '', tok.lower())


def is_family(tok):
    names(); k = key(tok)
    return k not in _NAMES and (k in _FAM or (len(k) > 5 and k[:2] in ('al', 'el')))


def arabic_first(c, female):
    """Arabic first name for the template, or '' (→ not sent automatically)."""
    fn = P.first_name(c)
    if AR.search(fn):
        return fn
    parts = re.sub(r'\s+', ' ', str(c.get('full_name') or c.get('first_name') or '')).strip().split(' ')
    parts = [p for p in parts if p]
    if not parts:
        return ''
    tok = parts[0]
    if is_family(tok) and len(parts) > 1:
        tok = parts[1]
        if AR.search(tok):
            return tok
    if key(tok) in ('alaa', 'ala2', 'alaa2'):
        return 'آلاء' if female else 'علاء'
    return names().get(key(tok), '')


# ----------------------------------------------------------------------------- state
def load_state(now):
    try:
        st = json.loads(STATE.read_text(encoding='utf-8'))
    except Exception:
        st = {}
    old = now - datetime.timedelta(days=KEEP_DAYS)
    return {k: v for k, v in st.items() if P.when(v) >= old}


def save_state(st):
    if not DRY:
        STATE.write_text(json.dumps(st, sort_keys=True), encoding='utf-8')


def mark(kind, cid):
    return hmac.new(os.environ['GATEWAY_KEY'].encode(), f'{kind}:{cid}'.encode(), hashlib.sha256).hexdigest()[:24]


# ----------------------------------------------------------------------------- gallabox
def gb_send(tpl, name, phone, fn):
    body = {'channelId': os.environ['GB_CHANNEL_ID'], 'channelType': 'whatsapp',
            'recipient': {'name': name or fn, 'phone': phone},
            'whatsapp': {'type': 'template', 'template': {'templateName': tpl, 'bodyValues': {'first_name': fn}}}}
    req = urllib.request.Request(GB_API + '/messages/whatsapp', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'apiKey': os.environ['GB_API_KEY'], 'apiSecret': os.environ['GB_API_SECRET'],
                                          'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status in (200, 201, 202)
    except urllib.error.HTTPError as e:
        print('gallabox http', e.code)            # status code only
        return False


# ----------------------------------------------------------------------------- main
def self_test():
    """--test-self: send the «account only» men's template once to Samer's own number (secret PAYSEND_TEST_PHONE)."""
    ok = gb_send(TPL[('acct', 'M')], 'SAMER SAAD', P.digits(os.environ['PAYSEND_TEST_PHONE']), 'سامر')
    print('test send:', 'accepted' if ok else 'FAILED')
    return 0 if ok else 1


def main():
    if '--test-self' in sys.argv:
        return self_test()
    now = datetime.datetime.now(datetime.timezone.utc)
    st = load_state(now)
    tok = P.login()
    oldest = now - datetime.timedelta(minutes=max(TRIED_MIN, ACCT_MIN) + WINDOW_MIN + 60)
    clients = P.pages(tok, 'clients', oldest)
    subs = P.pages(tok, 'subscriptions', oldest)
    by = {}
    for s in subs:
        by.setdefault(str(s.get('client_id')), []).append(s)

    todo = []                                    # (kind, client_id, client dict)
    # TRIED: newest unpaid subscription per client, created TRIED_MIN..TRIED_MIN+WINDOW_MIN ago, nothing paid since
    lo, hi = now - datetime.timedelta(minutes=TRIED_MIN + WINDOW_MIN), now - datetime.timedelta(minutes=TRIED_MIN)
    seen, n_old = set(), 0
    for s in sorted(subs, key=lambda s: P.when(s.get('created_at')), reverse=True):
        cid = str(s.get('client_id'))
        if s.get('payment_status') == 'Paid' or cid in seen or not (lo <= P.when(s.get('created_at')) <= hi):
            continue
        seen.add(cid)
        t0 = P.when(s.get('created_at')) - datetime.timedelta(minutes=1)
        if any(x.get('payment_status') == 'Paid' and P.when(x.get('created_at')) >= t0 for x in by.get(cid, [])):
            continue
        # the dashboard's own reminder (old templates pending_payment_*) went out before they were deleted → not again
        if s.get('whatsapp_payment_reminder_sent_at') and P.when(s.get('whatsapp_payment_reminder_sent_at')) < OLD_OFF:
            n_old += 1; continue
        todo.append(('tried', cid, s.get('client_info') or {}))
    # ACCT: account created ACCT_MIN..ACCT_MIN+WINDOW_MIN ago with no subscription at all
    lo, hi = now - datetime.timedelta(minutes=ACCT_MIN + WINDOW_MIN), now - datetime.timedelta(minutes=ACCT_MIN)
    for c in clients:
        cid = str(c.get('_id'))
        if lo <= P.when(c.get('created_at')) <= hi and not by.get(cid):
            todo.append(('acct', cid, c))

    n = {k: 0 for k in ('due', 'already', 'test', 'nophone', 'us', 'noname', 'off', 'sent', 'failed')}
    per = {'tried': 0, 'acct': 0}
    for kind, cid, c in todo:
        n['due'] += 1
        m = mark(kind, cid)
        if m in st:
            n['already'] += 1; continue
        if P.is_test(c):
            n['test'] += 1; continue
        ph = P.digits(c.get('mobile_number'))
        if len(ph) < 8:
            n['nophone'] += 1; continue
        if ph.startswith('1') and len(ph) == 11:
            n['us'] += 1; continue
        female = str((c.get('personal_info') or {}).get('gender') or '').lower() == 'female'
        fn = arabic_first(c, female)
        if not fn:
            n['noname'] += 1; continue
        if DRY:
            per[kind] += 1; continue
        if not on(kind):
            n['off'] += 1; continue
        if gb_send(TPL[(kind, 'F' if female else 'M')], c.get('full_name') or fn, ph, fn):
            st[m] = now.isoformat(); save_state(st)        # saved after every send, so a crash can't cause a repeat
            n['sent'] += 1; per[kind] += 1
        else:
            n['failed'] += 1
    save_state(st)
    print('switches: tried=%s acct=%s' % (on('tried'), on('acct')))
    print('tried already reminded by the dashboard:', n_old)
    print(' · '.join(f'{k}: {v}' for k, v in n.items()) + f' · tried: {per["tried"]} · acct: {per["acct"]}'
          + (' (dry run: would send)' if DRY else ''))
    return 1 if n['failed'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as ex:
        print('error:', type(ex).__name__)          # type only — the log is public
        sys.exit(1)
