#!/usr/bin/env python3
"""
«💳 لم يكمل الدفع» — customer-service list of new accounts that did not pay (Samer 26/11/2026).

Every 2 hours (cron-job.org → workflow_dispatch; GitHub cron as backup) this rebuilds ONE fixed Google Sheet
(PAYLIST_ID in the gateway's Code.gs) through the private sheet gateway (mode=upload, target=paylist):
  • who: dashboard accounts created in the last KEEP_DAYS (3) days, at least WAIT_MIN (30) minutes ago,
         with NO Paid subscription. Deleted and test accounts are skipped. Whoever pays drops out at the next run.
  • columns (مِرسال فاكتيف format): name, wa.me, phone, email, country, signed up, status, ready message, notes.
  • message: asks what problem they hit, so they reply (text approved by Samer 26/11/2026).

PRIVACY: this repository and its logs are public. This script prints counts only — never a name, phone or e-mail.
Secrets: GATEWAY_URL, GATEWAY_KEY, DASH_EMAIL, DASH_PASSWORD. Standard library only.
"""
import os, sys, json, re, datetime, urllib.request, urllib.parse, urllib.error, time

API = 'https://api.factive.app/api'
KEEP_DAYS = int(os.environ.get('PAYLIST_DAYS', '3'))
WAIT_MIN = int(os.environ.get('PAYLIST_WAIT_MIN', '30'))
KW = datetime.timezone(datetime.timedelta(hours=3))
TAB = 'لم يكمل الدفع'          # fixed: مِرسال keeps the «أرسلت» marks per file + tab + phone
DRY = '--dry-run' in sys.argv

MSG_M = ('السلام عليكم اخوي {fn} 🌹\nمعاك خالد من فريق فاكتيف للمدرب محمد المرزوق\n\n'
         'شفت إنك سويت حساب بموقعنا وما اكتمل اشتراكك\n'
         'بلغني شنو المشكلة اللي واجهتك حتى أساعدك ونكمل اشتراكك على طول 💐')
MSG_F = ('السلام عليكم أخت {fn} 🌹\nمعاج فاطمة من فريق فاكتيف للنساء للتدريب الرياضي\n\n'
         'شفت إنج سويتي حساب بموقعنا وما اكتمل اشتراكج\n'
         'بلغيني شنو المشكلة اللي واجهتج حتى أساعدج ونكمل اشتراكج على طول 💐')
COUNTRY = {'KW': 'الكويت', 'SA': 'السعودية', 'AE': 'الإمارات', 'QA': 'قطر', 'BH': 'البحرين', 'OM': 'عُمان',
           'US': 'أمريكا', 'GB': 'بريطانيا', 'UK': 'بريطانيا'}


def http(url, data=None, headers=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8')


def login():
    body = json.dumps({'email': os.environ['DASH_EMAIL'], 'password': os.environ['DASH_PASSWORD'], 'role': 'admin'}).encode()
    st, txt = http(API + '/auth/login', body, {'Content-Type': 'application/json'})
    j = json.loads(txt)
    tok = j.get('accessToken') or (j.get('data') or {}).get('accessToken')
    if not tok:
        raise RuntimeError('dashboard login: no token')
    return tok


def pages(tok, path, stop_before):
    """Newest-first pages until the last item is older than stop_before. Sequential with retries (the API throttles)."""
    out, pn = [], 1
    while pn <= 40:
        for attempt in range(4):
            try:
                st, txt = http(f'{API}/{path}?page_size=200&page_number={pn}', headers={'Authorization': 'Bearer ' + tok})
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 521) and attempt < 3:
                    time.sleep(3 * (attempt + 1)); continue
                raise
        j = json.loads(txt)
        arr = j if isinstance(j, list) else (j.get('results') or j.get('data') or [])
        out += arr
        if len(arr) < 200 or not arr or when(arr[-1].get('created_at')) < stop_before:
            break
        pn += 1
    return out


def when(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def digits(s):
    return re.sub(r'\D', '', str(s or ''))


def is_test(c):
    e = str(c.get('email') or '').lower()
    return c.get('is_deleted') or 'test' in e or e.endswith('@factive.app')


PREFIX = ('عبد', 'ابو', 'أبو')


def first_name(c):
    fnf = re.sub(r'\s+', ' ', str(c.get('first_name') or '')).strip()
    full = re.sub(r'\s+', ' ', str(c.get('full_name') or '')).strip()
    for v in ((full, fnf) if fnf in PREFIX or not fnf else (fnf, full)):
        if v:
            parts = v.split(' ')
            if parts[0] in PREFIX and len(parts) > 1:      # «عبد الله» → «عبدالله», «ابو فهد» stays two words
                return parts[0] + ('' if parts[0] == 'عبد' else ' ') + parts[1]
            return parts[0]
    return ''


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    start, ready = now - datetime.timedelta(days=KEEP_DAYS), now - datetime.timedelta(minutes=WAIT_MIN)
    tok = login()
    clients = [c for c in pages(tok, 'clients', start) if start <= when(c.get('created_at')) <= ready]
    subs = pages(tok, 'subscriptions', start - datetime.timedelta(days=1))
    by = {}
    for s in subs:
        by.setdefault(str(s.get('client_id')), []).append(s)
    rows, n_paid, n_test, n_nophone = [], 0, 0, 0
    for c in sorted(clients, key=lambda c: when(c.get('created_at')), reverse=True):
        if is_test(c):
            n_test += 1; continue
        mine = by.get(str(c.get('_id')), [])
        if any(s.get('payment_status') == 'Paid' for s in mine):
            n_paid += 1; continue
        ph = digits(c.get('mobile_number'))
        if len(ph) < 8:
            n_nophone += 1; continue
        pi = c.get('personal_info') or {}
        female = str(pi.get('gender') or '').lower() == 'female'
        fn = first_name(c)
        unpaid = [s for s in mine if s.get('payment_status') != 'Paid']
        if unpaid:
            s = max(unpaid, key=lambda s: when(s.get('created_at')))
            months = s.get('duration_months')
            status = f"وصل للدفع ولم يكمل ({s.get('payment_status')})" + (f' — باقة {months} شهور' if months else '')
        else:
            status = 'سوّى حساب فقط — لم يصل لصفحة الدفع'
        notes = []
        if any(s.get('whatsapp_payment_reminder_sent_at') for s in unpaid):
            notes.append('وصله تذكير دفع تلقائي من النظام')
        if not pi.get('gender'):
            notes.append('الجنس غير محدد في الحساب — الرسالة بصيغة المذكر')
        signed = when(c.get('created_at')).astimezone(KW).strftime('%d/%m %H:%M')
        country = pi.get('country_of_residence') or ''
        rows.append([c.get('full_name') or fn, 'https://wa.me/' + ph, ph, c.get('email') or '',
                     COUNTRY.get(str(country).upper(), country), signed, status,
                     (MSG_F if female else MSG_M).format(fn=fn), ' · '.join(notes)])
    stamp = now.astimezone(KW).strftime('%d/%m %H:%M')
    head = ['الاسم', 'رابط واتساب', 'الرقم', 'الإيميل', 'الدولة', 'وقت التسجيل', 'الحالة', 'الرسالة الجاهزة',
            f'ملاحظات (آخر تحديث {stamp})']
    if not rows:
        rows = [['لا يوجد أحد حالياً', '', '', '', '', '', '', 'لا يوجد أحد لم يكمل الدفع الآن — افتح الرابط لاحقاً', '']]
    print(f'accounts in window: {len(clients)} · paid: {n_paid} · test/deleted: {n_test} · no phone: {n_nophone} · on the list: {len(rows) if rows[0][2] else 0}')
    if DRY:
        print('dry run: nothing uploaded'); return 0
    spec = {'name': TAB, 'rows': [head] + rows, 'widths': [20, 28, 15, 26, 10, 12, 30, 70, 36]}
    body = json.dumps({'target': 'paylist', 'sheets': [spec]}, ensure_ascii=False).encode('utf-8')
    q = urllib.parse.urlencode({'key': os.environ['GATEWAY_KEY'], 'mode': 'upload'})
    st, txt = http(os.environ['GATEWAY_URL'] + '?' + q, body, {'Content-Type': 'application/json'}, timeout=180)
    j = json.loads(txt) if txt.strip().startswith('{') else {'error': 'non-json answer'}
    if j.get('error'):
        print('upload failed'); return 1
    print('upload ok')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as ex:
        print('error:', type(ex).__name__)          # type only — the log is public
        sys.exit(1)
