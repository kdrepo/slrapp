import requests
import time
import os
import re
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("S2_API_KEY", "")   # optional — works without it too
MAX_RESULTS = 80
OUTPUT_FILE = "semantic_scholar_results.ris"

FIELDS = (
    "paperId,title,abstract,year,publicationDate,venue,publicationVenue,"
    "journal,externalIds,url,openAccessPdf,fieldsOfStudy,s2FieldsOfStudy,"
    "publicationTypes,citationCount,referenceCount,influentialCitationCount,"
    "isOpenAccess,authors,tldr"
)

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


# ── QUERY SIMPLIFIER ──────────────────────────────────────────────────────────
def simplify_query(query: str) -> str:
    """
    Semantic Scholar supports simple keyword search, not full Scopus-style boolean.
    Extracts the most meaningful terms from a complex boolean query and builds
    a clean, simple query string that the API will accept.
    """
    original = query.strip()

    # Already simple — no parentheses or boolean operators
    if "(" not in original and " AND " not in original and " OR " not in original:
        return original

    # Extract all quoted phrases
    phrases = re.findall(r'"([^"]+)"', original)

    # Extract unquoted significant words (ignore operators and short words)
    no_quotes = re.sub(r'"[^"]*"', '', original)
    operators = {"AND", "OR", "NOT", "and", "or", "not"}
    bare_words = [
        w.strip("()").strip()
        for w in no_quotes.split()
        if w.strip("()").strip()
        and w.strip("()").strip() not in operators
        and len(w.strip("()").strip()) > 3
    ]

    # Deduplicate preserving order
    seen = set()
    all_terms = []
    for t in phrases + bare_words:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            all_terms.append(t)

    # Quote multi-word phrases, join (Semantic Scholar treats space as implicit AND)
    parts = []
    for term in all_terms:
        parts.append(f'"{term}"' if " " in term else term)

    # Best results with 4–6 key terms
    return " ".join(parts[:6])


# ── API CALL ──────────────────────────────────────────────────────────────────
def fetch_page(query, offset, limit, headers, using_key):
    params = {
        "query": query,
        "fields": FIELDS,
        "limit": limit,
        "offset": offset,
    }

    for attempt in range(7):
        try:
            response = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Connection error: {e}. Retrying in 5s...")
            time.sleep(5)
            continue

        if response.status_code == 200:
            return response.json()

        elif response.status_code == 429:
            # Unauthenticated hits a shared pool — back off aggressively
            wait = (2 ** attempt) + (10 if not using_key else 2)
            print(f"   ⚠️  Rate limited. Waiting {wait}s (retry {attempt + 1}/7)...")
            time.sleep(wait)

        elif response.status_code == 400:
            print(f"   ❌ Query rejected by API (400). Returning results so far.")
            return None

        else:
            print(f"   ❌ Error {response.status_code}: {response.text}")
            return None

    print("   ❌ Max retries reached.")
    return None


def search_semantic_scholar(query: str, max_results: int = 80):
    using_key = bool(API_KEY)
    headers = {"x-api-key": API_KEY} if using_key else {}
    request_delay = 1.5 if using_key else 5.0

    # Auto-simplify complex boolean queries
    simplified = simplify_query(query)
    if simplified != query:
        print(f"\n   ℹ️  Complex boolean query detected.")
        print(f"   ℹ️  Semantic Scholar uses simple keyword search, not full boolean.")
        print(f"   ✏️  Auto-simplified to: \"{simplified}\"\n")
        query = simplified

    print(f"🔍 Searching: \"{query}\"")
    print(f"   Mode  : {'API key ✅' if using_key else 'No API key — unauthenticated (still works, just slower)'}")
    print(f"   Target: {max_results} results\n")

    # Small initial pause for unauthenticated to avoid instant burst limit
    if not using_key:
        time.sleep(3)

    papers = []
    offset = 0
    limit = min(100, max_results)

    while len(papers) < max_results:
        data = fetch_page(query, offset, limit, headers, using_key)
        if data is None:
            break

        batch = data.get("data", [])
        total_available = data.get("total", 0)

        if not batch:
            print("   ℹ️  No more results available.")
            break

        papers.extend(batch)
        offset += len(batch)

        print(f"   ✅ Fetched {len(papers)} / {min(max_results, total_available)} papers...")

        if offset >= total_available or len(papers) >= max_results:
            break

        time.sleep(request_delay)

    return papers[:max_results]


# ── RIS CONVERSION ────────────────────────────────────────────────────────────
def map_publication_type(pub_types):
    if not pub_types:
        return "GEN"
    mapping = {
        "journalarticle": "JOUR",
        "conferencepaper": "CONF",
        "review": "JOUR",
        "booksection": "CHAP",
        "book": "BOOK",
        "preprint": "JOUR",
        "dataset": "DATA",
    }
    return mapping.get(pub_types[0].lower(), "GEN")


def paper_to_ris(paper: dict) -> str:
    lines = []

    def add(tag, value):
        if value is not None and str(value).strip():
            lines.append(f"{tag}  - {str(value).strip()}")

    pub_types = paper.get("publicationTypes") or []
    add("TY", map_publication_type(pub_types))
    add("TI", paper.get("title"))
    add("AB", paper.get("abstract"))

    year = paper.get("year")
    if year:
        add("PY", f"{year}///")
    add("DA", paper.get("publicationDate"))

    for author in (paper.get("authors") or []):
        add("AU", author.get("name"))
        affiliations = author.get("affiliations") or []
        if affiliations:
            add("AD", ", ".join(affiliations))

    journal    = paper.get("journal") or {}
    pub_venue  = paper.get("publicationVenue") or {}
    venue_name = journal.get("name") or pub_venue.get("name") or paper.get("venue")
    add("JO", venue_name)
    add("JF", journal.get("name"))
    add("VL", journal.get("volume"))

    pages = journal.get("pages", "")
    if pages and "-" in str(pages):
        sp, ep = str(pages).split("-", 1)
        add("SP", sp.strip())
        add("EP", ep.strip())
    elif pages:
        add("SP", pages)

    ext = paper.get("externalIds") or {}
    add("DO", ext.get("DOI"))
    add("M1", ext.get("ArXiv"))
    add("M2", ext.get("PubMed"))
    add("M3", str(ext["CorpusId"]) if ext.get("CorpusId") else None)

    add("UR", paper.get("url"))
    add("L1", (paper.get("openAccessPdf") or {}).get("url"))
    add("C7", paper.get("citationCount"))
    add("C3", paper.get("influentialCitationCount"))
    add("N1", (paper.get("tldr") or {}).get("text"))

    for f in (paper.get("fieldsOfStudy") or []):
        add("KW", f)

    add("SN", pub_venue.get("issn"))
    add("DB", "Semantic Scholar")
    add("DP", "Semantic Scholar API")
    add("AN", paper.get("paperId"))

    lines.append("ER  - ")
    lines.append("")
    return "\n".join(lines)


# ── SAVE RIS ──────────────────────────────────────────────────────────────────
def save_ris(papers: list, filepath: str, query: str):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("TY  - GEN\n")
        f.write("TI  - Semantic Scholar Search Export\n")
        f.write(f"AB  - Query: {query} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Results: {len(papers)}\n")
        f.write("ER  - \n\n")
        for paper in papers:
            f.write(paper_to_ris(paper))
            f.write("\n")
    print(f"\n💾 Saved {len(papers)} records → {filepath}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 58)
    print("  Semantic Scholar → RIS Exporter")
    print("=" * 58)

    if not API_KEY:
        print("\n  ℹ️  No API key — unauthenticated mode.")
        print("  Requests are spaced out to stay within shared rate limits.")
        print("  Get a free key: https://www.semanticscholar.org/product/api")

    query = input("\nEnter your search query: ").strip()
    if not query:
        print("❌ No query entered. Exiting.")
        return

    papers = search_semantic_scholar(query, max_results=MAX_RESULTS)

    if not papers:
        print("❌ No results found. Try broader or fewer keywords.")
        return

    print(f"\n📄 Converting {len(papers)} papers to RIS format...")
    save_ris(papers, OUTPUT_FILE, query)

    print(f"\n✅ Done! Import '{OUTPUT_FILE}' into Zotero, Mendeley, or EndNote.")
    print("=" * 58)


if __name__ == "__main__":
    main()