"""Ядро SEO Meta Auditor: загрузка страниц, извлечение мета-данных, поиск проблем."""
import ipaddress
import re
import socket
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SEOMetaAuditor/1.0)"}
TIMEOUT = 10
MAX_URLS = 200
MAX_REDIRECTS = 5
ALLOWED_PORTS = (80, 443)


class UnsafeURL(ValueError):
    """Адрес запрещён: не http(s), нестандартный порт или ведёт во внутреннюю сеть."""


def check_url_safe(url):
    """Не даёт сервису ходить на localhost и внутренние адреса (защита от SSRF)."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("разрешены только http(s)-адреса")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise UnsafeURL("некорректный порт")
    if port not in ALLOWED_PORTS:
        raise UnsafeURL("разрешены только порты 80 и 443")
    try:
        infos = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURL("домен не найден")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise UnsafeURL("адрес ведёт во внутреннюю сеть")


def safe_get(url):
    """GET с ручной обработкой редиректов: каждый переход проверяется заново."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url_safe(url)
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False)
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            if not location:
                return resp
            url = urljoin(url, location)
            continue
        return resp
    raise requests.TooManyRedirects("слишком много редиректов")

TITLE_RANGE = (30, 65)
DESC_RANGE = (70, 165)


def parse_urls(text):
    """Из произвольного текста берёт уникальные http(s)-адреса, сохраняя порядок."""
    seen, result = set(), []
    for line in re.split(r"[\s,;]+", text or ""):
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^https?://", line):
            line = "https://" + line
        if urlparse(line).netloc and line not in seen:
            seen.add(line)
            result.append(line)
    return result[:MAX_URLS]


def urls_from_sitemap(sitemap_url):
    """Возвращает список URL из sitemap.xml (поддерживает вложенные sitemap-индексы)."""
    resp = safe_get(sitemap_url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "xml")
    locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
    if soup.find("sitemapindex"):
        urls = []
        for sub in locs[:5]:
            try:
                urls += urls_from_sitemap(sub)
            except (requests.RequestException, UnsafeURL):
                continue
            if len(urls) >= MAX_URLS:
                break
        return urls[:MAX_URLS]
    return locs[:MAX_URLS]


def audit_url(url):
    """Загружает страницу и возвращает словарь с мета-данными."""
    row = {"url": url, "status": None, "title": "", "description": "",
           "h1": "", "h1_count": 0, "canonical": "", "robots": "", "error": ""}
    try:
        resp = safe_get(url)
    except UnsafeURL as exc:
        row["error"] = f"адрес запрещён: {exc}"
        return row
    except requests.RequestException as exc:
        row["error"] = type(exc).__name__
        return row
    row["status"] = resp.status_code
    if "html" not in resp.headers.get("Content-Type", ""):
        row["error"] = "не HTML"
        return row
    soup = BeautifulSoup(resp.text, "lxml")
    if soup.title and soup.title.string:
        row["title"] = soup.title.string.strip()
    desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    row["description"] = (desc.get("content") or "").strip() if desc else ""
    h1s = soup.find_all("h1")
    row["h1_count"] = len(h1s)
    row["h1"] = h1s[0].get_text(" ", strip=True) if h1s else ""
    canon = soup.find("link", rel="canonical")
    row["canonical"] = (canon.get("href") or "").strip() if canon else ""
    robots = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    row["robots"] = (robots.get("content") or "").strip() if robots else ""
    return row


def find_issues(rows):
    """Добавляет к каждой строке список проблем и итоговую оценку важности."""
    ok_rows = [r for r in rows if r["status"] and r["status"] < 400]
    titles = Counter(r["title"] for r in ok_rows if r["title"])
    descs = Counter(r["description"] for r in ok_rows if r["description"])
    for r in rows:
        issues = []
        if r["error"] and r["status"] is None:
            issues.append(("critical", f"Страница недоступна ({r['error']})"))
        elif r["status"] and r["status"] >= 400:
            issues.append(("critical", f"Код ответа {r['status']}"))
        elif not r["error"]:
            t, d = len(r["title"]), len(r["description"])
            if not r["title"]:
                issues.append(("critical", "Нет title"))
            elif t < TITLE_RANGE[0]:
                issues.append(("warning", f"Title короткий ({t} симв.)"))
            elif t > TITLE_RANGE[1]:
                issues.append(("warning", f"Title длинный ({t} симв.)"))
            if titles[r["title"]] > 1 and r["title"]:
                issues.append(("critical", "Дубль title"))
            if not r["description"]:
                issues.append(("warning", "Нет description"))
            elif d < DESC_RANGE[0]:
                issues.append(("warning", f"Description короткий ({d} симв.)"))
            elif d > DESC_RANGE[1]:
                issues.append(("warning", f"Description длинный ({d} симв.)"))
            if descs[r["description"]] > 1 and r["description"]:
                issues.append(("warning", "Дубль description"))
            if r["h1_count"] == 0:
                issues.append(("critical", "Нет H1"))
            elif r["h1_count"] > 1:
                issues.append(("warning", f"Несколько H1 ({r['h1_count']})"))
            if not r["canonical"]:
                issues.append(("info", "Нет canonical"))
            if "noindex" in r["robots"].lower():
                issues.append(("critical", "Страница закрыта noindex"))
        r["issues"] = issues
        levels = {lvl for lvl, _ in issues}
        r["level"] = ("critical" if "critical" in levels else
                      "warning" if "warning" in levels else
                      "info" if "info" in levels else "ok")
    return rows


def run_audit(urls):
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(audit_url, urls))
    return find_issues(rows)
