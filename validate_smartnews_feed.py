#!/usr/bin/env python3
"""Local validation for the TNL SmartNews SmartFormat feed.

Checks the feed against the SmartFormat 2.2 requirements as documented
in the assessment (secondary sources — the official spec and SmartNews's
own validator are policy-blocked in this environment, so this is a
local structural validation, NOT a substitute for sf-validator).

Usage: python3 validate_smartnews_feed.py [smartnews.xml]
Exit 0 = all checks pass; exit 1 = any check fails.
"""
import email.utils
import sys
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "snf": "http://www.smartnews.be/snf",
}

failures = []
warnings = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def is_https(url):
    try:
        p = urlparse(url or "")
        return p.scheme == "https" and bool(p.netloc)
    except Exception:
        return False


def main(path):
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        print(f"FAIL: not well-formed XML: {e}")
        return 1
    root = tree.getroot()
    check(root.tag == "rss", f"root element is <{root.tag}>, expected <rss>")
    check(root.get("version") == "2.0", "rss version != 2.0")
    raw = open(path, encoding="utf-8").read()
    for prefix, uri in NS.items():
        check(f'xmlns:{prefix}="{uri}"' in raw, f"namespace {prefix} ({uri}) not declared")

    ch = root.find("channel")
    check(ch is not None, "missing <channel>")
    if ch is None:
        print("FAIL")
        return 1
    check((ch.findtext("title") or "") == "The Nerd's List", "channel title wrong")
    check((ch.findtext("link") or "") == "https://www.thenerdslist.com", "channel link wrong")
    desc = ch.findtext("description") or ""
    check(0 < len(desc) <= 30, f"channel description length {len(desc)} (want 1-30 chars)")
    check((ch.findtext("language") or "") == "en", "channel language != en")
    check(bool(ch.findtext("lastBuildDate")), "missing lastBuildDate")
    logo = ch.findtext("{%s}logo" % NS["snf"])
    check(bool(logo) and is_https(logo), f"snf:logo missing or not https: {logo!r}")
    if logo and "700x100" not in logo:
        warnings.append(f"snf:logo URL does not mention 700x100: {logo}")

    items = ch.findall("item")
    check(1 <= len(items) <= 25, f"item count {len(items)} (want 1-25)")
    for i, it in enumerate(items, 1):
        tag = f"item {i} ({(it.findtext('title') or '')[:40]!r})"
        check(bool((it.findtext("title") or "").strip()), f"{tag}: missing title")
        check(is_https(it.findtext("link")), f"{tag}: link missing/not https")
        d = it.findtext("description") or ""
        check(bool(d.strip()), f"{tag}: missing description")
        enc = it.findtext("{%s}encoded" % NS["content"])
        check(bool(enc) and len(enc) > 500, f"{tag}: content:encoded missing/short ({len(enc or '')} chars)")
        if enc:
            check("blogger-post-footer" not in enc, f"{tag}: footer boilerplate still present")
            check("<script" not in enc.lower(), f"{tag}: <script> still present")
            check("Follow TNL for more!" not in enc, f"{tag}: footer text still present")
        check(bool((it.findtext("guid") or "").strip()), f"{tag}: missing guid")
        pd = it.findtext("pubDate") or ""
        try:
            email.utils.parsedate_to_datetime(pd)
        except Exception:
            failures.append(f"{tag}: pubDate not RFC 822: {pd!r}")
        check(len(it.findall("category")) >= 1, f"{tag}: no category")
        check((it.findtext("{%s}creator" % NS["dc"]) or "") == "Jamal Jarrett",
              f"{tag}: dc:creator != Jamal Jarrett")
        check((it.findtext("{%s}language" % NS["dc"]) or "") == "en", f"{tag}: dc:language != en")
        th = it.find("{%s}thumbnail" % NS["media"])
        check(th is not None and is_https(th.get("url")), f"{tag}: media:thumbnail missing/not https")

    print(f"Checked {len(items)} items.")
    for w in warnings:
        print("WARN:", w)
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed:")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS: all local SmartFormat checks passed.")
    print("NOTE: this is local structural validation only — the authoritative")
    print("check is SmartNews's own validator (sf-validator.smartnews.com),")
    print("which is policy-blocked from this environment.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "smartnews.xml"))
