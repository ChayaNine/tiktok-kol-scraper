"""
Classification utilities.
All rules are intentionally simple and transparent.
"""

from typing import Optional


# ── Influencer size ──────────────────────────────────────────────────────────

def classify_influencer_size(followers: Optional[int]) -> str:
    if followers is None:
        return "Unknown"
    if followers >= 1_000_000:
        return "Mega"
    if followers >= 100_000:
        return "MOF"       # Middle-of-Funnel / Macro
    if followers >= 10_000:
        return "Micro"
    return "Nano"


# ── Creator type ─────────────────────────────────────────────────────────────

# Words in bio / video descriptions that hint at KOC (selling / product focus)
KOC_KEYWORDS = [
    "ขาย", "สั่งซื้อ", "ลิงก์", "link", "shop", "shopee", "lazada",
    "tiktok shop", "โปรโมชัน", "ส่วนลด", "discount", "review สินค้า",
    "รีวิวสินค้า", "แนะนำสินค้า", "demo", "ทดสอบ", "ทดลอง",
]

# Words that hint at KOL (educational / authoritative)
KOL_KEYWORDS = [
    "สอน", "tutorial", "how to", "วิธี", "เทคนิค", "เคล็ดลับ",
    "tips", "แนะนำ", "รีวิว", "review", "ทดสอบ", "เปรียบเทียบ",
    "compare", "อธิบาย", "explain", "ช่างมืออาชีพ",
]


def classify_creator_type(
    bio: Optional[str],
    video_descriptions: Optional[list[str]] = None,
    avg_view: Optional[float] = None,
    followers: Optional[int] = None,
) -> str:
    """
    Simple keyword + heuristic approach.
    Returns: KOC / KOL / Creator / Unknown
    """
    if bio is None and not video_descriptions:
        return "Unknown"

    combined_text = ""
    if bio:
        combined_text += bio.lower()
    if video_descriptions:
        combined_text += " ".join(video_descriptions).lower()

    koc_score = sum(1 for kw in KOC_KEYWORDS if kw in combined_text)
    kol_score = sum(1 for kw in KOL_KEYWORDS if kw in combined_text)

    # Boost KOL score if the creator has good view numbers relative to followers
    if avg_view and followers and followers > 0:
        view_ratio = avg_view / followers
        if view_ratio > 0.5:
            kol_score += 2

    if koc_score == 0 and kol_score == 0:
        return "Creator"

    if koc_score > kol_score:
        return "KOC"
    if kol_score > koc_score:
        return "KOL"

    # Tie: prefer KOL for creators with higher follower counts
    if followers and followers >= 50_000:
        return "KOL"
    return "KOC"


# ── Category ─────────────────────────────────────────────────────────────────

DIY_KEYWORDS = [
    "ซ่อม", "ติดตั้ง", "เจาะ", "ขัน", "ประกอบ", "ช่าง", "เฟอร์นิเจอร์",
    "รีโนเวท", "diy", "สว่าน", "ไขควง", "น้ำรั่ว", "ประตู", "บ้าน",
]

GARDEN_KEYWORDS = [
    "สวน", "ต้นไม้", "ปลูก", "ตัดกิ่ง", "ดอกไม้", "ผัก", "เกษตร",
    "สวนครัว", "ไร่", "แปลง", "มะม่วง", "มะขาม", "garden",
]


def classify_category(
    bio: Optional[str],
    video_descriptions: Optional[list[str]] = None,
    source_hashtag: Optional[str] = None,
) -> str:
    combined = ""
    if bio:
        combined += bio.lower()
    if video_descriptions:
        combined += " ".join(video_descriptions).lower()
    if source_hashtag:
        combined += source_hashtag.lower()

    diy_score    = sum(1 for kw in DIY_KEYWORDS    if kw in combined)
    garden_score = sum(1 for kw in GARDEN_KEYWORDS if kw in combined)

    if diy_score == 0 and garden_score == 0:
        return "Unknown"
    if diy_score >= garden_score:
        return "DIY"
    return "Garden"
