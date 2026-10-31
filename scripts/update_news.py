import datetime
import email.utils
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

FEEDS = [
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
    ("NASA", "https://www.nasa.gov/feed/"),
    ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss"),
]
OUTPUT_FILE = Path("news.json")
MAX_ARTICLES = 30
USER_AGENT = "TechnologyMadeSimpleNews/1.0 (+https://technologicmadesimple.com)"


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value):
    parser = TextExtractor()
    parser.feed(html.unescape(value or ""))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element, *names):
    for child in element.iter():
        if local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def get_link(item):
    for child in item:
        if local_name(child.tag) == "link":
            href = child.attrib.get("href", "").strip()
            if href:
                return href
            if child.text:
                return child.text.strip()
    return ""


def parse_date(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.astimezone(datetime.timezone.utc)
        except ValueError:
            return None


def categorize(title, description):
    text = f"{title} {description}".lower()
    rules = [
        ("Climate", ("climate", "warming", "emissions", "carbon", "environment", "power grid", "renewable")),
        ("Artificial Intelligence", ("artificial intelligence", "machine learning", " ai ", "ai-", "agent", "chatbot", "llm", "neural network", "robot")),
        ("Space", ("space", "planet", "satellite", "moon", "mars", "astronomy", "rocket", "nasa")),
        ("Health", ("health", "medical", "drug", "disease", "clinical", "biotech", "medicine")),
        ("Cybersecurity", ("cyber", "security", "hack", "privacy", "scam", "phishing")),
        ("Business", ("business", "enterprise", "startup", "ipo", "manufacturing", "industry", "market")),
        ("Science", ("science", "research", "quantum", "physics", "biology", "chemistry")),
    ]
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category
    return "Other"


def fetch_feed(source, url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"}
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        root = ET.fromstring(response.read())

    found = []
    for item in root.iter():
        if local_name(item.tag) not in ("item", "entry"):
            continue

        title = clean_text(child_text(item, "title"))
        link = get_link(item)
        date_text = child_text(item, "pubdate", "published", "updated", "date")
        description = clean_text(child_text(item, "description", "summary", "content", "encoded"))
        parsed_date = parse_date(date_text)

        if not title or not link or not parsed_date:
            continue

        found.append({
            "title": title,
            "link": link,
            "date": parsed_date.isoformat().replace("+00:00", "Z"),
            "description": description,
            "source": source,
            "category": categorize(title, description),
        })
    return found


def main():
    articles_by_link = {}

    # Preserve existing articles if one publisher's feed is temporarily unavailable.
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            for article in existing:
                if article.get("link"):
                    articles_by_link[article["link"]] = article
        except (json.JSONDecodeError, OSError):
            print("Could not read the existing news.json; continuing with fresh feeds.")

    for source, url in FEEDS:
        try:
            fetched = fetch_feed(source, url)
            for article in fetched:
                articles_by_link[article["link"]] = article
            print(f"{source}: fetched {len(fetched)} articles.")
        except Exception as error:
            print(f"Warning: could not update {source}: {error}")

    articles = list(articles_by_link.values())
    articles.sort(
        key=lambda article: parse_date(article.get("date", "")) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
        reverse=True
    )
    articles = articles[:MAX_ARTICLES]

    OUTPUT_FILE.write_text(
        json.dumps(articles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )
    print(f"Saved {len(articles)} articles to {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()
