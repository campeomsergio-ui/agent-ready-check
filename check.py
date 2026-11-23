#!/usr/bin/env python3
"""agent-ready-check: can AI assistants and agents read this business website? Reads public pages only."""
import json, re, sys, urllib.request, urllib.robotparser, urllib.error
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "agent-ready-check/0.1 (+https://github.com/campeomsergio-ui)"
# Crawler user-agents from the vendors' own docs. 'search' = used to answer/cite live; 'training' = model training only.
BOTS = {"OAI-SearchBot": "search", "ChatGPT-User": "search", "Claude-SearchBot": "search", "Claude-User": "search",
        "PerplexityBot": "search", "GPTBot": "training", "ClaudeBot": "training", "Google-Extended": "training", "CCBot": "training"}
LOCAL_TYPES = re.compile(r"Service\b|Business|Office|Clinic|Agency|Shop|Salon|Practice|Center|Dealer|LocalBusiness|Restaurant|Store|Dentist|Hotel|Organization|Plumber|Electrician|Physician|AutoRepair|LegalService|HomeAndConstructionBusiness|ProfessionalService|BeautySalon|Bakery|CafeOrCoffeeShop|Contractor|RoofingContractor|HVACBusiness|MedicalBusiness", re.I)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.skip, self.jsonld, self.cur_ld = [], 0, [], None
        self.title, self.in_title, self.meta = "", False, {}
        self.labels_for, self.inputs, self.buttons, self.cur_btn, self.links = set(), [], [], None, []
        self.label_depth = 0

    def handle_starttag(self, tag, a):
        a = {k: (v or "") for k, v in a}
        if tag in ("script", "style", "noscript", "template"):
            self.skip += 1
            if tag == "script" and a.get("type", "").lower() == "application/ld+json":
                self.cur_ld = []
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "label":
            self.label_depth += 1
            if a.get("for"):
                self.labels_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            if a.get("type", "").lower() not in ("hidden", "submit", "button", "image", "reset"):
                self.inputs.append((a, self.label_depth > 0))
        elif tag == "button":
            self.cur_btn = [a, ""]
        elif tag == "a":
            self.links.append(a.get("href", ""))
        if a.get("itemtype"):
            self.microdata = getattr(self, "microdata", []) + [a["itemtype"]]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template"):
            self.skip = max(0, self.skip - 1)
            if self.cur_ld is not None and tag == "script":
                self.jsonld.append("".join(self.cur_ld)); self.cur_ld = None
        elif tag == "title":
            self.in_title = False
        elif tag == "label":
            self.label_depth = max(0, self.label_depth - 1)
        elif tag == "button" and self.cur_btn:
            self.buttons.append(tuple(self.cur_btn)); self.cur_btn = None

    def handle_data(self, d):
        if self.cur_ld is not None:
            self.cur_ld.append(d)
        elif self.skip:
            return
        elif self.in_title:
            self.title += d
        else:
            self.text.append(d)
            if self.cur_btn:
                self.cur_btn[1] += d


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "ignore"), r.url
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), "", url
    except Exception as e:
        return 0, {}, str(e), url


def f(sev, check, title, detail, fix, evidence):
    return {"severity": sev, "check": check, "title": title, "detail": detail, "fix": fix, "evidence": evidence}


def check_robots(robots_txt, page_url):
    out = []
    rp = urllib.robotparser.RobotFileParser(); rp.parse(robots_txt.splitlines())
    blocked = {b: k for b, k in BOTS.items() if not rp.can_fetch(b, page_url)}
    search = sorted(b for b, k in blocked.items() if k == "search")
    train = sorted(b for b, k in blocked.items() if k == "training")
    if search:
        out.append(f("high", "robots", "robots.txt blocks AI search/answer crawlers", ", ".join(search),
                     "Allow these user-agents if you want to be found and quoted in ChatGPT/Claude/Perplexity answers.", "vendor crawler docs"))
    if train:
        out.append(f("info", "robots", "robots.txt blocks AI training crawlers", ", ".join(train),
                     "A business choice; blocking training bots does not stop live answers.", "vendor crawler docs"))
    return out


def check_page(html, headers, robots_txt="", url="https://example.com/"):
    p = Page(); p.feed(html)
    out = []
    text = re.sub(r"\s+", " ", " ".join(p.text)).strip()
    robots_meta = (p.meta.get("robots", "") + " " + str(headers.get("X-Robots-Tag", headers.get("x-robots-tag", "")))).lower()
    if "noindex" in robots_meta:
        out.append(f("high", "noindex", "Page asks not to be indexed", robots_meta.strip(), "Remove noindex from the live site.", "Google Search docs"))
    if len(text) < 200:
        out.append(f("high", "js-only", "Almost no text without JavaScript", f"{len(text)} characters of visible text in the HTML.",
                     "Render the main content server-side or pre-render it; most AI crawlers do not run JavaScript.", "Vercel/MERJ crawler study 2024"))
    if not p.title.strip():
        out.append(f("medium", "title", "No page title", "", "Add a <title> with business name and what you do.", "HTML standard"))
    if not p.meta.get("description", "").strip():
        out.append(f("low", "description", "No meta description", "", "Add one sentence: who you are, where, what you offer.", "Google Search docs"))
    items, bad = [], 0
    for raw in p.jsonld:
        try:
            d = json.loads(raw)
        except ValueError:
            bad += 1; continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                items.append(x); stack.extend(x.get("@graph", []) if isinstance(x.get("@graph"), list) else [])
    if bad:
        out.append(f("high", "jsonld-invalid", "Structured data (JSON-LD) does not parse", f"{bad} block(s) invalid.",
                     "Fix the JSON; invalid blocks are ignored by every consumer.", "schema.org / Google rich results docs"))
    biz = [{"@type": t} for t in getattr(p, "microdata", []) if LOCAL_TYPES.search(t)]
    biz += [i for i in items if LOCAL_TYPES.search(str(i.get("@type", ""))) or i.get("address") or i.get("telephone")]
    b = next((i for i in biz if len(i) > 1), None)
    if not biz:
        out.append(f("medium", "jsonld-business", "No business structured data", "No LocalBusiness/Organization JSON-LD found.",
                     "Add LocalBusiness JSON-LD with name, address, phone, opening hours.", "schema.org, Google local business docs"))
    if b:
        missing = [k for k in ("name", "address", "telephone", "openingHoursSpecification|openingHours", "url")
                   if not any(b.get(x) for x in k.split("|"))]
        if missing:
            out.append(f("low", "jsonld-fields", "Business structured data is incomplete", "missing: " + ", ".join(m.split("|")[-1] for m in missing),
                         "Fill in the missing fields so assistants can answer 'are they open / how do I call'.", "schema.org LocalBusiness"))
    has_tel = any(h.startswith("tel:") for h in p.links) or re.search(r"\+?\d[\d ()-]{7,}\d", text)
    has_mail = any(h.startswith("mailto:") for h in p.links) or re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if not (has_tel or has_mail):
        out.append(f("medium", "contact", "No phone or email in the page text", "", "Put a phone number or email in plain HTML text.", "observation"))
    unlabeled = [a.get("name") or a.get("id") or a.get("type", "text") for a, wrapped in p.inputs
                 if not wrapped and a.get("id") not in p.labels_for and not a.get("aria-label") and not a.get("aria-labelledby") and not a.get("title")]
    if unlabeled:
        out.append(f("medium", "form-labels", "Form fields without labels", ", ".join(unlabeled[:6]),
                     "Give each field a <label> or aria-label; agents and screen readers read the label, not the placeholder.", "WCAG 2.2 / Lighthouse"))
    empty_btn = [a for a, t in p.buttons if not t.strip() and not a.get("aria-label") and not a.get("title")]
    if empty_btn:
        out.append(f("medium", "button-names", "Buttons with no name", f"{len(empty_btn)} button(s).", "Add visible text or aria-label.", "WCAG 2.2 / Lighthouse"))
    if robots_txt:
        out += check_robots(robots_txt, url)
    return out


def suggest_jsonld(html, url):
    """Draft LocalBusiness JSON-LD from what the page already shows publicly. Unknowns stay as TODO."""
    p = Page(); p.feed(html)
    text = re.sub(r"\s+", " ", " ".join(p.text))
    tel = next((h[4:] for h in p.links if h.startswith("tel:")), None) or (re.search(r"\+?\d[\d ()-]{7,}\d", text) or [None])[0]
    mail = next((h[7:].split("?")[0] for h in p.links if h.startswith("mailto:")), None)
    ld_names = []
    for raw in p.jsonld:
        try:
            d0 = json.loads(raw)
        except ValueError:
            continue
        ld_names += [x.get("name") for x in (d0 if isinstance(d0, list) else [d0]) if isinstance(x, dict) and x.get("name")]
    parts = [x.strip() for x in re.split(r"\s+[|\u2013\u2014-]\s+", p.title.strip()) if x.strip().lower() not in ("home", "welcome", "homepage")]
    name = ld_names[0] if ld_names else (parts[0] if parts else p.meta.get("og:site_name", ""))
    d = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": name or "TODO", "url": url,
         "telephone": tel or "TODO", "email": mail or "TODO", "description": p.meta.get("description") or "TODO",
         "address": {"@type": "PostalAddress", "streetAddress": "TODO", "addressLocality": "TODO", "postalCode": "TODO", "addressCountry": "TODO"},
         "openingHours": "TODO e.g. Mo-Fr 09:00-17:00"}
    return '<script type="application/ld+json">\n' + json.dumps(d, indent=2, ensure_ascii=False) + "\n</script>"


def audit(url, suggest=False):
    if "://" not in url:
        url = "https://" + url
    status, headers, html, final = fetch(url)
    if status != 200:
        return final, [f("high", "fetch", "Home page did not load", f"HTTP {status} {html[:80]}", "Check the site is up for non-browser clients.", "direct fetch")]
    root = f"{urlparse(final).scheme}://{urlparse(final).netloc}/"
    rs, _, robots, _ = fetch(urljoin(root, "robots.txt"))
    out = check_page(html, headers, robots if rs == 200 else "", final)
    if urlparse(final).scheme != "https":
        out.insert(0, f("medium", "https", "Site is not on HTTPS", final, "Serve over HTTPS.", "browser/search vendors"))
    if suggest and any(x["check"] in ("jsonld-business", "jsonld-fields") for x in out):
        out.append(f("info", "suggested-fix", "Draft structured data (check every TODO before using)", suggest_jsonld(html, final), "Paste into the page <head>.", "schema.org LocalBusiness"))
    ls, _, _, _ = fetch(urljoin(root, "llms.txt"))
    out.append(f("info", "llms-txt", "llms.txt " + ("present" if ls == 200 else "absent"), "Convention only.",
                 "No evidence it changes AI citations today; optional.", "llmstxt.org; Google says it does not use it"))
    return final, out


def render(url, findings, fmt="md"):
    if fmt == "json":
        return json.dumps({"url": url, "findings": findings}, indent=2)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    lines = [f"# Agent-readability check: {url}", ""]
    real = [x for x in findings if x["severity"] != "info"]
    lines.append(f"{len(real)} issue(s). Static check of public HTML and robots.txt; not a ranking or citation guarantee.\n")
    for x in sorted(findings, key=lambda x: order[x["severity"]]):
        if x["check"] == "suggested-fix":
            lines.append(f"- **FIX DRAFT** {x['title']}\n\n```html\n{x['detail']}\n```"); continue
        lines.append(f"- **{x['severity'].upper()}** {x['title']}" + (f": {x['detail']}" if x["detail"] else "") + f"\n  Fix: {x['fix']} _(basis: {x['evidence']})_")
    return "\n".join(lines) + "\n"


def main(argv):
    fmt = "json" if "--format=json" in argv else "md"
    urls = [a for a in argv if not a.startswith("--")]
    if not urls:
        print("usage: python3 check.py URL [URL...] [--format=json] [--suggest]", file=sys.stderr); return 2
    worst = 0
    for u in urls:
        final, fs = audit(u, "--suggest" in argv)
        print(render(final, fs, fmt))
        worst = max(worst, 1 if any(x["severity"] == "high" for x in fs) else 0)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
