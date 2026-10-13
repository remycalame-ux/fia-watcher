import json
import os
import re
import time
from html import unescape
from urllib.parse import urljoin

import requests

BASE = "https://www.fia.com"
MAIN_URL = BASE + "/documents/championships/fia-formula-one-world-championship-14/season/season-2026-2072"
WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
SEEN_FILE = "seen.json"
EXTRA_GP_LISTS = 3   # nombre de GP repliés à surveiller en plus du GP déplié
MAX_POSTS_PER_RUN = 20

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RedactionF1Bot/1.0)"}
PDF_RE = re.compile(
    r'<a[^>]+href="([^"]*?/system/files/decision-document/[^"]+?\.pdf)"[^>]*>(.*?)</a>',
    re.S,
)
NOJS_RE = re.compile(r'href="([^"]*decision-document-list/nojs/\d+)"')


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    # Au cas où la réponse serait du JSON avec des "\/" échappés
    return r.text.replace("\\/", "/").replace('\\"', '"')


def extract_docs(html):
    docs = {}
    for href, label in PDF_RE.findall(html):
        url = urljoin(BASE, href)
        title = unescape(re.sub(r"<[^>]+>", "", label)).strip()
        title = re.sub(r"\s+", " ", title)
        if not title:
            title = url.rsplit("/", 1)[-1].replace("_", " ").replace(".pdf", "")
        docs[url] = title
    return docs


def collect():
    main_html = get(MAIN_URL)
    docs = extract_docs(main_html)
    nojs_links = list(dict.fromkeys(NOJS_RE.findall(main_html)))
    for link in nojs_links[:EXTRA_GP_LISTS]:
        try:
            docs.update(extract_docs(get(urljoin(BASE, link))))
        except Exception as e:
            print("Erreur sur", link, e)
    return docs


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return None


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=1)


def post(title, url):
    payload = {"content": f"📄 **Nouveau document FIA**\n{title}\n{url}"}
    r = requests.post(WEBHOOK, json=payload, timeout=30)
    if r.status_code == 429:
        time.sleep(float(r.json().get("retry_after", 2)))
        r = requests.post(WEBHOOK, json=payload, timeout=30)
    r.raise_for_status()


def main():
    docs = collect()
    print(f"{len(docs)} documents trouvés")
    if not docs:
        print("Rien trouvé, la page a peut-être changé. On s'arrête.")
        return

    seen = load_seen()
    if seen is None:
        # Premier lancement : on mémorise tout sans rien poster
        save_seen(set(docs))
        print("Premier lancement : documents existants mémorisés, rien posté.")
        return

    new_urls = [u for u in reversed(list(docs)) if u not in seen]  # plus anciens d'abord
    for url in new_urls[:MAX_POSTS_PER_RUN]:
        post(docs[url], url)
        seen.add(url)
        time.sleep(1)
    save_seen(seen)
    print(f"{min(len(new_urls), MAX_POSTS_PER_RUN)} document(s) posté(s)")


if __name__ == "__main__":
    main()
