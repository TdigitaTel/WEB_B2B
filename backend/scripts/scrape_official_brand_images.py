"""Localiza imágenes oficiales de GEBO, IBIDE y GENEBRE y opcionalmente las importa.

El modo predeterminado solo genera un CSV auditable. ``--apply`` guarda únicamente
coincidencias de alta confianza en ``products.image_data``.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx
from sqlalchemy import func, or_, select

from app.db import SessionLocal
from app.erp_db import image_media_type, normalize_image_data
from app.models import Brand, Product


USER_AGENT = "BermudezUlloa-OfficialCatalogImporter/1.0 (+catalog image audit)"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SOURCES = {
    "GEBO": {
        "seeds": ["https://www.gebo.group/en/c/Products/"],
        "hosts": {"gebo.group", "www.gebo.group"},
    },
    "IBIDE": {
        "seeds": ["https://ibide.com/", "https://www.suministros-de-fontaneria.es/shop/?lang=es"],
        "hosts": {"ibide.com", "www.ibide.com", "suministros-de-fontaneria.es", "www.suministros-de-fontaneria.es"},
    },
    "GENEBRE": {
        "seeds": ["https://www.genebre.es/"],
        "hosts": {"genebre.es", "www.genebre.es"},
    },
}


def compact(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.meta_images: list[str] = []
        self.json_ld: list[str] = []
        self.text: list[str] = []
        self.title: list[str] = []
        self._in_title = False
        self._in_json = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        elif tag == "img":
            src = values.get("src") or values.get("data-src") or values.get("data-lazy-src")
            if src:
                self.images.append((src, values.get("alt") or values.get("title") or ""))
        elif tag == "meta" and (values.get("property") in {"og:image", "twitter:image"} or values.get("name") == "twitter:image"):
            if values.get("content"):
                self.meta_images.append(values["content"])
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and values.get("type") == "application/ld+json":
            self._in_json = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_json = False

    def handle_data(self, data):
        value = data.strip()
        if not value:
            return
        if self._in_title:
            self.title.append(value)
        elif self._in_json:
            self.json_ld.append(value)
        else:
            self.text.append(value)


@dataclass
class Candidate:
    product: Product
    brand: str
    page_url: str
    image_url: str
    score: int
    reason: str


def robots_for(client: httpx.Client, url: str, cache: dict[str, RobotFileParser]) -> RobotFileParser:
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in cache:
        parser = RobotFileParser()
        try:
            response = client.get(f"{root}/robots.txt")
            parser.parse(response.text.splitlines() if response.is_success else [])
        except Exception:
            parser.parse([])
        cache[root] = parser
    return cache[root]


def json_images_and_refs(parser: PageParser) -> tuple[list[str], set[str]]:
    images: list[str] = []
    refs: set[str] = set()
    for raw in parser.json_ld:
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                for key in ("sku", "mpn", "productID"):
                    if item.get(key):
                        refs.add(compact(str(item[key])))
                image = item.get("image")
                if isinstance(image, str):
                    images.append(image)
                elif isinstance(image, list):
                    images.extend(str(value) for value in image if isinstance(value, str))
                stack.extend(value for value in item.values() if isinstance(value, (dict, list)))
    return images, refs


def useful_image(url: str) -> bool:
    lowered = url.lower()
    return url.startswith("http") and not any(word in lowered for word in ("logo", "icon", "favicon", "sprite", "banner", "header", "footer"))


def useful_page(url: str) -> bool:
    """Evita descargar documentos y recursos que no pueden contener una ficha."""
    path = urlparse(url).path.lower()
    return not path.endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".xml"))


def choose_image(page_url: str, parser: PageParser, reference: str) -> tuple[str, int, str] | None:
    json_images, json_refs = json_images_and_refs(parser)
    ref = compact(reference)
    candidates: list[tuple[str, str]] = []
    candidates.extend((urljoin(page_url, value), "structured") for value in json_images)
    candidates.extend((urljoin(page_url, value), "meta") for value in parser.meta_images)
    candidates.extend((urljoin(page_url, value), f"img:{alt}") for value, alt in parser.images)
    best = None
    for url, origin in candidates:
        if not useful_image(url):
            continue
        score = 65 if origin == "structured" else 55 if origin == "meta" else 30
        if ref and ref in compact(url + " " + origin):
            score += 40
        if ref in json_refs:
            score += 40
        value = (url, min(score, 100), origin)
        if best is None or value[1] > best[1]:
            best = value
    return best


def products_for_brand(db, brand: str) -> list[Product]:
    name = brand.upper()
    return db.scalars(
        select(Product).join(Brand).where(Product.active.is_(True)).where(or_(
            func.upper(Brand.name).contains(name),
            func.upper(Product.short_description).contains(name),
            func.upper(Product.original_description).contains(name),
        )).order_by(Product.id)
    ).all()


def crawl_brand(client: httpx.Client, brand: str, products: list[Product], max_pages: int, delay: float) -> list[Candidate]:
    source = SOURCES[brand]
    queue = deque(source["seeds"])
    visited: set[str] = set()
    robots: dict[str, RobotFileParser] = {}
    references: dict[str, list[Product]] = defaultdict(list)
    for product in products:
        reference = compact(product.manufacturer_reference)
        if len(reference) >= 4:
            references[reference].append(product)
    matches: dict[int, Candidate] = {}
    while queue and len(visited) < max_pages:
        url = urldefrag(queue.popleft())[0]
        if url in visited or urlparse(url).netloc.lower() not in source["hosts"]:
            continue
        visited.add(url)
        if not robots_for(client, url, robots).can_fetch(USER_AGENT, url):
            continue
        try:
            response = client.get(url)
            if not response.is_success or "text/html" not in response.headers.get("content-type", ""):
                continue
            parser = PageParser(); parser.feed(response.text)
        except Exception as exc:
            print({"brand": brand, "url": url, "status": "error", "detail": str(exc)})
            continue
        title = " ".join(parser.title)
        searchable = compact(title + " " + " ".join(parser.text))
        page_ref_candidates = [ref for ref in references if ref in searchable or ref in compact(url)]
        for ref in page_ref_candidates:
            selected = choose_image(str(response.url), parser, ref)
            if not selected:
                continue
            image_url, image_score, origin = selected
            direct = ref in compact(url + " " + title) or image_score >= 90
            score = min(100, image_score + (25 if direct else 0))
            for product in references[ref]:
                candidate = Candidate(product, brand, str(response.url), image_url, score,
                                      f"referencia exacta; {origin}{'; URL/título' if direct else ''}")
                current = matches.get(candidate.product.id)
                if current is None or candidate.score > current.score:
                    matches[candidate.product.id] = candidate
        for href in parser.links:
            linked = urldefrag(urljoin(str(response.url), href))[0]
            parsed = urlparse(linked)
            if (parsed.scheme in {"http", "https"} and parsed.netloc.lower() in source["hosts"]
                    and useful_page(linked) and linked not in visited):
                queue.append(linked)
        if delay:
            time.sleep(delay)
    print({"brand": brand, "pages": len(visited), "products": len(products), "candidates": len(matches)})
    return list(matches.values())


def download_and_apply(client: httpx.Client, db, candidate: Candidate, overwrite: bool) -> str:
    product = candidate.product
    if product.image_data and not overwrite:
        return "existing_image"
    if candidate.score < 80:
        return "review_required"
    response = client.get(candidate.image_url, headers={"Referer": candidate.page_url})
    response.raise_for_status()
    declared_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if declared_type and not declared_type.startswith("image/"):
        raise ValueError(f"El servidor devolvió {declared_type} en vez de una imagen")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise ValueError("Imagen superior a 10 MB")
    data = normalize_image_data(response.content)
    media_type = image_media_type(data)
    if not media_type.startswith("image/"):
        raise ValueError("El recurso no es una imagen compatible")
    product.image_data = data
    product.image_media_type = media_type
    product.image_source_url = str(response.url)
    product.image_source_provider = f"{candidate.brand} sitio oficial"
    product.image_sha256 = hashlib.sha256(data).hexdigest()
    db.commit()
    return "imported"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brands", nargs="+", default=list(SOURCES), choices=list(SOURCES))
    parser.add_argument("--output", default="/tmp/official_brand_image_candidates.csv")
    parser.add_argument("--max-pages", type=int, default=400)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--apply", action="store_true", help="Guarda coincidencias con puntuación >= 80 en PostgreSQL")
    parser.add_argument("--overwrite", action="store_true", help="Sustituye imágenes existentes; requiere --apply")
    args = parser.parse_args()
    if args.overwrite and not args.apply:
        parser.error("--overwrite requiere --apply")
    candidates: list[Candidate] = []
    stats: dict[str, int] = {}
    with SessionLocal() as db, httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for brand in args.brands:
            candidates.extend(crawl_brand(client, brand, products_for_brand(db, brand), args.max_pages, args.delay))
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=("sku", "manufacturer_reference", "brand", "description", "page_url", "image_url", "score", "reason", "status"))
            writer.writeheader()
            for candidate in sorted(candidates, key=lambda item: (item.brand, item.product.sku)):
                status = "candidate"
                if args.apply:
                    try:
                        status = download_and_apply(client, db, candidate, args.overwrite)
                    except Exception as exc:
                        db.rollback(); status = f"error: {exc}"
                stats[status] = stats.get(status, 0) + 1
                writer.writerow({"sku": candidate.product.sku, "manufacturer_reference": candidate.product.manufacturer_reference,
                                 "brand": candidate.brand, "description": candidate.product.short_description,
                                 "page_url": candidate.page_url, "image_url": candidate.image_url,
                                 "score": candidate.score, "reason": candidate.reason, "status": status})
    print({"status": "ok", "output": str(Path(args.output)), "candidates": len(candidates), "results": stats})


if __name__ == "__main__":
    main()
