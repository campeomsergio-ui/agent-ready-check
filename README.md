# agent-ready-check

[![ci](https://github.com/campeomsergio-ui/agent-ready-check/actions/workflows/ci.yml/badge.svg)](https://github.com/campeomsergio-ui/agent-ready-check/actions)
![python](https://img.shields.io/badge/python-3.8%2B-blue) ![deps](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen) ![license](https://img.shields.io/badge/license-MIT-lightgrey)

Can AI assistants and agents actually read your business website? More people now ask ChatGPT, Claude or Perplexity for a local business instead of searching. This tool checks the things that stop that software from reading the page. It uses only the Python standard library and fetches only public URLs.

## Run it

```bash
python3 check.py example.com [more.com ...]
python3 check.py example.com --format=json
```

## Example (real output, example.com)

```text
4 issue(s). Static check of public HTML and robots.txt; not a ranking or citation guarantee.
- HIGH   Almost no text without JavaScript: 156 characters of visible text in the HTML.
         Fix: Render the main content server-side or pre-render it; most AI crawlers do not run JavaScript.
- MEDIUM No business structured data: No LocalBusiness/Organization JSON-LD found.
- MEDIUM No phone or email in the page text
- LOW    No meta description
- INFO   llms.txt absent: Convention only.
```

Every finding cites its basis (vendor docs, schema.org, crawler studies), or says "observation" when it is a judgment call.

## What it checks

Page loads · `noindex` · visible text without JavaScript · title and meta description · valid JSON-LD · business data (name/address/phone/hours/url) · contact info in plain text · form labels and button names · robots.txt rules, split into **AI-search crawlers** (OAI-SearchBot, Claude-SearchBot, PerplexityBot…) vs **training-only crawlers** (GPTBot, ClaudeBot, CCBot…) · HTTPS. `llms.txt` is reported as a convention only.

## What it does not claim

It does not predict rankings or citations. It finds concrete blockers, each with a fix.

## Tests

`python3 tests/test_pairs.py`: red/green HTML pairs, run in CI on every push.

Built by [Yuval Rochman](https://www.linkedin.com/in/yuval-rochman-206903452) · [GuraForge](https://guraforge.com).
