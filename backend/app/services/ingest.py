import re
import httpx
from bs4 import BeautifulSoup
from typing import Tuple, Optional
from app.logging_config import logger

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
    
    logger.info(f"Fetching URL: {url}")
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise IngestionError(
                    f"Failed to fetch URL. Server responded with status {response.status_code}",
                    status_code=400
                )
            html_content = response.text
    except httpx.RequestError as exc:
        logger.error(f"Network error fetching {url}: {exc}")
        raise IngestionError(f"Network connection error while fetching URL: {str(exc)}", status_code=502)
    except IngestionError:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error fetching {url}: {exc}")
        raise IngestionError(f"Unexpected error fetching URL: {str(exc)}", status_code=500)

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
