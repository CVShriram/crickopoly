"""Centralized, easily tunable game balance configuration.

Every number that affects gameplay lives here. The game engine never hardcodes
prices, probabilities or rewards; it reads them from this module so that balance
changes require no engine edits.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Core rules
# ---------------------------------------------------------------------------
STARTING_MONEY = 1000
SALARY = 100                      # collected when passing or landing on START
MAX_PLAYERS = 4
MIN_PLAYERS = 2
DICE_COUNT = 2
DICE_SIDES = 6
MAX_CONSECUTIVE_DOUBLES = 3
AUCTION_DURATION_SECONDS = 15
DECISION_TIMEOUT_SECONDS = 12

# Targeting rule for bowler attacks: "random" (default), "weakest", "strongest"
BATSMAN_TARGETING = "random"

# Starter asset given to every player so the wicket mechanic matters immediately
STARTER_BATSMAN = {
    "name": "Starter Batsman",
    "category": "starter",
    "wickets": 3,
    "rent": 25,
    "runs": 2,
}

# ---------------------------------------------------------------------------
# Batsmen — income and running between the wickets
# ---------------------------------------------------------------------------
BATSMEN: dict[str, dict] = {
    "beginner": {
        "name": "Beginner Batsman", "price": 100, "wickets": 2,
        "rent": 40, "runs": 3, "upgrade_cost": 60, "ability": None,
        "blurb": "A dependable opener. Low rent, low risk.",
    },
    "average": {
        "name": "Average Batsman", "price": 200, "wickets": 3,
        "rent": 80, "runs": 5, "upgrade_cost": 110, "ability": None,
        "blurb": "Consistent run scorer with a little more staying power.",
    },
    "good": {
        "name": "Good Batsman", "price": 350, "wickets": 4,
        "rent": 140, "runs": 8, "upgrade_cost": 190, "ability": "steady",
        "blurb": "Reduces the chance of losing a wicket by 10%.",
    },
    "star": {
        "name": "Star Batsman", "price": 500, "wickets": 5,
        "rent": 220, "runs": 12, "upgrade_cost": 270, "ability": "quick",
        "blurb": "Earns +20% runs when opponents visit.",
    },
    "elite": {
        "name": "Elite Batsman", "price": 750, "wickets": 7,
        "rent": 350, "runs": 17, "upgrade_cost": 400, "ability": "resilient",
        "blurb": "Takes one fewer wicket from swing attacks.",
    },
    "legendary": {
        "name": "Legendary Batsman", "price": 1000, "wickets": 10,
        "rent": 500, "runs": 24, "upgrade_cost": 550, "ability": "icon",
        "blurb": "Generates premium income, runs and crowd bonuses.",
    },
}

# ---------------------------------------------------------------------------
# Bowlers — attacking assets
# ---------------------------------------------------------------------------
BOWLERS: dict[str, dict] = {
    "tier1": {"name": "Club Bowler", "price": 300, "fee": 100,
              "upgrade_cost": 180, "blurb": "Premium defensive property. Landing fee 100; takes one wicket."},
    "tier2": {"name": "County Bowler", "price": 500, "fee": 200,
              "upgrade_cost": 300, "blurb": "Strong attack. Landing fee 200; takes one wicket."},
    "tier3": {"name": "International Bowler", "price": 800, "fee": 350,
              "upgrade_cost": 480, "blurb": "Elite attack. Landing fee 350; takes one wicket."},
    "tier4": {"name": "World Class Bowler", "price": 1200, "fee": 500,
              "upgrade_cost": 720, "blurb": "Deadliest attack. Landing fee 500; takes one wicket."},
}

# ---------------------------------------------------------------------------
# Defensive assets
# ---------------------------------------------------------------------------
WICKET_KEEPERS: dict[str, dict] = {
    "tier1": {"name": "Club Wicketkeeper", "price": 200, "fee": 60, "run_penalty": 2,
              "upgrade_cost": 120, "blurb": "Landing fee 60 and 2 runs deducted. No wicket lost."},
    "tier2": {"name": "County Wicketkeeper", "price": 400, "fee": 120, "run_penalty": 4,
              "upgrade_cost": 240, "blurb": "Landing fee 120 and 4 runs deducted. No wicket lost."},
    "tier3": {"name": "International Wicketkeeper", "price": 650, "fee": 200, "run_penalty": 6,
              "upgrade_cost": 390, "blurb": "Landing fee 200 and 6 runs deducted. No wicket lost."},
}

FIELDERS: dict[str, dict] = {
    "tier1": {"name": "Club Fielder", "price": 100, "fee": 30,
              "upgrade_cost": 60, "blurb": "Cheap defensive property. Landing fee 30. No wicket lost."},
    "tier2": {"name": "County Fielder", "price": 200, "fee": 60,
              "upgrade_cost": 120, "blurb": "Landing fee 60. No wicket lost."},
    "tier3": {"name": "International Fielder", "price": 350, "fee": 100,
              "upgrade_cost": 210, "blurb": "Landing fee 100. No wicket lost."},
}

STADIUMS: dict[str, dict] = {
    "main": {
        "name": "Main Stadium", "price": 600, "fee": 90,
        "income_bonus": 0.15, "sponsorship": 60, "upgrade_cost": 350,
        "blurb": "+15% batsman income and 60 sponsorship each salary.",
    },
    "secondary": {
        "name": "County Stadium", "price": 450, "fee": 70,
        "income_bonus": 0.10, "sponsorship": 40, "upgrade_cost": 280,
        "blurb": "+10% batsman income and 40 sponsorship each salary.",
    },
}

# Cap for stacked stadium bonuses so income cannot scale without limit
MAX_STADIUM_BONUS = 0.40
MAX_LEVEL = 3                    # property upgrade levels (0 -> 3)
PROPERTY_LEVEL_INCOME_MULTIPLIER = 0.5
LEVEL_INCOME_MULTIPLIER = 0.35   # legacy stadium income scaling
SELL_REFUND_RATIO = 0.5

# ---------------------------------------------------------------------------
# Batsman roster / identity draft (Phase 7)
# ---------------------------------------------------------------------------
MAX_BATSMEN_PER_PLAYER = 5
BATSMAN_STARTING_WICKETS = 3
MAX_BATSMAN_LEVEL = 5
SIX_RUNS_PER_LEVEL = 6
BATSMAN_UPGRADE_COSTS = {1: 200, 2: 400, 3: 700, 4: 1100}
RECRUITMENT_COST = 250

# Player-to-player coin gifts. Bounded and rate-limited so wealth cannot be
# dumped in a single turn to distort the ranking or empty a rival instantly.
GIFT_MIN_COINS = 50
GIFT_MAX_COINS = 500
GIFT_RESERVE_COINS = 100
GIFTS_PER_ROUND = 1

# Famous cricketers are identities only — every entry has identical gameplay
# statistics. Adding a new cricketer here automatically extends the draft and
# recruitment pool.
FAMOUS_BATSMEN: dict[str, dict] = {
    "virat_kohli":      {"name": "Virat Kohli",      "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 18},
    "rohit_sharma":     {"name": "Rohit Sharma",     "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 45},
    "ms_dhoni":         {"name": "MS Dhoni",         "country": "India",        "avatar": "🧤", "jersey_color": "#1e40af", "jersey_number": 7},
    "rishabh_pant":     {"name": "Rishabh Pant",     "country": "India",        "avatar": "🧤", "jersey_color": "#1e40af", "jersey_number": 17},
    "shreyas_iyer":     {"name": "Shreyas Iyer",     "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 41},
    "kl_rahul":         {"name": "KL Rahul",         "country": "India",        "avatar": "🧤", "jersey_color": "#1e40af", "jersey_number": 1},
    "hardik_pandya":    {"name": "Hardik Pandya",    "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 33},
    "suryakumar_yadav": {"name": "Suryakumar Yadav", "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 63},
    "shubman_gill":     {"name": "Shubman Gill",     "country": "India",        "avatar": "🏏", "jersey_color": "#1e40af", "jersey_number": 2},
    "jasprit_bumrah":   {"name": "Jasprit Bumrah",   "country": "India",        "avatar": "🎯", "jersey_color": "#1e40af", "jersey_number": 93},
    "ab_de_villiers":   {"name": "AB de Villiers",   "country": "South Africa", "avatar": "🏏", "jersey_color": "#065f46", "jersey_number": 17},
    "steve_smith":      {"name": "Steve Smith",      "country": "Australia",    "avatar": "🏏", "jersey_color": "#facc15", "jersey_number": 49},
    "kane_williamson":  {"name": "Kane Williamson",  "country": "New Zealand",  "avatar": "🏏", "jersey_color": "#0f172a", "jersey_number": 22},
    "babar_azam":       {"name": "Babar Azam",       "country": "Pakistan",     "avatar": "🏏", "jersey_color": "#16a34a", "jersey_number": 45},
    "joe_root":         {"name": "Joe Root",         "country": "England",      "avatar": "🏏", "jersey_color": "#dc2626", "jersey_number": 66},
    "jos_buttler":      {"name": "Jos Buttler",      "country": "England",      "avatar": "🧤", "jersey_color": "#dc2626", "jersey_number": 63},
    "ben_stokes":       {"name": "Ben Stokes",       "country": "England",      "avatar": "🏏", "jersey_color": "#dc2626", "jersey_number": 55},
    "glenn_maxwell":    {"name": "Glenn Maxwell",    "country": "Australia",    "avatar": "🏏", "jersey_color": "#facc15", "jersey_number": 32},
    "david_warner":     {"name": "David Warner",     "country": "Australia",    "avatar": "🏏", "jersey_color": "#facc15", "jersey_number": 31},
    "travis_head":      {"name": "Travis Head",      "country": "Australia",    "avatar": "🏏", "jersey_color": "#facc15", "jersey_number": 62},
    "chris_gayle":      {"name": "Chris Gayle",      "country": "West Indies",  "avatar": "🏏", "jersey_color": "#7c3aed", "jersey_number": 333},
    "mitchell_starc":   {"name": "Mitchell Starc",   "country": "Australia",    "avatar": "🎯", "jersey_color": "#facc15", "jersey_number": 56},
}

CUSTOM_IDENTITY_DEFAULTS = {
    "name": "My Batsman", "country": "Custom", "avatar": "🏏",
    "jersey_color": "#22c55e", "jersey_number": 18,
    "skin": "#f1c27d", "hair": "short", "face": "smile",
    "hair_color": "#2d1b0e",
}
CUSTOM_SKIN_OPTIONS = ["#fde3c8", "#f1c27d", "#d8a06a", "#a9653c", "#6b3f24"]
CUSTOM_HAIR_OPTIONS = ["short", "spiky", "long", "curly", "bald"]
CUSTOM_FACE_OPTIONS = ["smile", "grin", "focused", "determined"]
CUSTOM_COUNTRIES = sorted({info["country"] for info in FAMOUS_BATSMEN.values()} | {"Custom"})

VICTORY_MODES = ("last_standing", "turn_limit")
DEFAULT_VICTORY_MODE = "last_standing"
DEFAULT_TURN_LIMIT = 20

# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
RUN_MILESTONES = {50: 50, 100: 100, 200: 200, 300: 300, 500: 500}
BOUNDARY_RUNS = 4
BOUNDARY_MONEY = 20
SIXER_RUNS = 6
SIXER_MONEY = 40
STREAK_BONUS_RUNS = 2            # consecutive boundary/sixer streak
STREAK_BONUS_AT = 3              # every 3rd consecutive scoring event

# ---------------------------------------------------------------------------
# Special space effects
# ---------------------------------------------------------------------------
INJURY_ROUNDS = 2                # batsman earns nothing while injured
FREE_HIT_BLOCKS = 1              # next wicket attack is nullified
POWERPLAY_ROUNDS = 2
POWERPLAY_MULTIPLIER = 1.5
NO_BALL_PENALTY = 60          # legacy event card only
NO_BALL_RUNS_PER_TURN = 6     # board No-ball bonus: turns since last no-ball × 6
NO_BALL_MAX_PROTECTION = 1    # protection never stacks beyond one wicket
OUT_SPACE_WICKETS = 1
RUN_OUT_PENALTY_RUNS = 3

# ---------------------------------------------------------------------------
# Event cards — resolved entirely by the server
# ---------------------------------------------------------------------------
EVENT_CARDS: list[dict] = [
    {"id": "sixer", "name": "SIXER!", "kind": "good",
     "text": "Clear the rope! Gain 6 runs and 40 coins.",
     "effect": {"runs": 6, "money": 40}},
    {"id": "boundary", "name": "FOUR!", "kind": "good",
     "text": "A crisp boundary. Gain 4 runs and 20 coins.",
     "effect": {"runs": 4, "money": 20}},
    {"id": "free_hit", "name": "FREE HIT", "kind": "good",
     "text": "The next bowler attack against you is nullified.",
     "effect": {"free_hit": 1}},
    {"id": "powerplay", "name": "POWERPLAY", "kind": "good",
     "text": "Your batsmen earn 50% more for 2 rounds.",
     "effect": {"powerplay": 2}},
    {"id": "crowd", "name": "CROWD SUPPORT", "kind": "good",
     "text": "The crowd loves you. Gain 80 coins.",
     "effect": {"money": 80}},
    {"id": "sponsor", "name": "SPONSORSHIP", "kind": "good",
     "text": "A new sponsor signs on. Gain 120 coins.",
     "effect": {"money": 120}},
    {"id": "injury", "name": "INJURY", "kind": "bad",
     "text": "A hamstring strain. One batsman stops earning for 2 rounds.",
     "effect": {"injury": 2}},
    {"id": "run_out", "name": "RUN OUT", "kind": "bad",
     "text": "A mix-up between the wickets. Lose 1 wicket and 3 runs.",
     "effect": {"wicket": 1, "runs": -3}},
    {"id": "no_ball", "name": "NO BALL", "kind": "bad",
     "text": "You are penalised 60 coins.",
     "effect": {"money": -60}},
    {"id": "wide", "name": "WIDE", "kind": "bad",
     "text": "An expensive extra. Lose 50 coins.",
     "effect": {"money": -50}},
    {"id": "catch_out", "name": "CATCH OUT", "kind": "bad",
     "text": "A sharp catch in the slips. Lose 1 wicket.",
     "effect": {"wicket": 1}},
    {"id": "poor_form", "name": "POOR FORM", "kind": "bad",
     "text": "Your batsmen earn 30% less for 2 rounds.",
     "effect": {"poor_form": 2}},
    {"id": "fielding_error", "name": "FIELDING ERROR", "kind": "bad",
     "text": "A costly drop. Lose 70 coins.",
     "effect": {"money": -70}},
    {"id": "rain", "name": "RAIN INTERRUPTION", "kind": "bad",
     "text": "Play is stopped. Lose 30 coins but take no wicket.",
     "effect": {"money": -30}},
]

CHALLENGES: list[dict] = [
    {"id": "chase", "name": "RUN CHASE", "text": "Score 22 runs off 12 balls.",
     "success": 0.55, "reward": {"money": 100, "runs": 8}, "fail": {"wicket": 1}},
    {"id": "yorker", "name": "YORKER DUEL", "text": "Face the yorker.",
     "success": 0.6, "reward": {"money": 80, "runs": 5}, "fail": {"wicket": 1}},
    {"id": "catch", "name": "SLIP CATCH", "text": "Hold the catch at first slip.",
     "success": 0.5, "reward": {"money": 120}, "fail": {"money": -60}},
]

# ---------------------------------------------------------------------------
# Achievements
# ---------------------------------------------------------------------------
ACHIEVEMENTS = {
    "first_purchase": "First signing — buy your first player.",
    "century": "Century — reach 100 runs in a match.",
    "five_wickets": "Five-fer — take 5 wickets with your bowlers.",
    "stadium_owner": "Groundskeeper — own a stadium.",
    "survivor": "Survivor — still standing after 5 rounds.",
}

# Space layout. Each entry: (name, type, category_key)
# type: start|property|stadium|event|run_1|run_2|run_4|run_6|free_hit|rest|
#       auction|injury|no_ball|challenge|recruit|out
# Board size stays at 32 so the existing 9x9 visual grid remains valid.
BOARD_LAYOUT: list[tuple[str, str, str | None]] = [
    ("Start Line", "start", None),
    ("1 RUN", "run_1", None),
    ("Club Bowler", "property", "bowler:tier1"),
    ("Cricket Card", "event", None),
    ("2 RUNS", "run_2", None),
    ("Club Fielder", "property", "fielder:tier1"),
    ("Batsman Recruitment", "recruit", None),
    ("4 RUNS", "run_4", None),
    ("Club Wicketkeeper", "property", "keeper:tier1"),
    ("Free Hit", "free_hit", None),
    ("6 RUNS", "run_6", None),
    ("County Bowler", "property", "bowler:tier2"),
    ("NO BALL", "no_ball", None),
    ("County Fielder", "property", "fielder:tier2"),
    ("Pavilion", "rest", None),
    ("2 RUNS", "run_2", None),
    ("County Wicketkeeper", "property", "keeper:tier2"),
    ("Cricket Card", "event", None),
    ("4 RUNS", "run_4", None),
    ("International Bowler", "property", "bowler:tier3"),
    ("Batsman Recruitment", "recruit", None),
    ("1 RUN", "run_1", None),
    ("International Fielder", "property", "fielder:tier3"),
    ("Challenge", "challenge", None),
    ("6 RUNS", "run_6", None),
    ("International Wicketkeeper", "property", "keeper:tier3"),
    ("Auction House", "auction", None),
    ("World Class Bowler", "property", "bowler:tier4"),
    ("1 RUN", "run_1", None),
    ("Injury", "injury", None),
    ("4 RUNS", "run_4", None),
    ("Out!", "out", None),
]
