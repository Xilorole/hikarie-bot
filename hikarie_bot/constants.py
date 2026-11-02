from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/d9bddfb0-199c-4252-b821-52a62954811f"
NOT_ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/86451acf-82ce-4ec2-b72e-7c6b9f728efb"

CONTEXT_ITEM_MAX = 10

# Public URLs of the item images shown on the item cards, by item ID; an item without one has no icon.
ITEM_IMAGE_URLS: dict[str, str] = {}
