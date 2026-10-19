import argparse
import ipaddress
import json
import os
import re
import socket
import sys
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, ValidationError

load_dotenv()

MODEL_NAME = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
TIMEOUT = 15
MAX_PAGES = 8
MAX_TEXT_LENGTH = 30000
MAX_NEWS_ITEMS = 8
REPORTS_DIR = Path("reports")
USER_AGENT = "CompanyIntelligenceAnalyzer/1.0"


class BusinessSummary(BaseModel):
    model: str = Field(description="Company's business model")
    target_persona: str = Field(description="Main customer or buyer")


class BusinessTrigger(BaseModel):
    headline: str = Field(description="Recent business event or lack of verified evidence")
    date_or_timeframe: str = Field(description="Verified event date or timeframe, or unknown")
    source_relevance: str = Field(description="Evidence source and why the event matters")


class CompanyAnalysis(BaseModel):
    company_name: str
    business_summary: BusinessSummary
    key_business_trigger: BusinessTrigger
    operational_bottleneck_hypothesis: str


def _is_public_hostname(hostname: str) -> bool:
    """Resolve a hostname and reject private, local, or otherwise non-public IPs."""
    if not hostname or hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False
    return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("Enter a company domain or URL.")
    if "://" not in raw_url:
        raw_url = "https://" + raw_url

    parsed = urlparse(raw_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a valid public website URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed.")
    if not _is_public_hostname(parsed.hostname):
        raise ValueError("The URL must resolve to a public internet address.")
    return raw_url


def validate_public_url(url: str, expected_host: str | None = None) -> str:
    """Validate URLs before requests, including links discovered from a page."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only public HTTP/HTTPS URLs are allowed.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed.")
    if expected_host and parsed.hostname.lower() != expected_host.lower():
        raise ValueError("Refusing to fetch a URL outside the original website.")
    if not _is_public_hostname(parsed.hostname):
        raise ValueError("Refusing to fetch a non-public address.")
    return url


def fetch_page(url: str) -> tuple[str, list[str]]:
    # Validate the first URL, then validate every redirect destination before
    # requesting it. This supports regional redirects such as stripe.com/in
    # without blindly following redirects to private/local addresses.
    current_url = validate_public_url(url)
    response = None

    for _ in range(6):
        response = requests.get(
            current_url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=False,
        )

        if response.status_code not in (301, 302, 303, 307, 308):
            break

        location = response.headers.get("Location")
        if not location:
            raise ValueError("Website returned a redirect without a destination.")

        next_url = urljoin(current_url, location)
        current_host = urlparse(current_url).hostname
        next_host = urlparse(next_url).hostname

        # Permit redirects within the same hostname or between the bare
        # domain and its www variant. Refuse unexpected cross-domain redirects.
        allowed_hosts = {current_host}
        if current_host and current_host.startswith("www."):
            allowed_hosts.add(current_host[4:])
        elif current_host:
            allowed_hosts.add("www." + current_host)

        if next_host not in allowed_hosts:
            raise ValueError(f"Refusing unexpected cross-domain redirect to: {next_host}")

        current_url = validate_public_url(next_url)

    else:
        raise ValueError("Too many redirects while fetching website.")

    if response is None:
        raise ValueError("No response received from website.")

    response.raise_for_status()
    url = current_url

    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type:
        raise ValueError("The URL did not return an HTML page.")

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Unknown"

    for tag in soup(["script", "style", "nav", "footer", "noscript", "svg", "header"]):
        tag.decompose()

    page_text = soup.get_text(" ", strip=True)
    keywords = ("about", "news", "press", "research", "company", "announcement",
                "customer", "product", "platform", "solution", "investor", "blog")
    links = []
    original_host = urlparse(url).hostname

    for anchor in soup.find_all("a", href=True):
        link = urljoin(url, anchor["href"])
        parsed_link = urlparse(link)
        label = anchor.get_text(" ", strip=True).lower()
        searchable_text = label + " " + parsed_link.path.lower()
        if parsed_link.scheme not in ("http", "https"):
            continue
        if parsed_link.hostname != original_host:
            continue
        if any(word in searchable_text for word in keywords):
            if link not in links and link != url:
                links.append(link)

    extracted_text = f"Title: {title}\nURL: {url}\nContent: {page_text}"
    return extracted_text, links


def collect_website_text(start_url: str) -> str:
    start_url = validate_public_url(start_url)
    start_host = urlparse(start_url).hostname
    pending = [start_url]
    visited = set()
    content = []

    # Common paths are useful when a homepage has sparse navigation text.
    common_paths = (
        "/about", "/about-us", "/company", "/about/company",
        "/news", "/press", "/press-releases", "/blog",
        "/customers", "/customer-stories", "/products",
    )
    for path in common_paths:
        candidate = urljoin(start_url.rstrip("/") + "/", path.lstrip("/"))
        if urlparse(candidate).hostname == start_host and candidate not in pending:
            pending.append(candidate)

    while pending and len(visited) < MAX_PAGES:
        url = pending.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page_text, links = fetch_page(url)
            if page_text.strip():
                content.append(page_text)
                print(f"Collected page: {url}", file=sys.stderr)
            for link in links:
                if link not in visited and link not in pending:
                    pending.append(link)
        except (requests.RequestException, ValueError) as exc:
            print(f"Warning: Could not fetch {url}: {exc}", file=sys.stderr)

    if not content:
        raise RuntimeError(
            "No website text could be extracted. The site may block automated requests "
            "or redirect to another host."
        )
    print(f"Collected website text from {len(content)} page(s).", file=sys.stderr)
    return "\n\n".join(content)[:MAX_TEXT_LENGTH]


def search_recent_news(company_name: str, domain: str) -> list[dict]:
    """Search Google News RSS for recent articles; RSS metadata is treated as evidence leads."""
    queries = [
        f'"{company_name}" when:365d',
        f"site:{domain} news when:365d",
    ]
    collected = []
    seen = set()

    for query in queries:
        rss_url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"
        try:
            response = requests.get(
                rss_url,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"Warning: News search failed for query {query!r}: {exc}", file=sys.stderr)
            continue

        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = (source_el.text or "").strip() if source_el is not None else "Unknown source"
            if not title or not link or link in seen:
                continue

            # Keep only items with a parseable publication date within the last 365 days.
            try:
                published = parsedate_to_datetime(pub_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=__import__("datetime").timezone.utc)
                age_seconds = time.time() - published.timestamp()
                if age_seconds < 0 or age_seconds > 365 * 24 * 60 * 60:
                    continue
                date_label = published.date().isoformat()
            except (TypeError, ValueError, OverflowError):
                date_label = "Date not verified"

            seen.add(link)
            collected.append({
                "headline": title,
                "published_date": date_label,
                "source": source,
                "url": link,
                "search_query": query,
            })

    # Prefer newest items and cap the evidence provided to the model.
    collected.sort(key=lambda item: item["published_date"], reverse=True)
    return collected[:MAX_NEWS_ITEMS]


def guess_company_name(website_text: str, url: str) -> str:
    """A conservative fallback name based on the page title or hostname."""
    first_title = re.search(r"Title:\s*(.+)", website_text)
    if first_title:
        title = first_title.group(1).strip()
        if title and title.lower() != "unknown":
            return title.split("|")[0].split("—")[0].strip()[:100]
    host = urlparse(url).hostname or "Unknown"
    return host.removeprefix("www.").split(".")[0].replace("-", " ").title()


def analyze_company(url: str, website_text: str, news_items: list[dict]) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from your .env file.")

    client = Groq(api_key=api_key)
    company_fallback = guess_company_name(website_text, url)

    prompt = f"""
Analyze the company using the supplied website text and recent-news search results.

Return a JSON object with exactly these fields:
- company_name: string
- business_summary: object with model and target_persona
- key_business_trigger: object with headline, date_or_timeframe, and source_relevance
- operational_bottleneck_hypothesis: string

Rules:
1. Describe the business model and target persona using website evidence. If the evidence is insufficient, state that clearly rather than guessing.
2. Select a relevant business event from the last 6-12 months only if the supplied news metadata supports it.
3. Do not invent dates, events, article details, sources, or claims. The news results are search-result metadata, not full article text.
4. If no suitable recent event is found, use "Unknown - not verified from supplied sources" for headline and date_or_timeframe, and explain that no suitable verified trigger was found in source_relevance.
5. Explain how the selected event could matter to the company, but distinguish evidence from inference.
6. The bottleneck must begin with "Hypothesis:" and must be a plausible, clearly unverified operational or technical bottleneck. Tie it to the supplied evidence where possible. Do not present it as a discovered fact.
7. Keep all fields concise and specific. Return valid JSON only.

Input URL: {url}
Fallback company name if the evidence does not establish one: {company_fallback}

Website evidence:
{website_text}

Recent-news search results (metadata only):
{json.dumps(news_items, ensure_ascii=False, indent=2)}
"""

    start_time = time.perf_counter()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a careful company intelligence analyst. Use only supplied evidence, "
                    "separate facts from hypotheses, and never invent sources or events. "
                    "Return only valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    latency = round(time.perf_counter() - start_time, 2)
    response_text = response.choices[0].message.content
    if not response_text:
        raise ValueError("Groq returned an empty response.")

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Groq returned invalid JSON.") from exc

    analysis = CompanyAnalysis.model_validate({
        "company_name": result.get("company_name") or company_fallback,
        "business_summary": result["business_summary"],
        "key_business_trigger": result["key_business_trigger"],
        "operational_bottleneck_hypothesis": result["operational_bottleneck_hypothesis"],
    })

    return {
        "company_name": analysis.company_name,
        "analyzed_url": url,
        "business_summary": analysis.business_summary.model_dump(),
        "key_business_trigger": analysis.key_business_trigger.model_dump(),
        "operational_bottleneck_hypothesis": analysis.operational_bottleneck_hypothesis,
        "execution_metadata": {
            "model_used": MODEL_NAME,
            "latency_seconds": latency,
        },
    }


def save_report(result: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    company_name = result["company_name"].lower()
    safe_name = re.sub(r"[^a-z0-9]+", "_", company_name).strip("_") or "company"
    hostname = (urlparse(result["analyzed_url"]).hostname or "website").removeprefix("www.")
    safe_host = re.sub(r"[^a-z0-9]+", "_", hostname).strip("_") or "website"
    base_name = f"{safe_name}_{safe_host}"
    report_path = REPORTS_DIR / f"{base_name}.json"
    counter = 2
    while report_path.exists():
        report_path = REPORTS_DIR / f"{base_name}_{counter}.json"
        counter += 1
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a public company website and recent news using Groq AI."
    )
    parser.add_argument(
        "url",
        help="Company domain or URL, e.g. https://www.stripe.com",
    )
    args = parser.parse_args()

    try:
        url = normalize_url(args.url)

        print("Fetching company website...", file=sys.stderr)
        website_text = collect_website_text(url)

        company_name = guess_company_name(website_text, url)
        domain = urlparse(url).hostname or ""
        print("Searching recent company news...", file=sys.stderr)
        news_items = search_recent_news(company_name, domain)
        print(f"Found {len(news_items)} recent news result(s).", file=sys.stderr)

        print("Analyzing company with Groq...", file=sys.stderr)
        result = analyze_company(url, website_text, news_items)

        print(json.dumps(result, indent=2, ensure_ascii=False))
        report_path = save_report(result)
        print(f"\nReport saved to: {report_path}", file=sys.stderr)

    except (
        ValueError,
        RuntimeError,
        requests.RequestException,
        ValidationError,
        KeyError,
    ) as exc:
        parser.exit(1, f"Error: {exc}\n")
    except Exception as exc:
        parser.exit(1, f"Unexpected error: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
