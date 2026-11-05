from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/d9bddfb0-199c-4252-b821-52a62954811f"
NOT_ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/86451acf-82ce-4ec2-b72e-7c6b9f728efb"
# a weekday that is not a business day (a holiday) in the attendance history, served like the item images
DAY_OFF_IMAGE_URL = "https://raw.githubusercontent.com/Xilorole/hikarie-bot/main/assets/history/day_off.png"

CONTEXT_ITEM_MAX = 10

# The item images (assets/items/<item id>.png), served from the public repository's default branch.
ITEM_IMAGE_BASE_URL = "https://raw.githubusercontent.com/Xilorole/hikarie-bot/main/assets/items"
