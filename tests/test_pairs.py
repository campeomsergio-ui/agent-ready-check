import sys, unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check
from check import check_page, check_robots, suggest_jsonld
import json

BODY = "<p>" + "Smith Plumbing fixes leaks and boilers in Leeds. Call 0113 496 0000 any weekday. " * 4 + "</p>"
LD = '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Plumber","name":"Smith","url":"https://x","address":"1 Road","telephone":"+44 113 496 0000","openingHours":"Mo-Fr 08:00-17:00"}</script>'
GREEN = f"<html><head><title>Smith Plumbing</title><meta name=description content='Plumber in Leeds'>{LD}</head><body>{BODY}<form><label for=e>Email</label><input id=e name=email><button>Send</button></form></body></html>"

def checks(html, headers=None, robots=""):
    return {x["check"] for x in check_page(html, headers or {}, robots)}

class Pairs(unittest.TestCase):
    def test_green_page_clean(self):
        self.assertEqual(checks(GREEN), set())
    def test_js_only(self):
        self.assertIn("js-only", checks("<html><head><title>x</title></head><body><div id=root></div><script>render()</script></body></html>"))
    def test_noindex_meta_and_header(self):
        self.assertIn("noindex", checks(GREEN.replace("<head>", "<head><meta name=robots content='noindex'>")))
        self.assertIn("noindex", checks(GREEN, {"X-Robots-Tag": "noindex"}))
    def test_invalid_jsonld(self):
        self.assertIn("jsonld-invalid", checks(GREEN.replace('"Smith",', '"Smith"')))
    def test_missing_business_ld(self):
        self.assertIn("jsonld-business", checks(GREEN.replace(LD, "")))
    def test_graph_ld_accepted(self):
        g = LD.replace('{"@context":"https://schema.org",', '{"@context":"https://schema.org","@graph":[{').replace("}</script>", "}]}</script>")
        self.assertEqual(checks(GREEN.replace(LD, g)), set())
    def test_accounting_service_subtype(self):
        self.assertEqual(checks(GREEN.replace('"Plumber"', '"AccountingService"')), set())
        self.assertIn("jsonld-business", checks(GREEN.replace('"Plumber"', '"WebSite"').replace(',"address":"1 Road","telephone":"+44 113 496 0000"', "")))
    def test_microdata_business_counts(self):
        html = GREEN.replace(LD, "").replace("<body>", '<body itemscope itemtype="https://schema.org/Plumber">')
        self.assertNotIn("jsonld-business", checks(html))
    def test_type_array(self):
        self.assertEqual(checks(GREEN.replace('"Plumber"', '["Plumber","Organization"]')), set())
    def test_suggest_uses_page_data_only(self):
        html = GREEN.replace(LD, "").replace("<button>", "<a href='tel:+441134960000'>call</a><button>")
        d = json.loads(suggest_jsonld(html, "https://x/").split("\n", 1)[1].rsplit("\n", 1)[0])
        self.assertEqual((d["name"], d["telephone"], d["address"]["streetAddress"]), ("Smith Plumbing", "+441134960000", "TODO"))
    def test_incomplete_fields(self):
        self.assertIn("jsonld-fields", checks(GREEN.replace(',"telephone":"+44 113 496 0000"', "")))
    def test_unlabeled_input_and_wrapped_ok(self):
        self.assertIn("form-labels", checks(GREEN.replace("<label for=e>Email</label>", "")))
        self.assertNotIn("form-labels", checks(GREEN.replace("<label for=e>Email</label><input id=e name=email>", "<label>Email <input name=email></label>")))
    def test_empty_button(self):
        self.assertIn("button-names", checks(GREEN.replace("<button>Send</button>", "<button><svg></svg></button>")))
        self.assertNotIn("button-names", checks(GREEN.replace("<button>Send</button>", "<button aria-label=Send><svg></svg></button>")))
    def test_no_contact(self):
        self.assertIn("contact", checks(GREEN.replace("Call 0113 496 0000 any weekday.", "We are great at plumbing work.")))
    def test_robots_allowlist_pattern_fix(self):
        red = "User-agent: Googlebot\nDisallow:\nCrawl-delay: 300\n\nUser-agent: *\nDisallow: /\n"
        r = check_robots(red, "https://x/")
        self.assertTrue(r and "Allow-list pattern" in r[0]["fix"])
        green = "User-agent: OAI-SearchBot\nDisallow: /\n"
        r = check_robots(green, "https://x/")
        self.assertTrue(r and "Allow-list pattern" not in r[0]["fix"])

    def test_robots_search_vs_training(self):
        r = check_robots("User-agent: OAI-SearchBot\nDisallow: /\n", "https://x/")
        self.assertEqual([x["severity"] for x in r], ["high"])
        r = check_robots("User-agent: GPTBot\nDisallow: /\n", "https://x/")
        self.assertEqual([x["severity"] for x in r], ["info"])
        self.assertEqual(check_robots("User-agent: *\nDisallow: /admin\n", "https://x/"), [])
        self.assertEqual(len(check_robots("User-agent: *\nDisallow: /\n", "https://x/")), 2)

class Tls(unittest.TestCase):
    def test_bad_cert_named(self):
        import check
        orig = check.fetch
        check.fetch = lambda u, timeout=15: (0, {}, "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate>", u)
        try:
            self.assertEqual(check.audit("x.test")[1][0]["check"], "tls")
        finally:
            check.fetch = orig

class FieldRegressions(unittest.TestCase):
    # Recover at </noscript> after an unclosed quoted attribute so the real body is counted.
    @unittest.expectedFailure
    def test_malformed_tracking_noscript_does_not_swallow_body(self):
        broken = '<noscript><img hidden src="/pixel\n</noscript>'
        html = GREEN.replace("</head>", broken + "</head>")
        self.assertNotIn("js-only", checks(html))

    def test_tracking_noscript_does_not_make_an_empty_shell_readable(self):
        html = f"<html><head><title>Example</title><noscript>{BODY}</noscript></head><body><div id=root></div></body></html>"
        self.assertIn("js-only", checks(html))

    # Retry with a neutral HTTP user agent before describing an almost-empty response as site-wide.
    @unittest.expectedFailure
    def test_user_agent_specific_empty_shell_is_not_a_sitewide_finding(self):
        from unittest.mock import patch
        from check import audit
        site = "https://example.com/"
        shell = "<html><head><title>Example</title></head><body><div id=root></div></body></html>"
        responses = [
            (200, {}, shell, site),
            (200, {}, GREEN, site),
            (404, {}, "", site + "robots.txt"),
            (404, {}, "", site + "llms.txt"),
        ]
        with patch("check.fetch", side_effect=responses):
            self.assertNotIn("js-only", {f["check"] for f in audit(site)[1]})

    def test_empty_shell_still_reports_js_only(self):
        self.assertIn("js-only", checks("<div id=root></div><script>loadPage()</script>"))

    # Skip controls hidden by the HTML hidden attribute or an explicit inline display:none.
    @unittest.expectedFailure
    def test_inline_hidden_implementation_field_ignored(self):
        field = '<input name="_app_id" tabindex="-1" style="display:none">'
        self.assertNotIn("form-labels", checks(GREEN.replace("<form>", "<form>" + field)))

    def test_visible_implementation_named_field_still_requires_label(self):
        field = '<input name="_app_id">'
        self.assertIn("form-labels", checks(GREEN.replace("<form>", "<form>" + field)))

    # Ignore explicitly assistive-tech-hidden controls that are also removed from tab order.
    @unittest.expectedFailure
    def test_offscreen_honeypot_is_ignored(self):
        field = '<input name="website" tabindex="-1" aria-hidden="true" style="position:absolute;left:-5000px">'
        self.assertNotIn("form-labels", checks(GREEN.replace("<form>", "<form>" + field)))

    def test_regular_website_field_still_requires_label(self):
        self.assertIn("form-labels", checks(GREEN.replace("<form>", '<form><input name="website">')))

    # Treat a class as hidden only when the page CSS confirms display:none.
    @unittest.expectedFailure
    def test_css_hidden_honeypot_is_ignored(self):
        html = GREEN.replace("</head>", "<style>.hidden { display: none }</style></head>")
        field = '<input class="hidden" name="_gotcha" tabindex="-1">'
        self.assertNotIn("form-labels", checks(html.replace("<form>", "<form>" + field)))

    def test_similar_class_without_hiding_rule_still_requires_label(self):
        field = '<input class="hidden" name="_gotcha" tabindex="-1">'
        self.assertIn("form-labels", checks(GREEN.replace("<form>", "<form>" + field)))

    # Keep fallback CAPTCHA controls separate from normal-page contact-field findings.
    @unittest.expectedFailure
    def test_noscript_captcha_is_not_a_normal_page_field(self):
        fallback = '<noscript><textarea name="g-recaptcha-response" placeholder="CAPTCHA response"></textarea></noscript>'
        self.assertNotIn("form-labels", checks(GREEN.replace("<form>", "<form>" + fallback)))

    def test_visible_captcha_field_still_requires_label(self):
        visible = '<textarea name="captcha" placeholder="CAPTCHA response"></textarea>'
        self.assertIn("form-labels", checks(GREEN.replace("<form>", "<form>" + visible)))

class FetchRetry(unittest.TestCase):
    """Field FP 23 Nov: a WAF 403'd our UA but served browsers and AI bots; 'did not load' was wrong."""
    def run_with(self, browser_status):
        calls = []
        def fake(url, ua, timeout):
            calls.append(ua)
            return (403, {}, "", url) if ua == check.UA else (browser_status, {}, "<html>ok</html>", url)
        with patch("check._get", side_effect=fake):
            return check.fetch("https://example.test/")[0], calls

    def test_green_browser_ok_means_loaded(self):
        status, calls = self.run_with(200)
        self.assertEqual((status, len(calls)), (200, 2))

    def test_red_browser_also_refused_stays_403(self):
        self.assertEqual(self.run_with(403)[0], 403)


class RobotsRfc9309(unittest.TestCase):
    """Field FP 23 Nov (frikitek.com): 'Disallow: /?' was read as 'Disallow: /'."""
    def test_green_query_only_rule_allows_home(self):
        self.assertFalse(check_robots("User-agent: *\nDisallow: /?\nDisallow: */feed/\n", "https://x.test/"))

    def test_red_catch_all_block_still_flagged(self):
        out = check_robots("User-agent: Googlebot\nDisallow:\n\nUser-agent: *\nDisallow: /\n", "https://x.test/")
        self.assertTrue(any(f["severity"] == "high" for f in out))

    def test_allow_dollar_beats_disallow_all_on_home(self):
        self.assertTrue(check.robots_allows("User-agent: *\nDisallow: /\nAllow: /$\n", "GPTBot", "https://x.test/"))


if __name__ == "__main__":
    unittest.main()
