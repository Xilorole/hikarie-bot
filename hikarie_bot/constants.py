from functools import lru_cache

BADGE_TYPES_TO_CHECK: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 17, 18]


@lru_cache(maxsize=1)
def _generate_kiriban_id_counts(under: int = 10000) -> list[tuple[int, int]]:
    """Generate KIRIBAN_ID_COUNTS dynamically.

    Returns list of (badge_id, kiriban_count) tuples starting from badge_id 6001.
    """
    # Import here to avoid circular dependency
    from hikarie_bot.db_data.badges import KiribanGenerator

    generator = KiribanGenerator()
    kiriban_numbers = list(generator.generate_kiriban(under=under))
    return [(kiriban.id, kiriban.number) for kiriban in kiriban_numbers]


# Dynamic KIRIBAN_ID_COUNTS that generates automatically
KIRIBAN_ID_COUNTS: list[tuple[int, int]] = _generate_kiriban_id_counts()


ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/d9bddfb0-199c-4252-b821-52a62954811f"
NOT_ACHIEVED_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/86451acf-82ce-4ec2-b72e-7c6b9f728efb"
TAKEN_6XX_BADGE_IMAGE_URL = "https://gist.github.com/user-attachments/assets/e71a6c8c-b28e-44dd-a4e5-b77395100998"

CONTEXT_ITEM_MAX = 10
MAX_URL_DISPLAY_LENGTH = 100
