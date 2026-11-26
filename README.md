# Factive — instant waitlist check

Every 5 minutes, checks whether someone registered on the waitlist at least 10 minutes ago without messaging us,
and if so starts the private sending workflow. Public only so that GitHub Actions minutes are free.
No customer data is stored here, and the logs show counts only. Secrets: GATEWAY_URL, GATEWAY_KEY, GH_TOKEN.

## paylist.py — «💳 لم يكمل الدفع» (added 26/11/2026)
Every 2 hours: dashboard accounts created in the last 3 days, at least 45 minutes ago, with no Paid subscription
→ one fixed Google Sheet for customer service (مِرسال format), through the private gateway (`mode=upload`, `target=paylist`).
Prints counts only. Extra secrets: `DASH_EMAIL`, `DASH_PASSWORD`. Workflow `paylist.yml` (dispatch from cron-job.org; GitHub cron backup).

## paysend.py — automatic WhatsApp to accounts that did not pay (added 26/11/2026)
Every 10 minutes (cron-job.org job 8949249 → `paysend.yml`; GitHub cron backup at :23/:53):
- «حاول يدفع»: an unpaid subscription, ~35 min after it was created → Gallabox `factive_paylist_tried_m/_f`.
- «سوّى حساب فقط»: an account with no subscription, 60 min after it was created → `factive_paylist_acct_m/_f`.
One of each per person per 7 days. Sent-state = HMACs in the Actions cache (never committed). Prints counts only.
Switches (repo variables): `PAYSEND_TRIED`, `PAYSEND_ACCT` ('1' = send). Variable `GB_CHANNEL_ID`.
Extra secrets: `GB_API_KEY`, `GB_API_SECRET` (same values as in factive-daily-cloud). Arabic first names come from
the public `names_ar.json` of WhatsAppSendingTool; a Latin name not in it is not sent (it stays for customer service).
