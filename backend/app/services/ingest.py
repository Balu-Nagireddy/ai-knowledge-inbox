import io
import re
import ipaddress
import socket
from urllib.parse import urlsplit
import httpx
from bs4 import BeautifulSoup
from typing import Tuple, Optional, List, Dict
from app.logging_config import logger

def _validate_public_http_url(url: str) -> None:
    """Reject malformed URLs and destinations that resolve to non-public IPs."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise IngestionError("URL must be an absolute HTTP or HTTPS URL.", status_code=400)
        if parsed.username or parsed.password:
            raise IngestionError("URLs containing embedded credentials are not allowed.", status_code=400)
        if parsed.port and parsed.port not in {80, 443}:
            raise IngestionError("Only standard HTTP/HTTPS ports are allowed.", status_code=400)

        host = parsed.hostname.rstrip(".")
        try:
            literal_ip = ipaddress.ip_address(host)
            addresses = [literal_ip]
        except ValueError:
            try:
                records = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
                addresses = list({ipaddress.ip_address(record[4][0]) for record in records})
            except (socket.gaierror, ValueError, OSError):
                raise IngestionError("The URL host could not be resolved.", status_code=400)

        if not addresses or any(not address.is_global for address in addresses):
            raise IngestionError("URLs resolving to private or non-public network addresses are not allowed.", status_code=400)
    except ValueError:
        raise IngestionError("Invalid URL or port.", status_code=400)


class IngestionError(Exception):
    """Custom exception raised when content ingestion fails."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

async def fetch_url_content(url: str, custom_title: Optional[str] = None) -> Tuple[str, str]:
    """
    Fetch web page content server-side, clean HTML tags, and extract readable text and title.
    Returns:
        (title, clean_text)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    logger.info("Fetching URL content")
    try:
        current_url = str(url)
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = None
            for redirect_count in range(6):
                _validate_public_http_url(current_url)
                response = await client.get(current_url, headers=headers)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location")
                if not location or redirect_count == 5:
                    raise IngestionError("URL redirect limit exceeded or redirect target missing.", status_code=400)
                current_url = str(response.url.join(location))
            if response is None or response.status_code != 200:
                code = response.status_code if response is not None else "unknown"
                raise IngestionError(f"Failed to fetch URL. Server responded with status {code}", status_code=502)
            if "text/html" not in response.headers.get("content-type", "").lower() and "application/xhtml+xml" not in response.headers.get("content-type", "").lower():
                raise IngestionError("The target URL did not return an HTML document.", status_code=415)
            html_content = response.text
    except httpx.RequestError as exc:
        logger.warning("Network error while fetching a URL: %s", exc)
        raise IngestionError("Network connection error while fetching URL.", status_code=502)
    except IngestionError:
        raise
    except Exception:
        logger.exception("Unexpected URL extraction failure")
        raise IngestionError("Unexpected error fetching URL.", status_code=500)

    # Clean HTML
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract title
    extracted_title = ""
    if soup.title and soup.title.string:
        extracted_title = soup.title.string.strip()
    
    title = custom_title.strip() if custom_title and custom_title.strip() else (extracted_title or url)

    # Remove non-content elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "form"]):
        element.decompose()

    # Extract text with whitespace normalization
    text = soup.get_text(separator="\n")
    
    # Clean redundant blank lines and spaces
    lines = [line.strip() for line in text.splitlines()]
    clean_text = "\n".join(chunk for chunk in lines if chunk)

    if not clean_text or len(clean_text) < 10:
        raise IngestionError("The target URL did not contain readable textual content.", status_code=422)

    logger.info(f"Successfully extracted {len(clean_text)} characters from {url} (Title: '{title}')")
    return title, clean_text

def process_note_content(raw_content: str, custom_title: Optional[str] = None) -> Tuple[str, str]:
    """
    Process plain text note content, extract/generate title, and clean whitespace.
    Returns:
        (title, clean_text)
    """
    clean_text = raw_content.strip()
    if not clean_text:
        raise IngestionError("Note content cannot be blank.", status_code=400)

    if custom_title and custom_title.strip():
        title = custom_title.strip()
    else:
        # Infer title from the first non-empty line
        first_line = clean_text.splitlines()[0].strip()
        first_line = re.sub(r'^[#*\-•\d\.\s]+', '', first_line).strip()
        title = (first_line[:60] + "...") if len(first_line) > 60 else (first_line or "Untitled Note")

    return title, clean_text

def process_file_content(file_bytes: bytes, filename: str, custom_title: Optional[str] = None) -> Tuple[str, str]:
    """
    Extract readable text from uploaded files: PDF (.pdf), Word (.docx), Markdown (.md), and Text (.txt).
    Returns:
        (title, clean_text)
    """
    if not file_bytes:
        raise IngestionError(f"Uploaded file '{filename}' is empty.", status_code=400)

    ext = filename.lower().split(".")[-1] if "." in filename else ""
    title = custom_title.strip() if custom_title and custom_title.strip() else filename
    extracted_text = ""

    try:
        if ext == "pdf":
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            extracted_text = "\n\n".join(pages_text)
        elif ext == "docx":
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            extracted_text = "\n\n".join(paragraphs)
        elif ext in ["txt", "md", "csv", "json", "py", "js", "html"]:
            try:
                extracted_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = file_bytes.decode("latin-1", errors="ignore")
        else:
            # Attempt general text decode
            try:
                extracted_text = file_bytes.decode("utf-8")
            except Exception:
                raise IngestionError(
                    f"Unsupported file format '.{ext}'. Supported formats are: PDF (.pdf), Word (.docx), Markdown (.md), and Text (.txt).",
                    status_code=400
                )
    except IngestionError:
        raise
    except Exception as exc:
        logger.error(f"Failed to parse file '{filename}': {exc}")
        raise IngestionError(f"Failed to parse file '{filename}': {str(exc)}", status_code=422)

    clean_text = extracted_text.strip()
    if not clean_text or len(clean_text) < 10:
        raise IngestionError(f"File '{filename}' did not contain extractable text.", status_code=422)

    logger.info(f"Successfully extracted {len(clean_text)} characters from file '{filename}'")
    return title, clean_text

async def search_and_fetch_web(query: str, max_results: int = 2) -> List[Dict[str, str]]:
    """
    Search the web for query, fetch top articles server-side, and return clean content for dynamic ingestion.
    Uses DuckDuckGo HTML endpoint with clean extraction.
    """
    logger.info(f"Performing live web search for: '{query}'")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    search_url = f"https://html.duckduckgo.com/html/?q={httpx.URL(query)}"
    links_to_fetch: List[Tuple[str, str]] = []

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            res = await client.get(search_url, headers=headers)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                results = soup.find_all("a", class_="result__url", limit=5)
                for r in results:
                    href = r.get("href", "").strip()
                    if href.startswith("//duckduckgo.com/l/?uddg="):
                        import urllib.parse
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        if "uddg" in parsed:
                            real_url = parsed["uddg"][0]
                            if real_url.startswith("http") and not any(skip in real_url for skip in ["youtube.com", "facebook.com", "twitter.com"]):
                                links_to_fetch.append((r.get_text().strip(), real_url))
                                if len(links_to_fetch) >= max_results:
                                    break
    except Exception as exc:
        logger.warning(f"Web search scrape failed: {exc}")

    # Fallback to Wikipedia API if search scraper got 0 links
    if not links_to_fetch:
        try:
            wiki_api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{httpx.URL(query.replace(' ', '_'))}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                wres = await client.get(wiki_api)
                if wres.status_code == 200:
                    wdata = wres.json()
                    extract = wdata.get("extract")
                    if extract:
                        return [{
                            "title": wdata.get("title", query),
                            "url": wdata.get("content_urls", {}).get("desktop", {}).get("page", "https://en.wikipedia.org"),
                            "content": extract
                        }]
        except Exception:
            pass

    # Fetch and extract text from candidate URLs
    fetched_documents = []
    for snippet_title, url in links_to_fetch[:max_results]:
        try:
            title, clean_text = await fetch_url_content(url, custom_title=snippet_title)
            fetched_documents.append({
                "title": title,
                "url": url,
                "content": clean_text
            })
        except Exception as e:
            logger.warning(f"Failed to fetch search result {url}: {e}")

    return fetched_documents
