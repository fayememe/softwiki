import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
from softwiki.ingestion.normalize import normalize_text

def extract_web_content(url: str, headers: dict = None) -> dict:
    if not headers:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    if response.encoding == 'ISO-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'

    soup = BeautifulSoup(response.text, "html.parser")
    
    title = ""
    title_tag = soup.find("h1") or soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()
    else:
        parsed_url = urlparse(url)
        title = parsed_url.path.split("/")[-1] or parsed_url.netloc

    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        element.decompose()
        
    article_content = soup.find("article") or soup.find("div", class_=lambda c: c and any(x in c.lower() for x in ["article", "post", "content", "entry"]))
    
    if article_content:
        paragraphs = article_content.find_all(["p", "h2", "h3", "h4", "li"])
    else:
        paragraphs = soup.find_all(["p", "h2", "h3", "h4", "li"])
        
    raw_text_parts = []
    for p in paragraphs:
        text = p.get_text().strip()
        if text:
            if p.name in ["h2", "h3", "h4"]:
                raw_text_parts.append(f"\n## {text}\n")
            else:
                raw_text_parts.append(text)
                
    raw_text = "\n".join(raw_text_parts)
    cleaned_text = normalize_text(raw_text)
    
    published_at = datetime.utcnow()
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        try:
            dt_str = time_tag.get("datetime")[:10]
            published_at = datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            pass
    else:
        meta_date = (
            soup.find("meta", property="article:published_time") or
            soup.find("meta", attrs={"name": "pubdate"}) or
            soup.find("meta", attrs={"name": "publish-date"}) or
            soup.find("meta", property="og:pubdate")
        )
        if meta_date and meta_date.get("content"):
            try:
                dt_str = meta_date.get("content")[:10]
                published_at = datetime.strptime(dt_str, "%Y-%m-%d")
            except Exception:
                pass

    author = "Unknown Author"
    author_tag = soup.find("meta", attrs={"name": "author"}) or soup.find("span", class_=lambda c: c and "author" in c.lower())
    if author_tag:
        if author_tag.name == "meta":
            author = author_tag.get("content")
        else:
            author = author_tag.get_text().strip()
            
    # Detect language from <html lang="..."> attribute
    language = "unknown"
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        language = html_tag["lang"][:2].lower()
    elif "ja.wikipedia.org" in url or ".jp/" in url:
        language = "ja"
    elif "zh.wikipedia.org" in url or "zh." in url:
        language = "zh"
    elif "en." in url or ".com" in url or ".org" in url:
        language = "en"

    return {
        "title": title,
        "author": author,
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "published_at": published_at,
        "raw_html": response.text,
        "language": language,
    }
