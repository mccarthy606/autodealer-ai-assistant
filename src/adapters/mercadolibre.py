"""MercadoLibre adapter. Sync listings, import inventory, handle questions."""

import json
import logging
import re
from decimal import Decimal
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.adapters.base import ChannelAdapter

logger = logging.getLogger(__name__)

ML_API_URL = "https://api.mercadolibre.com"


class MercadoLibreAdapter(ChannelAdapter):
    """MercadoLibre adapter. Works in mock mode if tokens are not set."""

    def __init__(self):
        self.token = settings.ml_access_token
        self.user_id = settings.ml_user_id
        self.is_configured = bool(self.token and self.user_id)

    async def send_text(self, to: str, text: str) -> dict:
        """Send answer to ML question. 'to' is the question_id."""
        if not self.is_configured:
            logger.info("[ML MOCK] send_text question_id=%s: %s", to, text[:100])
            return {"status": "mock", "question_id": to}

        url = f"{ML_API_URL}/answers"
        payload = {
            "question_id": int(to),
            "text": text,
        }
        return await self._post(url, payload)

    async def send_images(self, to: str, image_urls: list[str], caption: Optional[str] = None) -> dict:
        """ML doesn't support sending images in answers — send text with URLs."""
        text = caption or ""
        if image_urls:
            text += "\n" + "\n".join(image_urls[:3])
        return await self.send_text(to, text.strip())

    async def sync_listings(self) -> list[dict]:
        """
        Fetch active listings from MercadoLibre using seller user_id.
        Returns list of parsed items.
        """
        if not self.is_configured:
            logger.info("[ML MOCK] sync_listings - no token")
            return []

        url = f"{ML_API_URL}/users/{self.user_id}/items/search?status=active&limit=50"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=self._headers())
                data = resp.json()
                item_ids = data.get("results", [])
                return await self._fetch_items_details(client, item_ids)
        except Exception as e:
            logger.error("ML sync error: %s", e)
            return []

    async def get_questions(self, status: str = "UNANSWERED") -> list[dict]:
        """Fetch unanswered questions."""
        if not self.is_configured:
            return []

        url = f"{ML_API_URL}/questions/search?seller_id={self.user_id}&status={status}&sort=DATE_CREATED_DESC&limit=20"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers())
                data = resp.json()
                return data.get("questions", [])
        except Exception as e:
            logger.error("ML questions error: %s", e)
            return []

    async def get_buyer_contact(self, question_id: str) -> Optional[dict]:
        """
        Fetch buyer contact info from ML question (api_version=4).
        Returns {phone, email, name} or None if unavailable.
        For vehicles category, ML provides contact info when buyer clicks
        'Quiero que me contacten'. Per D-04.
        """
        if not self.is_configured:
            logger.info("[ML MOCK] get_buyer_contact question_id=%s", question_id)
            return None

        url = f"{ML_API_URL}/questions/{question_id}?api_version=4"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code != 200:
                    logger.warning("ML buyer contact fetch failed: status=%s", resp.status_code)
                    return None
                data = resp.json()
                buyer = data.get("from", {})
                phone_data = buyer.get("phone", {})
                if phone_data and phone_data.get("number"):
                    area = phone_data.get("area_code", "")
                    number = phone_data.get("number", "")
                    from src.services.phone_utils import normalize_ar_phone
                    normalized = normalize_ar_phone(area, number)
                    return {
                        "phone": normalized,
                        "email": buyer.get("email"),
                        "name": buyer.get("first_name", ""),
                    }
        except Exception as e:
            logger.warning("ML buyer contact error: %s", e)
        return None

    async def _post(self, url: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                return resp.json()
        except Exception as e:
            logger.error("ML API error: %s", e)
            return {"error": str(e)}

    def _headers(self) -> dict:
        if self.token:
            return {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        return {"Content-Type": "application/json"}

    async def _fetch_items_details(self, client: httpx.AsyncClient, item_ids: list[str]) -> list[dict]:
        """Fetch full details for a list of item IDs."""
        listings = []
        # ML supports multi-get: up to 20 items at once
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i:i + 20]
            ids_str = ",".join(batch)
            try:
                resp = await client.get(
                    f"{ML_API_URL}/items?ids={ids_str}",
                    headers=self._headers(),
                )
                items_data = resp.json()
                for item_wrapper in items_data:
                    item = item_wrapper.get("body", item_wrapper)
                    if item.get("id"):
                        listings.append(_parse_ml_item(item))
            except Exception as e:
                logger.error("ML batch fetch error: %s", e)
                # Fallback: fetch one by one
                for item_id in batch:
                    try:
                        resp = await client.get(
                            f"{ML_API_URL}/items/{item_id}",
                            headers=self._headers(),
                        )
                        item = resp.json()
                        if item.get("id"):
                            listings.append(_parse_ml_item(item))
                    except Exception as e2:
                        logger.error("ML item fetch error %s: %s", item_id, e2)
        return listings


# === Public scraping functions (HTML scraping — API is 403 blocked) ===

async def fetch_seller_items_public(nickname: str) -> list[dict]:
    """
    Fetch all active items from a ML seller by scraping the HTML listing page.
    No access token needed.
    Returns list of parsed items with photos.
    """
    items = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            # Step 1: Scrape listing page(s)
            seen_ids: set[str] = set()
            for page in range(1, 4):  # up to 3 pages
                if page == 1:
                    url = f"https://listado.mercadolibre.com.ar/pagina/{nickname.lower()}/vehiculos/"
                else:
                    url = f"https://listado.mercadolibre.com.ar/pagina/{nickname.lower()}/vehiculos/_Desde_{(page-1)*48+1}"

                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                if resp.status_code != 200:
                    break
                html = resp.text

                page_items = _parse_listing_html(html)
                new_count = 0
                for item in page_items:
                    if item["ml_item_id"] not in seen_ids:
                        seen_ids.add(item["ml_item_id"])
                        items.append(item)
                        new_count += 1

                logger.info("ML scrape page %d: %d new items", page, new_count)
                if new_count < 5:  # last page
                    break

            # Step 2: Fetch additional photos from individual item pages
            for item in items:
                permalink = item.get("permalink", "")
                if permalink:
                    try:
                        extra = await _scrape_item_photos(client, permalink)
                        if extra:
                            existing_set = set(item.get("photos", []))
                            for p in extra:
                                existing_set.add(p)
                            item["photos"] = list(existing_set)[:10]
                    except Exception:
                        pass  # photo fetch failure is non-critical

            logger.info("ML scrape complete: %d items total", len(items))
            return items

    except Exception as e:
        logger.error("ML public fetch error: %s", e)
        return []


async def fetch_single_item_public(item_id: str) -> Optional[dict]:
    """
    Fetch a single ML item by scraping the item page.
    Falls back to API (which may be blocked).
    """
    # Normalize ID
    clean_id = item_id.replace("-", "").replace(" ", "").upper()
    if not clean_id.startswith("MLA"):
        clean_id = "MLA" + clean_id

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            # Try API first (may be blocked)
            try:
                resp = await client.get(f"{ML_API_URL}/items/{clean_id}")
                data = resp.json()
                if data.get("id") and not data.get("error"):
                    parsed = _parse_ml_item(data)
                    # Get description
                    try:
                        desc_resp = await client.get(f"{ML_API_URL}/items/{clean_id}/description")
                        desc_data = desc_resp.json()
                        parsed["description"] = desc_data.get("plain_text", "") or desc_data.get("text", "")
                    except Exception:
                        pass
                    return parsed
            except Exception:
                pass

            # Fallback: search for item on listing page
            logger.info("ML API blocked, trying HTML search for %s", clean_id)
            search_url = f"https://listado.mercadolibre.com.ar/{clean_id}"
            resp = await client.get(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                items = _parse_listing_html(resp.text)
                for item in items:
                    if item["ml_item_id"].replace("-", "") == clean_id:
                        # Fetch photos from item page
                        if item.get("permalink"):
                            extra = await _scrape_item_photos(client, item["permalink"])
                            if extra:
                                item["photos"] = list(set(item.get("photos", []) + extra))[:10]
                        return item

            return None

    except Exception as e:
        logger.error("ML single item fetch error: %s", e)
        return None


async def _scrape_item_photos(client: httpx.AsyncClient, permalink: str) -> list[str]:
    """Fetch photos from an individual ML item page via HTML scraping."""
    try:
        resp = await client.get(permalink, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return []
        html = resp.text

        # Find high-res photo URLs
        photos = re.findall(r'"(https://http2\.mlstatic\.com/D_NQ_NP_[^"]+\.jpg)"', html)
        photos = list(set(photos))
        # Also from data-zoom
        photos2 = re.findall(r'data-zoom="(https://[^"]+\.jpg)"', html)
        photos.extend(photos2)
        return list(set(photos))[:10]
    except Exception:
        return []


def _parse_listing_html(html: str) -> list[dict]:
    """Parse MercadoLibre listing HTML and extract car data."""
    # Extract links with MLA IDs
    item_links = re.findall(
        r'href="(https://[^"]*mercadolibre\.com\.ar/MLA-(\d+)-[^"]*)"', html
    )
    seen: set[str] = set()
    unique_links: list[tuple[str, str]] = []
    for link, mid in item_links:
        if mid not in seen:
            seen.add(mid)
            unique_links.append((link, mid))

    # Extract titles
    titles = re.findall(
        r'class="[^"]*poly-component__title[^"]*"[^>]*>([^<]+)<', html
    )

    # Extract prices
    prices_raw = re.findall(
        r'class="[^"]*andes-money-amount[^"]*"[^>]*aria-label="([^"]*)"', html
    )
    prices = []
    for p in prices_raw:
        nums = re.findall(r'[\d]+', p.replace(".", ""))
        if nums:
            prices.append(int(nums[0]))
        else:
            prices.append(0)

    # Extract images
    images = re.findall(r'data-src="(https://http2\.mlstatic\.com/D_[^"]+)"', html)
    if not images:
        images = re.findall(r'src="(https://http2\.mlstatic\.com/D_[^"]+)"', html)

    # JSON-LD images (more reliable)
    item_images_map: dict[str, list[str]] = {}
    jsonld_match = re.search(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if jsonld_match:
        try:
            ld = json.loads(jsonld_match.group(1))
            for node in ld.get("@graph", []):
                if node.get("@type") == "Product":
                    mid_match = re.search(r'MLA-(\d+)', node.get("url", ""))
                    if mid_match:
                        img = node.get("image", "")
                        if img:
                            item_images_map[mid_match.group(1)] = [img] if isinstance(img, str) else img[:10]
        except Exception:
            pass

    items = []
    for idx, (link, mid) in enumerate(unique_links):
        title = titles[idx].strip() if idx < len(titles) else f"Car MLA{mid}"
        price = prices[idx] if idx < len(prices) else 0
        parsed_title = _parse_title(title)
        brand = parsed_title.get("brand", "")
        model_name = parsed_title.get("model", "")

        if not brand:
            parts = title.strip().split()
            brand = parts[0] if parts else ""
            model_name = parts[1] if len(parts) > 1 else ""

        # Get image(s)
        photos = item_images_map.get(mid, [])
        if not photos and idx < len(images):
            photos = [images[idx]]
        # Upgrade to full-size
        photos = [_upgrade_image_url(p) for p in photos]

        items.append({
            "ml_item_id": f"MLA{mid}",
            "title": title,
            "brand": brand,
            "model": model_name,
            "year": parsed_title.get("year"),
            "km": None,
            "price": price,
            "currency": "ARS",
            "condition": "used",
            "status": "available",
            "photos": photos,
            "permalink": link,
            "location": "",
            "description": f"Imported from MercadoLibre: MLA{mid}",
        })

    return items


def _upgrade_image_url(url: str) -> str:
    """Convert ML thumbnail to full-size image."""
    url = re.sub(r'-[A-Z]\.(\w+)$', r'-F.\1', url)
    url = url.replace('.webp', '.jpg')
    return url


# === Parsers ===

def _parse_ml_item(item: dict) -> dict:
    """Parse a full ML item response into our format."""
    photos = []
    for pic in item.get("pictures", []):
        url = pic.get("secure_url") or pic.get("url")
        if url:
            photos.append(url)

    # Extract brand/model from attributes
    brand = ""
    model = ""
    year = None
    km = None
    for attr in item.get("attributes", []):
        attr_id = attr.get("id", "")
        val = attr.get("value_name", "") or ""
        if attr_id == "BRAND":
            brand = val
        elif attr_id == "MODEL":
            model = val
        elif attr_id == "VEHICLE_YEAR":
            try:
                year = int(val)
            except (ValueError, TypeError):
                pass
        elif attr_id == "KILOMETERS":
            try:
                km = int(val.replace(" km", "").replace(".", "").replace(",", "").strip())
            except (ValueError, TypeError):
                pass

    # Fallback: parse title
    if not brand or not model:
        title = item.get("title", "")
        parts = _parse_title(title)
        brand = brand or parts.get("brand", "")
        model = model or parts.get("model", "")
        if not year:
            year = parts.get("year")

    condition = "used"
    ml_condition = item.get("condition", "")
    if ml_condition == "new":
        condition = "zero_km"

    return {
        "ml_item_id": item.get("id", ""),
        "title": item.get("title", ""),
        "brand": brand,
        "model": model,
        "year": year,
        "km": km,
        "price": item.get("price"),
        "currency": item.get("currency_id", "ARS"),
        "condition": condition,
        "status": "available",
        "permalink": item.get("permalink", ""),
        "thumbnail": item.get("thumbnail", ""),
        "photos": photos,
        "location": _extract_location(item),
        "description": "",
    }


def _parse_ml_search_result(result: dict) -> dict:
    """Parse a search result (less data than full item)."""
    brand = ""
    model = ""
    year = None
    km = None

    for attr in result.get("attributes", []):
        attr_id = attr.get("id", "")
        val = attr.get("value_name", "") or ""
        if attr_id == "BRAND":
            brand = val
        elif attr_id == "MODEL":
            model = val
        elif attr_id == "VEHICLE_YEAR":
            try:
                year = int(val)
            except (ValueError, TypeError):
                pass
        elif attr_id == "KILOMETERS":
            try:
                km = int(val.replace(" km", "").replace(".", "").replace(",", "").strip())
            except (ValueError, TypeError):
                pass

    if not brand or not model:
        parts = _parse_title(result.get("title", ""))
        brand = brand or parts.get("brand", "")
        model = model or parts.get("model", "")
        if not year:
            year = parts.get("year")

    condition = "used"
    if result.get("condition") == "new":
        condition = "zero_km"

    thumbnail = result.get("thumbnail", "")
    # Upgrade thumbnail to larger image
    if thumbnail:
        thumbnail = thumbnail.replace("-I.jpg", "-O.jpg")

    return {
        "ml_item_id": result.get("id", ""),
        "title": result.get("title", ""),
        "brand": brand,
        "model": model,
        "year": year,
        "km": km,
        "price": result.get("price"),
        "currency": result.get("currency_id", "ARS"),
        "condition": condition,
        "status": "available",
        "permalink": result.get("permalink", ""),
        "thumbnail": thumbnail,
        "photos": [thumbnail] if thumbnail else [],
        "location": _extract_location(result),
        "description": "",
    }


def _extract_location(item: dict) -> str:
    """Extract location string from item."""
    loc = item.get("seller_address", {})
    city = loc.get("city", {}).get("name", "")
    state = loc.get("state", {}).get("name", "")
    parts = [p for p in [city, state] if p]
    return ", ".join(parts) if parts else ""


def _parse_title(title: str) -> dict:
    """Fallback: parse brand/model/year from listing title."""
    result = {}
    # Year
    m = re.search(r"\b(19|20)\d{2}\b", title)
    if m:
        result["year"] = int(m.group())
    # Known brands
    t = title.lower()
    brands = ["toyota", "ford", "volkswagen", "fiat", "chevrolet", "honda",
              "nissan", "renault", "peugeot", "citroen", "hyundai", "kia",
              "jeep", "ram", "dodge", "bmw", "mercedes", "audi", "mitsubishi",
              "suzuki", "chery", "geely", "haval"]
    for b in brands:
        if b in t:
            result["brand"] = b.title()
            # Model = next word after brand in title
            idx = t.index(b) + len(b)
            rest = title[idx:].strip()
            words = rest.split()
            if words:
                result["model"] = words[0].strip(",.-")
            break
    return result


def parse_incoming_question(payload: dict) -> Optional[dict]:
    """
    Parse incoming ML webhook notification for questions.
    Returns {question_id, item_id, text, from_id} or None.
    """
    try:
        topic = payload.get("topic")
        if topic != "questions":
            return None
        resource = payload.get("resource", "")
        question_id = resource.split("/")[-1]
        return {
            "question_id": question_id,
            "resource": resource,
            "user_id": payload.get("user_id"),
        }
    except Exception:
        return None


async def get_dealership_by_ml(
    db: AsyncSession, ml_user_id: str
) -> Optional["Dealership"]:
    """
    Look up a Dealership by ml_user_id.
    Returns None if no dealership configured for that user_id.
    """
    from src.db.models import Dealership
    if not ml_user_id:
        return None
    stmt = select(Dealership).where(Dealership.ml_user_id == str(ml_user_id))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def parse_ml_url(url: str) -> Optional[dict]:
    """
    Parse a MercadoLibre listing URL and extract whatever info we can.

    Example URL:
    https://auto.mercadolibre.com.ar/MLA-1666773531-toyota-yaris-15-107cv-xls-pack-cvt-sedan-_JM

    Returns dict with: ml_item_id, brand, model, trim, title (parsed from slug).
    """
    url = url.strip()
    if not url:
        return None

    # Extract MLA ID
    m = re.search(r'MLA-?(\d{6,15})', url)
    if not m:
        return None

    ml_item_id = f"MLA{m.group(1)}"

    # Extract slug (human-readable part of URL)
    slug_match = re.search(r'MLA-?\d+-(.+?)(?:_JM|$|\?|#)', url)
    slug = slug_match.group(1) if slug_match else ""

    # Parse slug: replace hyphens with spaces, clean up
    slug_clean = slug.replace("-", " ").strip()

    # Try to identify brand from known list
    known_brands = {
        "toyota": "Toyota", "ford": "Ford", "volkswagen": "Volkswagen", "vw": "Volkswagen",
        "fiat": "Fiat", "chevrolet": "Chevrolet", "honda": "Honda", "nissan": "Nissan",
        "renault": "Renault", "peugeot": "Peugeot", "citroen": "Citroën", "citroën": "Citroën",
        "hyundai": "Hyundai", "kia": "Kia", "jeep": "Jeep", "ram": "Ram",
        "dodge": "Dodge", "bmw": "BMW", "mercedes": "Mercedes-Benz", "audi": "Audi",
        "mitsubishi": "Mitsubishi", "suzuki": "Suzuki", "chery": "Chery",
        "geely": "Geely", "haval": "Haval", "ds": "DS",
    }

    slug_lower = slug_clean.lower()
    brand = ""
    model = ""
    trim = ""

    for key, brand_name in known_brands.items():
        if slug_lower.startswith(key + " ") or slug_lower == key:
            brand = brand_name
            rest = slug_clean[len(key):].strip()
            words = rest.split()
            if words:
                model = words[0].title()
                trim = " ".join(words[1:]).title() if len(words) > 1 else ""
            break

    if not brand and slug_clean:
        # Fallback: first word = brand, second = model
        words = slug_clean.split()
        brand = words[0].title() if words else ""
        model = words[1].title() if len(words) > 1 else ""
        trim = " ".join(words[2:]).title() if len(words) > 2 else ""

    # Build human-readable title
    title_parts = [brand, model]
    if trim:
        title_parts.append(trim)
    title = " ".join(p for p in title_parts if p)

    return {
        "ml_item_id": ml_item_id,
        "brand": brand,
        "model": model,
        "trim": trim,
        "title": title or slug_clean.title(),
        "permalink": url.split("#")[0].split("?")[0],  # Clean URL
    }
