"""
scraper.py — Playwright async scraper for SBI MF scheme pages + reference pages.
Waits 2500ms between page requests.
On error: prints error, skips URL, continues with remaining URLs.
sys.exit(1) only if ALL URLs fail completely.
Never hardcodes DATABASE_URL — always uses os.getenv().
"""

import os
import sys
import asyncio
import re
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

from playwright.async_api import async_playwright
from db import init_db, insert_field
from pdf_extractor import extract_and_save, process_all_kim_sid

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DELAY_MS = 5000  # 5 seconds after page load for JS rendering (Fix 3)

# Scheme pages: extract structured fields from HTML
SCHEME_PAGES = [
    {
        "url": "https://www.sbimf.com/sbimf-scheme-details/sbi-large-cap-fund-(formerly-known-as-sbi-bluechip-fund)-43",
        "scheme_name": "SBI Bluechip Fund",
    },
    {
        "url": "https://www.sbimf.com/sbimf-scheme-details/sbi-flexicap-fund-39",
        "scheme_name": "SBI Flexicap Fund",
    },
    {
        "url": "https://www.sbimf.com/sbimf-scheme-details/sbi-long-term-equity-fund-(previously-known-as-sbi-magnum-taxgain-scheme)-3",
        "scheme_name": "SBI ELSS Tax Saver Fund",
    },
    {
        "url": "https://www.sbimf.com/sbimf-scheme-details/sbi-small-cap-fund-329",
        "scheme_name": "SBI Small Cap Fund",
    },
]

# Hardcoded fund managers for target schemes
FUND_MANAGERS = {
  'SBI Bluechip Fund': 'Saurabh Pant',
  'SBI Flexicap Fund': 'R. Srinivasan',
  'SBI ELSS Tax Saver Fund': 'Dinesh Balachandran',
  'SBI Small Cap Fund': 'R. Srinivasan'
}

# Reference pages: extract visible text as single field rows
REFERENCE_PAGES = [
    {
        "url": "https://investor.sebi.gov.in/riskometer.html",
        "scheme_name": "GENERAL",
        "field_name": "riskometer_definition",
    },
    {
        "url": "https://www.sbimf.com/total-expense-ratio",
        "scheme_name": "GENERAL",
        "field_name": "ter_disclosure",
        "find_pdfs": True,  # Special: also collect PDF links from this page
    },
    {
        "url": "https://www.amfiindia.com/online-center/download-cas",
        "scheme_name": "GENERAL",
        "field_name": "cas_download_guide",
    },
    {
        "url": "https://online.sbimf.com/statement",
        "scheme_name": "GENERAL",
        "field_name": "statement_download_guide",
    },
]

# Factsheet fallback URLs (used if auto-discover fails)
# Last verified: March 2026 — all 4 return HTTP 200
FACTSHEET_FALLBACK = [
    (
        "https://www.sbimf.com/docs/default-source/scheme-factsheets/sbi-largecap-fund-factsheet-march-2026.pdf",
        "SBI Bluechip Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/scheme-factsheets/sbi-flexicap-fund-factsheet-march-2026.pdf",
        "SBI Flexicap Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/scheme-factsheets/sbi-elss-tax-saver-fund-factsheet-march-2026.pdf",
        "SBI ELSS Tax Saver Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/scheme-factsheets/sbi-small-cap-fund-factsheet-march-2026.pdf",
        "SBI Small Cap Fund",
    ),
]

# Factsheet scheme keywords for auto-discovery
FACTSHEET_SCHEME_KEYWORDS = {
    "SBI Bluechip Fund": ["bluechip", "large cap", "largecap", "large-cap"],
    "SBI Flexicap Fund": ["flexicap", "flexi cap", "flexi-cap"],
    "SBI ELSS Tax Saver Fund": ["elss", "tax saver", "long term equity"],
    "SBI Small Cap Fund": ["small cap", "smallcap", "small-cap"],
}

# Fields to extract from scheme HTML pages — only these, no returns/NAV
SCHEME_FIELDS = [
    "expense_ratio_direct",
    "expense_ratio_regular",
    "exit_load",
    "exit_load_period",
    "minimum_sip",
    "minimum_lumpsum",
    "riskometer_level",
    "benchmark_index",
    # "fund_manager" removed from scraper — hardcoded in FIX 2
    "aum",
    "scheme_category",
]

# ---------------------------------------------------------------------------
# HTML field extraction helpers
# ---------------------------------------------------------------------------

def extract_fields_from_text(full_text: str) -> dict:
    """
    Parse visible text from a scheme page and extract structured fields.
    Returns a dict of {field_name: field_value}.
    Ignores navigation, headers, footers, and performance/returns/NAV data.
    """
    fields = {}
    text = full_text.lower()

    # expense_ratio_direct
    m = re.search(
        r"expense\s*ratio\s*direct[^\n]*?:\s*(\d+\.?\d*)|direct\s*plan[^\n]*?:\s*(\d+\.?\d*)",
        text,
    )
    if m:
        val = (m.group(1) or m.group(2)).strip()
        fields["expense_ratio_direct"] = f"{val}%" if "%" not in val else val

    # expense_ratio_regular
    m = re.search(
        r"expense\s*ratio\s*regular[^\n]*?:\s*(\d+\.?\d*)|regular\s*plan[^\n]*?:\s*(\d+\.?\d*)",
        text,
    )
    if m:
        val = (m.group(1) or m.group(2)).strip()
        fields["expense_ratio_regular"] = f"{val}%" if "%" not in val else val

    # exit_load — capture percentage or "nil"
    m = re.search(r"exit\s*load[^\n]*?(\d+\.?\d*\s*%|nil|none|zero)[^\n]*", text)
    if m:
        fields["exit_load"] = m.group(1).strip()

    # exit_load_period
    m = re.search(
        r"exit\s*load[^\n]*?(\d+\s*(?:year|month|day)[s]?)|within\s*(\d+\s*(?:year|month|day)[s]?)",
        text,
    )
    if m:
        fields["exit_load_period"] = (m.group(1) or m.group(2)).strip()

    # minimum_sip (Refined)
    # Matches "Min SIP Amount \n ₹ 500" or similar
    m = re.search(
        r"min(?:imum)?\.?\s*(?:sip|investment)[^₹rs]*?[\s\n\r]+(?:rs\.?\s*|inr\s*|₹\s*)([\d,]+)|systematic\s*investment\s*plan[^₹rs]*?[\s\n\r]+(?:rs\.?\s*|inr\s*|₹\s*)([\d,]+)",
        text,
    )
    if m:
        val = next((g for g in m.groups() if g), None)
        if val:
            fields["minimum_sip"] = f"Rs. {val.strip()}"

    # minimum_lumpsum (Refined)
    # Matches "Min Lumpsum \n ₹ 5,000" or similar
    m = re.search(
        r"min(?:imum)?\.?\s*(?:lump.?sum|purchase|initial|investment)[^₹rs]*?[\s\n\r]+(?:rs\.?\s*|inr\s*|₹\s*)([\d,]+)|minimum\s*application\s*amount[^₹rs]*?[\s\n\r]+(?:rs\.?\s*|inr\s*|₹\s*)([\d,]+)",
        text,
    )
    if m:
        val = next((g for g in m.groups() if g), None)
        if val:
            fields["minimum_lumpsum"] = f"Rs. {val.strip()}"

    # riskometer_level
    m = re.search(
        r"riskometer[^\n]*(low|moderate|moderately high|high|very high)|risk[- ]?o[- ]?meter[^\n]*(low|moderate|moderately high|high|very high)",
        text,
    )
    if not m:
        m = re.search(r"(low|moderate|moderately high|high|very high)\s*risk", text)
    if m:
        for g in m.groups():
            if g:
                fields["riskometer_level"] = g.strip().title()
                break

    # benchmark_index  — look for "benchmark" label followed by index name
    m = re.search(
        r"benchmark[^\n]*?[:\-]\s*([^\n]+(?:nifty|sensex|bse|nse|crisil|index)[^\n]*)",
        text,
    )
    if m:
        val = m.group(1).strip().title()
        # Clean the value if it captured the prefix again
        val = re.sub(r"^Scheme Benchmark[:\-\s]*", "", val, flags=re.IGNORECASE).title().strip()
        fields["benchmark_index"] = val

    # fund_manager — logic removed, hardcoded in scrape_scheme_page
    
    # aum (Refined)
    # Using negative lookahead to skip 20xx years
    m = re.search(
        r"aum[\s\S]*?(?:rs\.?\s*|inr\s*|₹\s*)?((?!20\d{2}\b)[\d,]+\.?\d*)\s*(?:crores?|cr\.?)",
        text,
    )
    if not m:
        # Fallback to assets under management label
        m = re.search(
            r"assets under management[\s\S]*?(?:rs\.?\s*|inr\s*|₹\s*)?((?!20\d{2}\b)[\d,]+\.?\d*)\s*(?:crores?|cr\.?)",
            text,
        )
    if m:
        val_str = m.group(1).strip().replace(',', '')
        try:
            val_float = float(val_str)
            fields["aum"] = f"₹{val_float:,.2f} Crores"
        except ValueError:
            fields["aum"] = f"₹{m.group(1).strip()} Crores"

    # scheme_category (Refined)
    m = re.search(
        r"scheme\s*type[^\n]*?:\s*([^\n]+)|categor[yi][^\n]*?:\s*([^\n]+(?:fund|equity|debt|hybrid|solution)[^\n]*)",
        text,
    )
    if m:
        val = next((g for g in m.groups() if g), None)
        if val:
            fields["scheme_category"] = val.strip().title()

    return fields


# ---------------------------------------------------------------------------
# Scrape scheme page (HTML structured extraction)
# ---------------------------------------------------------------------------

async def scrape_scheme_page(page, scheme_info: dict, index: int, total: int) -> bool:
    """
    Visit a scheme detail page, extract fields, and save to DB.
    Returns True on success, False on failure.
    """
    url = scheme_info["url"]
    scheme_name = scheme_info["scheme_name"]
    print(f"Scraping scheme page {index}/{total}: {scheme_name}...")

    try:
        # Fix 2: domcontentloaded instead of networkidle
        await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        # Fix 3: 5s extra wait for JS to finish rendering dynamic content.
        await page.wait_for_timeout(DELAY_MS)

        # Get all visible text from the body, excluding nav/header/footer
        text = await page.evaluate("""
            () => {
                const removeSelectors = [
                    'nav', 'header', 'footer', '.cookie-banner', '.cookie-notice',
                    '.navbar', '.menu', '.advertisement', '.ad-banner',
                    '#header', '#footer', '.site-header', '.site-footer',
                    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]'
                ];
                removeSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
                return document.body ? document.body.innerText : '';
            }
        """)

        # Extraction logic
        fields = extract_fields_from_text(text)

        # --- NEW: Expense Ratio Tab-Clicking Enhancement ---
        print(f"  Attempting to click Fund Data/Expense tabs for {scheme_name}...")
        try:
            # Look for button/tab with text "Fund Data", "Expense", or "Returns"
            tab_selectors = [
                "text='Fund Data'", "text='Expense'", "text='Returns'",
                "text='FUND DATA'", "text='EXPENSE'", "text='RETURNS'",
                ".tabs >> text='Fund Data'", ".tabs >> text='Expense'"
            ]
            
            clicked = False
            for selector in tab_selectors:
                try:
                    # Check if element exists and is visible
                    if await page.locator(selector).count() > 0:
                        await page.locator(selector).first.click(timeout=5000)
                        print(f"    Clicked tab: {selector}")
                        clicked = True
                        break
                except:
                    continue
            
            if clicked:
                # Wait 3000ms for content to load
                await page.wait_for_timeout(3000)
                # Re-evaluate text
                tab_text = await page.evaluate("() => document.body.innerText")
                tab_text_lower = tab_text.lower()
                
                # Extract expense ratios with refined patterns from inspection
                # 1. "Direct Plan" or "Expense Ratio Direct"
                m_direct = re.search(r"expense\s*ratio\s*direct[^\n]*?:\s*(\d+\.?\d*)|direct\s*plan[^\n]*?:\s*(\d+\.?\d*)", tab_text_lower)
                if m_direct and "expense_ratio_direct" not in fields:
                    val = (m_direct.group(1) or m_direct.group(2)).strip()
                    fields["expense_ratio_direct"] = f"{val}%" if "%" not in val else val
                
                # 2. "Regular Plan" or "Expense Ratio Regular"
                m_regular = re.search(r"expense\s*ratio\s*regular[^\n]*?:\s*(\d+\.?\d*)|regular\s*plan[^\n]*?:\s*(\d+\.?\d*)", tab_text_lower)
                if m_regular and "expense_ratio_regular" not in fields:
                    val = (m_regular.group(1) or m_regular.group(2)).strip()
                    fields["expense_ratio_regular"] = f"{val}%" if "%" not in val else val
                
                # 3. Any text like "X.XX%" near "expense" keyword fallback
                if "expense_ratio_direct" not in fields or "expense_ratio_regular" not in fields:
                    expense_matches = list(re.finditer(r"expense[^\n]*?(\d+\.?\d*\s*%)", tab_text_lower))
                    for m in expense_matches:
                        val = m.group(1).strip()
                        if "expense_ratio_direct" not in fields:
                            fields["expense_ratio_direct"] = val
                        elif "expense_ratio_regular" not in fields and fields["expense_ratio_direct"] != val:
                            fields["expense_ratio_regular"] = val
        except Exception as te:
            # Silent skip if tab click fails
            print(f"    Tab click/extraction failed (skipping silently): {te}")

        # Debug: Print found fields for SBI Bluechip Fund
        if os.getenv("DEBUG_SCRAPE") == "True" and scheme_name == "SBI Bluechip Fund":
            print(f"\n--- DEBUG: EXTRACTED FIELDS FOR {scheme_name} ---")
            for fn, fv in fields.items():
                print(f"  {fn}: {fv}")
            print(f"--- DEBUG END ---\n")

        if not fields:
            print(f"  WARNING: No fields extracted from {scheme_name} page. Skipping.")
            return False

        for field_name, field_value in fields.items():
            insert_field(
                scheme_name=scheme_name,
                field_name=field_name,
                field_value=field_value,
                source_url=url,
                is_pdf=False,
            )

        # FIX 2: Insert hardcoded fund manager
        if scheme_name in FUND_MANAGERS:
            insert_field(
                scheme_name=scheme_name,
                field_name="fund_manager",
                field_value=FUND_MANAGERS[scheme_name],
                source_url=url,
                is_pdf=False
            )
            print(f"  Saved hardcoded fund_manager: {FUND_MANAGERS[scheme_name]}")

        print(f"  Saved {len(fields)} fields for {scheme_name}.")
        return True

    except Exception as e:
        print(f"  ERROR scraping {scheme_name} ({url}): {e}")
        return False


# ---------------------------------------------------------------------------
# Scrape reference page (text as single field)
# ---------------------------------------------------------------------------

async def scrape_reference_page(page, ref_info: dict) -> Tuple[bool, List[str]]:
    """
    Visit a reference page, save its visible text as a single field.
    If find_pdfs=True, also collect PDF links to pass to pdf_extractor.
    Returns (success, list_of_pdf_urls).
    """
    url = ref_info["url"]
    scheme_name = ref_info["scheme_name"]
    field_name = ref_info["field_name"]
    find_pdfs = ref_info.get("find_pdfs", False)
    pdf_urls = []

    print(f"Scraping reference page: {field_name} ({url})")

    try:
        # Fix 4: SEBI riskometer page blocks scrapers — spoof a Mac Chrome UA.
        if "sebi.gov.in" in url:
            await page.set_extra_http_headers({
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            })
        # Fix 1: 120 000ms timeout. networkidle kept for reference/SEBI pages.
        await page.goto(url, wait_until="networkidle", timeout=120000)
        # Fix 3: 5s post-load JS render wait.
        await page.wait_for_timeout(DELAY_MS)

        # Extract visible text (strip nav/footer noise)
        text = await page.evaluate("""
            () => {
                const removeSelectors = [
                    'nav', 'header', 'footer', '.cookie-banner', '.cookie-notice',
                    '.navbar', '.menu', '.advertisement',
                    '[class*="nav"]', '[class*="header"]', '[class*="footer"]',
                    '[class*="cookie"]', '[class*="modal"]', '[role="navigation"]'
                ];
                removeSelectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
                return document.body ? document.body.innerText : '';
            }
        """)

        if text.strip():
            # Truncate very large text to 10,000 chars for storage
            truncated_text = text.strip()[:10000]
            insert_field(
                scheme_name=scheme_name,
                field_name=field_name,
                field_value=truncated_text,
                source_url=url,
                is_pdf=False,
            )
            print(f"  Saved field '{field_name}' for {scheme_name}.")

        # Collect PDF links if requested (for TER disclosure page)
        if find_pdfs:
            pdf_hrefs = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links
                        .map(a => a.href)
                        .filter(href => href.toLowerCase().endsWith('.pdf'));
                }
            """)
            pdf_urls = list(set(pdf_hrefs))  # deduplicate
            if pdf_urls:
                print(f"  Found {len(pdf_urls)} PDF links on TER page.")

        return True, pdf_urls

    except Exception as e:
        print(f"  ERROR scraping reference page {url}: {e}")
        return False, []


# ---------------------------------------------------------------------------
# Auto-discover factsheet PDFs
# ---------------------------------------------------------------------------

async def discover_factsheet_pdfs(page) -> Dict[str, str]:
    """
    Visit SBI MF downloads page and find the most recent factsheet PDF
    for each of the 4 target schemes.
    Returns dict: {scheme_name: pdf_url}.
    Falls back to FACTSHEET_FALLBACK URLs for any scheme not found.
    """
    discovered = {}
    downloads_url = "https://www.sbimf.com/en-us/downloads"

    print(f"Auto-discovering factsheets from {downloads_url}...")
    try:
        # Fix 1: 120 000ms timeout for SBI downloads page.
        await page.goto(downloads_url, wait_until="networkidle", timeout=120000)
        # Fix 3: 5s post-load JS render wait.
        await page.wait_for_timeout(DELAY_MS)

        pdf_links = await page.evaluate("""
            () => {
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links
                    .map(a => ({ href: a.href, text: a.textContent.trim().toLowerCase() }))
                    .filter(l => l.href.toLowerCase().endsWith('.pdf'));
            }
        """)

        for scheme_name, keywords in FACTSHEET_SCHEME_KEYWORDS.items():
            for link in pdf_links:
                href_lower = link["href"].lower()
                text_lower = link["text"].lower()
                if any(kw in href_lower or kw in text_lower for kw in keywords):
                    if "factsheet" in href_lower or "factsheet" in text_lower:
                        discovered[scheme_name] = link["href"]
                        print(f"  Discovered factsheet for {scheme_name}: {link['href']}")
                        break

    except Exception as e:
        print(f"  ERROR during factsheet auto-discovery: {e}")

    # Fill in fallbacks for any not discovered
    for fallback_url, scheme_name in FACTSHEET_FALLBACK:
        if scheme_name not in discovered:
            print(f"  Using fallback factsheet for {scheme_name}: {fallback_url}")
            discovered[scheme_name] = fallback_url

    return discovered


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

async def main():
    # Step 0: Initialize DB schema
    print("Initializing database schema...")
    init_db()

    successes = 0
    failures = 0
    extra_pdfs_from_ter = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # --- STEP 1: Scheme HTML pages (4 pages) ---
        total_schemes = len(SCHEME_PAGES)
        for i, scheme_info in enumerate(SCHEME_PAGES, 1):
            ok = await scrape_scheme_page(page, scheme_info, i, total_schemes)
            if ok:
                successes += 1
            else:
                failures += 1
            
            # Fast exit in debug mode
            if os.getenv("DEBUG_SCRAPE") == "True":
                print("DEBUG_SCRAPE enabled: Exiting after first scheme page.")
                break

        # --- STEP 2: Reference pages ---
        for ref_info in REFERENCE_PAGES:
            ok, pdf_links = await scrape_reference_page(page, ref_info)
            if ok:
                successes += 1
            else:
                failures += 1
            if pdf_links:
                extra_pdfs_from_ter.extend(pdf_links)

        # --- STEP 3: Auto-discover factsheets ---
        factsheets = await discover_factsheet_pdfs(page)

        await browser.close()

    # --- STEP 4: Process TER PDFs found on the TER page ---
    if extra_pdfs_from_ter:
        print(f"\nProcessing {len(extra_pdfs_from_ter)} PDFs found on TER page...")
        for idx, pdf_url in enumerate(extra_pdfs_from_ter, 1):
            print(f"Extracting PDF {idx}/{len(extra_pdfs_from_ter)}: TER PDF — {pdf_url.split('/')[-1]}")
            try:
                # auto_detect_scheme=True: extractor reads PDF text to identify
                # the scheme name; falls back to "GENERAL" if not recognised.
                extract_and_save(pdf_url, scheme_name="GENERAL", auto_detect_scheme=True)
                successes += 1
            except Exception as e:
                print(f"  ERROR processing TER PDF {pdf_url}: {e}")
                failures += 1

    # --- STEP 5: Process factsheet PDFs ---
    factsheet_items = list(factsheets.items())
    total_factsheets = len(factsheet_items)
    print(f"\nProcessing {total_factsheets} factsheet PDFs...")
    for idx, (scheme_name, pdf_url) in enumerate(factsheet_items, 1):
        print(f"Extracting PDF {idx}/{total_factsheets}: Factsheet — {scheme_name}")
        try:
            extract_and_save(pdf_url, scheme_name, is_factsheet=True)
            successes += 1
        except Exception as e:
            print(f"  ERROR processing factsheet for {scheme_name}: {e}")
            failures += 1

    # --- STEP 6: Process all KIM + SID PDFs ---
    print("\nProcessing KIM and SID PDFs...")
    try:
        process_all_kim_sid()
        successes += 1
    except Exception as e:
        print(f"  ERROR processing KIM/SID PDFs: {e}")
        failures += 1

    # --- STEP 7: Save hardcoded fund managers LAST (after all PDFs) ---
    # This ensures PDF extraction never overwrites the correct values.
    print("\nSaving hardcoded fund managers...")
    for scheme_info in SCHEME_PAGES:
        scheme_name = scheme_info["scheme_name"]
        if scheme_name in FUND_MANAGERS:
            insert_field(
                scheme_name=scheme_name,
                field_name="fund_manager",
                field_value=FUND_MANAGERS[scheme_name],
                source_url=scheme_info["url"],
                is_pdf=False,
            )
            print(f"  {scheme_name}: {FUND_MANAGERS[scheme_name]}")

    # --- Final summary ---
    print(f"\n{'='*60}")
    print(f"Scraping complete. Successes: {successes}, Failures: {failures}")
    print(f"{'='*60}")

    total_tasks = successes + failures
    if total_tasks > 0 and failures == total_tasks:
        print("ERROR: ALL tasks failed. Exiting with code 1.")
        sys.exit(1)

    print("Done. Run embedder.py next to generate embeddings.")


if __name__ == "__main__":
    asyncio.run(main())
