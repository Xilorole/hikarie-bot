from .models import Badge, BadgeType

# Define the badge types.
BadgeTypes = [
    BadgeType(
        id=1,
        name="welcome",
        description="出社登録BOTを初めて利用した",
    ),
    BadgeType(
        id=2,
        name="fastest_arrival",
        description="最速で出社登録をした",
    ),
    BadgeType(id=3, name="arrival_count", description="たくさん出社登録をした"),
    BadgeType(id=4, name="straight_flash", description="連続して出社した"),
    BadgeType(id=5, name="time_window", description="時間帯による出社登録"),
    BadgeType(id=6, name="kiriban", description="特定の出社登録の回数で付与される"),
    BadgeType(
        id=7, name="long_time_no_see", description="長期間出社登録がない状態で復帰した"
    ),
    BadgeType(id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"),
    BadgeType(id=9, name="reincarnation", description="転生した"),
    BadgeType(id=10, name="item_shop", description="道具屋を利用した"),
    BadgeType(id=11, name="used_log_report", description="ログ分析レポートを利用した"),
    BadgeType(
        id=12, name="seasonal_rank", description="特定のシーズンでランクインした"
    ),
    BadgeType(id=13, name="reactioner", description="リアクションをした"),
    BadgeType(id=14, name="advance_notice_success", description="予告出社を成功させた"),
]


Badges = [
    # BadgeType id=1, name="welcome", description="出社登録BOTを初めて利用した"
    Badge(
        message="はじめての出社登録",
        condition="出社登録BOTを初めて利用した",
        level=1,
        score=1,
        badge_type_id=1,
    ),
    # BadgeType id=2, name="fastest_arrival", description="最速で出社登録をした"
    Badge(
        message="光の速さの出社",
        condition="最速で出社登録を行った",
        level=1,
        score=1,
        badge_type_id=2,
    ),
    # BadgeType id=3, name="arrival_count", description="たくさん出社登録をした"
    Badge(
        message="出社登録ビギナー",
        condition="5回出社登録した",
        level=1,
        score=1,
        badge_type_id=3,
    ),
    Badge(
        message="出社登録ユーザー",
        condition="20回出社登録した",
        level=2,
        score=1,
        badge_type_id=3,
    ),
    Badge(
        message="出社登録マスター",
        condition="100回出社登録した",
        level=3,
        score=1,
        badge_type_id=3,
    ),
    # BadgeType id=4, name="straight_flash", description="連続して出社した"
    Badge(
        message="ストレートフラッ出社",
        condition="5日連続で出社した",
        level=1,
        score=1,
        badge_type_id=4,
    ),
    Badge(
        message="ロイヤルストレートフラッ出社",
        condition="異なる時間帯に5日連続で出社した",
        level=2,
        score=1,
        badge_type_id=4,
    ),
    Badge(
        message="ウルトラロイヤルストレートフラッ出社",
        condition="異なる連続した時間帯に5日連続で出社した",
        level=3,
        score=1,
        badge_type_id=4,
    ),
    # BadgeType id=5, name="time_window", description="時間帯による出社登録"
    Badge(
        message="朝型出社",
        condition="6-9時の間に出社登録をした",
        level=3,
        score=1,
        badge_type_id=5,
    ),
    Badge(
        message="出社",
        condition="9-11時の間に出社登録をした",
        level=2,
        score=1,
        badge_type_id=5,
    ),
    Badge(
        message="遅めの出社",
        condition="11時以降に出社登録をした",
        level=1,
        score=1,
        badge_type_id=5,
    ),
    # BadgeType id=6, name="kiriban", description="特定の出社登録の回数で付与される"
    Badge(
        message="100番目のお客様",
        condition="100回目の出社登録をした",
        level=1,
        score=1,
        badge_type_id=6,
    ),
    # BadgeType id=7, name="long_time_no_see",
    #           description="長期間出社登録がない状態で復帰した"  # noqa: ERA001
    Badge(
        message="2週間ぶりですね、元気にしていましたか？",  # noqa: RUF001
        condition="14日以上出社登録がなかったが復帰した",
        level=1,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        message="1か月ぶりですね、おかえりなさい。",
        condition="30日以上出社登録がなかったが復帰した",
        level=2,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        message="2か月ぶりですね、顔を忘れるところでした。",
        condition="2か月以上出社登録がなかったが復帰した",
        level=4,
        score=1,
        badge_type_id=7,
    ),
    Badge(
        message="半年ぶりですね、むしろ初めまして。",
        condition="半年以上出社登録がなかったが復帰した",
        level=4,
        score=1,
        badge_type_id=7,
    ),
    # BadgeType id=8, name="lucky_you_guys", description="同じ時間に出社登録をした"
    Badge(
        message="幸運なふたり",
        condition="分単位で同じ時間に出社登録をした",
        level=1,
        score=1,
        badge_type_id=8,
    ),
    Badge(
        message="幸運なトリオ",
        condition="分単位で同じ時間に出社登録をした",
        level=2,
        score=1,
        badge_type_id=8,
    ),
    # BadgeType id=9, name="reincarnation", description="転生した"
    Badge(
        message="新しくなったあなた",
        condition="1回目の転生をした",
        level=1,
        score=1,
        badge_type_id=9,
    ),
    Badge(
        message="2回目の目覚め",
        condition="2回目の転生をした",
        level=2,
        score=1,
        badge_type_id=9,
    ),
    # BadgeType id=10, name="item_shop", description="道具屋を利用した"
    Badge(
        message="道具屋利用",
        condition="道具屋を利用した",
        level=1,
        score=1,
        badge_type_id=10,
    ),
    # BadgeType id=11, name="used_log_report", description="ログ分析レポートを利用した"
    Badge(
        message="ログ分析レポート利用",
        condition="ログ分析レポートを利用した",
        level=1,
        score=1,
        badge_type_id=11,
    ),
    # BadgeType id=12, name="seasonal_rank",
    #           description="特定のシーズンでランクインした" # noqa: ERA001
    Badge(
        message="Top of Top",
        condition="特定のシーズンで首位になった",
        level=2,
        score=1,
        badge_type_id=12,
    ),
    Badge(
        message="Seasonal Ranker",
        condition="特定のシーズンで3位以内になった",
        level=1,
        score=1,
        badge_type_id=12,
    ),
    # BadgeType id=13, name="reactioner", description="リアクションをした"
    Badge(
        message="盛り上げ役",
        condition="10回リアクションをした",
        level=1,
        score=1,
        badge_type_id=13,
    ),
    Badge(
        message="大衆の扇動者",
        condition="50回リアクションをした",
        level=2,
        score=1,
        badge_type_id=13,
    ),
    # BadgeType id=14, name="advance_notice_success", description="予告出社を成功させた"
    Badge(
        message="予告出社成功",
        condition="予告出社を成功させた",
        level=1,
        score=1,
        badge_type_id=14,
    ),
]
