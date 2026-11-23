import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
    def test_robots_search_vs_training(self):
        r = check_robots("User-agent: OAI-SearchBot\nDisallow: /\n", "https://x/")
        self.assertEqual([x["severity"] for x in r], ["high"])
        r = check_robots("User-agent: GPTBot\nDisallow: /\n", "https://x/")
        self.assertEqual([x["severity"] for x in r], ["info"])
        self.assertEqual(check_robots("User-agent: *\nDisallow: /admin\n", "https://x/"), [])
        self.assertEqual(len(check_robots("User-agent: *\nDisallow: /\n", "https://x/")), 2)

if __name__ == "__main__":
    unittest.main()
