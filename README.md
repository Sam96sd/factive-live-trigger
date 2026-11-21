# Factive — instant waitlist check

Every 5 minutes, checks whether someone registered on the waitlist at least 10 minutes ago without messaging us,
and if so starts the private sending workflow. Public only so that GitHub Actions minutes are free.
No customer data is stored here, and the logs show counts only. Secrets: GATEWAY_URL, GATEWAY_KEY, GH_TOKEN.
