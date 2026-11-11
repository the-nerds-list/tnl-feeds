#!/usr/bin/env python3
"""Generate a SmartNews SmartFormat 2.2 feed for The Nerd's List.

Reads Blogger's Atom/RSS feed, keeps news posts only, strips the
blogger-post-footer boilerplate, and emits RSS 2.0 + SmartFormat 2.2.

Usage:
    python3 generate_smartnews_feed.py [--feed-url URL] [--base-url URL]
                                       [--out PATH] [--max-items N]

--base-url is the public base URL the feed + logos will be hosted at.
It is a placeholder until hosting is set up; update it to the real
hosted URL when GitHub Pages / Cloudflare Pages is configured.
Default matches the assessment's recommended GitHub Pages layout.

Excluded from the feed:
  * podcast episode site posts (labels `podcast` / `the nerds list daily`)
  * posts with no image in the body

Deliberately omitted (format not verifiable first-hand against the
official SmartFormat 2.2 spec — SmartNews domains are policy-blocked
in this environment; the spec was verified only via secondary sources):
  * snf:sponsoredLink (exact element format unverified)
  * snf:analytics (exact element format unverified; GA4 IS installed
    on the blog, so this can be added once the format is confirmed
    against the official spec / validator)
  * a dark-mode logo element in the feed (no verified element name;
    the dark-mode PNG is built alongside this script and is supplied
    to SmartNews via the publisher portal instead)
"""
import argparse
import email.utils
import html
import re
import sys
import time
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

BLOGGER_FEED = "https://www.thenerdslist.com/feeds/posts/default?alt=rss"
SITE_URL = "https://www.thenerdslist.com"
SITE_TITLE = "The Nerd's List"
SITE_DESCRIPTION = "Nerd news, daily."
AUTHOR = "Jamal Jarrett"

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "snf": "http://www.smartnews.be/snf",
}
EXCLUDED_LABELS = {"podcast", "the nerds list daily"}
USER_AGENT = "TNL-SmartNews-Feed-Generator/1.0 (+https://www.thenerdslist.com)"

FOOTER_RE = re.compile(
    r'<div[^>]*class="[^"]*blogger-post-footer[^"]*"[^>]*>.*?</div>\s*$',
    re.DOTALL | re.IGNORECASE,
)
SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
BLOGGER_SIZE_RE = re.compile(r"/s\d+(-c)?/")
REL_URL_RE = re.compile(r"""(href|src)=["']/(?!/)""", re.IGNORECASE)
PROTO_REL_RE = re.compile(r"""(href|src)=["']//""", re.IGNORECASE)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def clean_html(raw):
    """Strip footer boilerplate + scripts, absolutize URLs."""
    out = FOOTER_RE.sub("", raw)
    if "blogger-post-footer" in out:
        # Fallback: cut everything from the footer marker onward.
        idx = out.find("Follow TNL for more!")
        if idx > 0:
            out = out[: out.rfind("<", 0, idx)] if "<" in out[:idx] else out[:idx]
    out = SCRIPT_RE.sub("", out)
    out = COMMENT_RE.sub("", out)
    out = REL_URL_RE.sub(r'\1="https://www.thenerdslist.com/', out)
    out = PROTO_REL_RE.sub(r'\1="https://', out)
    return out.strip()


def first_image(html_text):
    for src in IMG_RE.findall(html_text):
        if src.startswith("data:"):
            continue
        return src
    return None


def thumbnail_url(src):
    """Blogger image URLs carry a size segment (/s72-c/); upscale it."""
    if "blogger.googleusercontent.com" in src:
        return BLOGGER_SIZE_RE.sub("/s800/", src, count=1)
    return src


def text_excerpt(html_text, limit=200, title=""):
    text = TAG_RE.sub(" ", html.unescape(html_text))
    text = WS_RE.sub(" ", text).strip()
    if title and text.startswith(title):
        text = text[len(title):].strip(" —–-:.").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def fetch_feed(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.content


def build_feed(feed_xml, base_url, max_items=25):
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("No <channel> in Blogger feed")

    items_out = []
    excluded = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        labels = {(c.text or "").strip().lower() for c in item.findall("category")}
        if labels & EXCLUDED_LABELS:
            excluded.append((title, "podcast episode site post"))
            continue
        raw_html = item.findtext("description") or ""
        cleaned = clean_html(raw_html)
        img = first_image(cleaned)
        if not img:
            excluded.append((title, "no image in post body"))
            continue
        items_out.append((item, cleaned, img))
        if len(items_out) >= max_items:
            break

    # --- Build RSS 2.0 + SmartFormat document ---
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = SITE_TITLE
    ET.SubElement(ch, "link").text = SITE_URL
    ET.SubElement(ch, "description").text = SITE_DESCRIPTION
    ET.SubElement(ch, "language").text = "en"
    ET.SubElement(ch, "lastBuildDate").text = email.utils.formatdate(time.time(), usegmt=True)
    ET.SubElement(ch, "ttl").text = "240"
    logo = ET.SubElement(ch, "{%s}logo" % NS["snf"])
    logo.text = urljoin(base_url, "snf-logo-light-700x100.png")

    for item, cleaned, img in items_out:
        el = ET.SubElement(ch, "item")
        ET.SubElement(el, "title").text = (item.findtext("title") or "").strip()
        ET.SubElement(el, "link").text = (item.findtext("link") or "").strip()
        ET.SubElement(el, "description").text = text_excerpt(
            cleaned, title=(item.findtext("title") or "").strip()
        )
        enc = ET.SubElement(el, "{%s}encoded" % NS["content"])
        enc.text = cleaned
        guid = ET.SubElement(el, "guid", {"isPermaLink": "false"})
        guid.text = (item.findtext("guid") or "").strip()
        ET.SubElement(el, "pubDate").text = (item.findtext("pubDate") or "").strip()
        cats = [(cat.text or "").strip() for cat in item.findall("category")]
        cats = [c for c in cats if c]
        if not cats:
            # Some posts publish with no Blogger labels; SmartFormat
            # requires a category, so fall back to "news".
            cats = ["news"]
            print(f"  ! {item.findtext('title')[:60]!r} has no labels; using fallback category 'news'",
                  file=sys.stderr)
        for c in cats:
            ET.SubElement(el, "category").text = c
        ET.SubElement(el, "{%s}creator" % NS["dc"]).text = AUTHOR
        ET.SubElement(el, "{%s}language" % NS["dc"]).text = "en"
        thumb = ET.SubElement(el, "{%s}thumbnail" % NS["media"])
        thumb.set("url", thumbnail_url(img))

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    return tree, items_out, excluded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed-url", default=BLOGGER_FEED)
    ap.add_argument("--base-url", default="https://thenerdslist.github.io/feeds/")
    ap.add_argument("--out", default="smartnews.xml")
    ap.add_argument("--max-items", type=int, default=25)
    args = ap.parse_args()

    feed_xml = fetch_feed(args.feed_url)
    tree, included, excluded = build_feed(feed_xml, args.base_url, args.max_items)
    tree.write(args.out, encoding="utf-8", xml_declaration=True)

    print(f"Wrote {args.out}: {len(included)} items")
    for item, _, _ in included:
        print(f"  + {item.findtext('title')}")
    print(f"Excluded {len(excluded)}:")
    for title, why in excluded:
        print(f"  - [{why}] {title[:80]}")


if __name__ == "__main__":
    main()
