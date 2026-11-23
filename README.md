# agent-ready-check

Can AI assistants and agents read your business website? A static check of your public home page and robots.txt. Python 3 standard library only; it fetches public URLs and nothing else.

    python3 check.py example.com [more.com ...] [--format=json]

Checks: page loads, noindex, text visible without JavaScript, title, meta description, valid JSON-LD, business structured data (name/address/phone/hours/url), phone or email in plain text, form labels, button names, robots.txt rules for AI search vs training crawlers, HTTPS. llms.txt is reported as "convention only".

What it does not claim: it does not predict rankings or citations in ChatGPT, Claude, Perplexity or Google. It finds things that stop software from reading your page.

Tests: `python3 tests/test_pairs.py` (red/green pairs).
