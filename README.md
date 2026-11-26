# Factive — instant waitlist check

Every 5 minutes, checks whether someone registered on the waitlist at least 10 minutes ago without messaging us,
and if so starts the private sending workflow. Public only so that GitHub Actions minutes are free.
No customer data is stored here, and the logs show counts only. Secrets: GATEWAY_URL, GATEWAY_KEY, GH_TOKEN.

## paylist.py — «💳 لم يكمل الدفع» (added 26/11/2026)
Every 2 hours: dashboard accounts created in the last 3 days, at least 30 minutes ago, with no Paid subscription
→ one fixed Google Sheet for customer service (مِرسال format), through the private gateway (`mode=upload`, `target=paylist`).
Prints counts only. Extra secrets: `DASH_EMAIL`, `DASH_PASSWORD`. Workflow `paylist.yml` (dispatch from cron-job.org; GitHub cron backup).
