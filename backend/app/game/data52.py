"""Static game data for Crickopoly: 52-tile board, 96 fictional players,
8 stadiums, 8 event tiles, pitches and configurable rule tables.

All player names are FICTIONAL. No real cricketer likenesses, official league
branding or copyrighted logos are used.
"""

from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------
COUNTRIES: dict[str, dict] = {
    "india": {"name": "India", "flag": "🇮🇳", "color": "#ff9933"},
    "australia": {"name": "Australia", "flag": "🇦🇺", "color": "#ffcd00"},
    "england": {"name": "England", "flag": "🏴", "color": "#ce1124"},
    "south_africa": {"name": "South Africa", "flag": "🇿🇦", "color": "#007a4d"},
    "pakistan": {"name": "Pakistan", "flag": "🇵🇰", "color": "#006600"},
    "new_zealand": {"name": "New Zealand", "flag": "🇳🇿", "color": "#00247d"},
    "west_indies": {"name": "West Indies", "flag": "🌴", "color": "#7b1113"},
    "sri_lanka": {"name": "Sri Lanka", "flag": "🇱🇰", "color": "#ffb612"},
}

ROLES = ("batsman", "bowler", "wicketkeeper", "allrounder")
ROLE_LABELS = {
    "batsman": "Batsman",
    "bowler": "Bowler",
    "wicketkeeper": "Wicketkeeper",
    "allrounder": "All-rounder",
}
ROLE_SHORT = {"batsman": "BAT", "bowler": "BOWL", "wicketkeeper": "WK", "allrounder": "AR"}
TIERS = ("bronze", "silver", "gold")
# Reserve price paid during the inaugural draft (keeps 15 picks affordable
# within the 1,500 FC starting budget while leaving room for the season).
DRAFT_PRICE = {"bronze": 30, "silver": 50, "gold": 80}

PITCHES: dict[str, dict] = {
    "flat": {"name": "Flat Pitch", "icon": "🏏", "bat": 1.10, "pace": 0.94, "spin": 0.96,
             "desc": "True bounce and even carry. Rewards attacking batting."},
    "green": {"name": "Green Pitch", "icon": "🌿", "bat": 0.95, "pace": 1.14, "spin": 0.97,
              "desc": "Moisture and grass assist swing and seam."},
    "dry": {"name": "Dry Pitch", "icon": "🏜️", "bat": 1.00, "pace": 0.96, "spin": 1.16,
            "desc": "Crumbles and grips. Spinners extract turn and bounce."},
    "slow": {"name": "Slow Pitch", "icon": "🐌", "bat": 0.96, "pace": 1.00, "spin": 1.06,
             "desc": "Low, slow carry. Rewards timing and placement over power."},
}
PITCH_KEYS = tuple(PITCHES)

# ---------------------------------------------------------------------------
# Stadiums (8) — venue identities only, no official league branding/logos.
# ---------------------------------------------------------------------------
STADIUMS: dict[str, dict] = {
    "melbourne": {"id": "melbourne", "name": "Melbourne Cricket Ground", "short": "MCG",
                  "country": "australia", "price": 320, "landing_fee": 55, "match_revenue": 80,
                  "pitch": "green", "home_bat": 1.03, "home_pace": 1.05, "home_spin": 1.00,
                  "desc": "Big ground and fresh green surface. Fast bowlers thrive."},
    "eden_gardens": {"id": "eden_gardens", "name": "Eden Gardens", "short": "EDEN",
                     "country": "india", "price": 300, "landing_fee": 50, "match_revenue": 75,
                     "pitch": "dry", "home_bat": 1.02, "home_pace": 0.98, "home_spin": 1.07,
                     "desc": "Huge crowd, dry turning surface. Spinners are kings here."},
    "lords": {"id": "lords", "name": "Lord's", "short": "LORDS",
              "country": "england", "price": 340, "landing_fee": 60, "match_revenue": 90,
              "pitch": "green", "home_bat": 1.00, "home_pace": 1.07, "home_spin": 1.00,
              "desc": "The home of cricket. Seam-friendly slope and a premium pavilion."},
    "newlands": {"id": "newlands", "name": "Newlands", "short": "NEWLANDS",
                 "country": "south_africa", "price": 260, "landing_fee": 45, "match_revenue": 70,
                 "pitch": "green", "home_bat": 1.02, "home_pace": 1.06, "home_spin": 0.98,
                 "desc": "Mountain backdrop and a quick, bowler-friendly wicket."},
    "wankhede": {"id": "wankhede", "name": "Wankhede Stadium", "short": "WANKHEDE",
                 "country": "india", "price": 310, "landing_fee": 52, "match_revenue": 82,
                 "pitch": "flat", "home_bat": 1.07, "home_pace": 0.98, "home_spin": 0.99,
                 "desc": "Short boundaries and true bounce. A batsman's paradise."},
    "gaddafi": {"id": "gaddafi", "name": "Gaddafi Stadium", "short": "GADDAFI",
                "country": "pakistan", "price": 250, "landing_fee": 42, "match_revenue": 68,
                "pitch": "dry", "home_bat": 1.04, "home_pace": 0.97, "home_spin": 1.05,
                "desc": "Dry, slow pitch that grips as the match progresses."},
    "premadasa": {"id": "premadasa", "name": "R. Premadasa Stadium", "short": "PREMadasa",
                  "country": "sri_lanka", "price": 240, "landing_fee": 40, "match_revenue": 65,
                  "pitch": "slow", "home_bat": 0.99, "home_pace": 0.97, "home_spin": 1.08,
                  "desc": "Slow, low surface where spinners and placement dominate."},
    "eden_park": {"id": "eden_park", "name": "Eden Park", "short": "EDEN PARK",
                  "country": "new_zealand", "price": 270, "landing_fee": 46, "match_revenue": 72,
                  "pitch": "green", "home_bat": 1.01, "home_pace": 1.04, "home_spin": 1.00,
                  "desc": "Compact outfield and a green top. Boundary risk for bowlers."},
}

STADIUM_UPGRADES: dict[str, dict] = {
    "pitch_development": {"name": "Pitch Development", "cost": 160,
                          "desc": "Strengthens the home pitch modifier by 12%."},
    "training_facilities": {"name": "Training Facilities", "cost": 180,
                            "desc": "Reduces this franchise's training costs by 25%."},
    "pavilion": {"name": "Pavilion", "cost": 200,
                 "desc": "Increases match revenue earned at this stadium by 30%."},
    "sports_science": {"name": "Sports Science Centre", "cost": 220,
                       "desc": "Improves fatigue recovery for your squad by 1 extra point."},
    "elite_stadium": {"name": "Elite Stadium", "cost": 400,
                      "desc": "Unlocks full home advantage: +5% bat, +8% bowling."},
}

# ---------------------------------------------------------------------------
# Special event tiles (8)
# ---------------------------------------------------------------------------
EVENTS: dict[str, dict] = {
    "mega_auction": {"id": "mega_auction", "name": "Mega Auction", "icon": "🔨",
                     "desc": "Open a multi-player auction with several available stars."},
    "matchday_arena": {"id": "matchday_arena", "name": "Matchday Arena", "icon": "🏟️",
                       "desc": "Schedule and play an immediate T20 against a rival."},
    "injury_reserve": {"id": "injury_reserve", "name": "Injury Reserve", "icon": "🩹",
                       "desc": "Rehabilitate an injured player or rest a fatigued one."},
    "training_camp": {"id": "training_camp", "name": "Training Camp", "icon": "🏋️",
                      "desc": "Run a subsidised training camp for one squad member."},
    "sponsorship_deal": {"id": "sponsorship_deal", "name": "Sponsorship Deal", "icon": "🤝",
                         "desc": "Sign a sponsorship contract paying per league round."},
    "championship_qualifier": {"id": "championship_qualifier", "name": "Championship Qualifier", "icon": "🏆",
                               "desc": "Earn bonus league points and reputation."},
    "strategy_room": {"id": "strategy_room", "name": "Strategy Room", "icon": "🧠",
                      "desc": "Gain a tactical card usable in your next match."},
    "recovery_camp": {"id": "recovery_camp", "name": "Recovery Camp", "icon": "💚",
                      "desc": "Reduce fatigue across your whole squad."},
}

# ---------------------------------------------------------------------------
# 52-tile board. Corners at 0/13/26/39; 12 tiles per side.
# Each side: 8 country markets (2 countries x 4 roles), 2 stadiums, 2 events.
# ---------------------------------------------------------------------------
CORNERS = {
    0: {"kind": "corner", "id": "season_start", "name": "SEASON START", "icon": "🎬",
        "desc": "Collect 200 FC for passing or landing here. A new financial season begins."},
    13: {"kind": "corner", "id": "headquarters", "name": "FRANCHISE HEADQUARTERS", "icon": "🏢",
         "desc": "Manage your squad, contracts, transfers, training and finances."},
    26: {"kind": "corner", "id": "matchday", "name": "MATCHDAY ARENA", "icon": "🏟️",
         "desc": "Open the match lobby and take on a league opponent."},
    39: {"kind": "corner", "id": "injury_reserve", "name": "INJURY RESERVE", "icon": "🚑",
         "desc": "Rehabilitation hub. Rest, recover and replace injured players."},
}

# (country, stadium, events) per side, clockwise from SEASON START.
_SIDE_PLAN = [
    (("india", "australia"), ("melbourne", "lords"), ("mega_auction", "training_camp")),
    (("england", "south_africa"), ("eden_gardens", "newlands"), ("matchday_arena", "sponsorship_deal")),
    (("pakistan", "new_zealand"), ("wankhede", "gaddafi"), ("championship_qualifier", "strategy_room")),
    (("west_indies", "sri_lanka"), ("premadasa", "eden_park"), ("injury_reserve", "recovery_camp")),
]


def _market_price(country_idx: int, role: str) -> int:
    base = {"batsman": 150, "bowler": 150, "wicketkeeper": 130, "allrounder": 180}[role]
    return base + country_idx * 10


def build_board() -> list[dict]:
    """Return the 52-tile board in clockwise position order (index 0..51)."""
    tiles: list[dict | None] = [None] * 52
    for pos, corner in CORNERS.items():
        tiles[pos] = dict(corner, position=pos)
    for side, (countries, stadiums, events) in enumerate(_SIDE_PLAN):
        start = side * 13 + 1
        slots: list[dict] = []
        for ci, country in enumerate(countries):
            for role in ROLES:
                slots.append({
                    "kind": "market",
                    "id": f"{country}_{role}",
                    "name": f"{COUNTRIES[country]['name']} {ROLE_LABELS[role]} Market",
                    "icon": f"{COUNTRIES[country]['flag']}{ROLE_SHORT[role]}",
                    "country": country,
                    "role": role,
                    "price": _market_price(side * 2 + ci, role),
                    "desc": f"Own the {COUNTRIES[country]['name']} {ROLE_LABELS[role].lower()} market. "
                            f"Earn scouting revenue and recruit {COUNTRIES[country]['name']} {ROLE_LABELS[role].lower()}s.",
                })
        # Interleave markets with stadiums/events so the side reads naturally:
        # M M S M M E M M S M M E  (12 tiles)
        layout = [0, 1, "S0", 2, 3, "E0", 4, 5, "S1", 6, 7, "E1"]
        for offset, item in enumerate(layout):
            tile = slots[item] if isinstance(item, int) else None
            if item == "S0":
                tile = dict(STADIUMS[stadiums[0]], kind="stadium", position=start + offset,
                            name=STADIUMS[stadiums[0]]["name"], icon="🏟️")
            elif item == "S1":
                tile = dict(STADIUMS[stadiums[1]], kind="stadium", position=start + offset,
                            name=STADIUMS[stadiums[1]]["name"], icon="🏟️")
            elif item == "E0":
                tile = dict(EVENTS[events[0]], kind="event", position=start + offset)
            elif item == "E1":
                tile = dict(EVENTS[events[1]], kind="event", position=start + offset)
            else:
                tile = dict(tile, position=start + offset)
            tiles[start + offset] = tile
    for i, tile in enumerate(tiles):
        assert tile is not None and tile.get("position") == i, f"Bad tile at {i}: {tile}"
    return tiles


BOARD: list[dict] = build_board()

# ---------------------------------------------------------------------------
# 96 fictional players: 8 countries x 4 roles x 3 tiers.
# ---------------------------------------------------------------------------
_NAME_BANK: dict[str, dict[str, list[str]]] = {
    "india": {
        "batsman": ["Rohan Mehta", "Arjun Deshpande", "Kabir Sharma"],
        "bowler": ["Dev Patel", "Ishaan Malhotra", "Nikhil Rao"],
        "wicketkeeper": ["Aman Verma", "Rahul Bhatt", "Sameer Joshi"],
        "allrounder": ["Vikram Nair", "Sahil Kapoor", "Aditya Rao"],
    },
    "australia": {
        "batsman": ["Jack Maddison", "Lachlan Reid", "Cooper Hayes"],
        "bowler": ["Mitchell Vaughan", "Brodie Ferguson", "Angus McLeod"],
        "wicketkeeper": ["Oliver Barnes", "Hamish Clarke", "Toby Walsh"],
        "allrounder": ["Riley Donovan", "Cameron Bell", "Dylan Fraser"],
    },
    "england": {
        "batsman": ["Oliver Penn", "Harry Whitfield", "Edward Brooks"],
        "bowler": ["James Fairbanks", "Thomas Grayson", "William Hurst"],
        "wicketkeeper": ["Charles Wilde", "George Eaton", "Frederick Lane"],
        "allrounder": ["Henry Ashwood", "Arthur Kelsey", "Rupert Shaw"],
    },
    "south_africa": {
        "batsman": ["Thabo Nkosi", "Ruan Botha", "Sibusiso Dlamini"],
        "bowler": ["Kagiso Mokoena", "Duan van Wyk", "Lwazi Ndelu"],
        "wicketkeeper": ["Sipho Mahlangu", "Pieter Snyman", "Bongani Zulu"],
        "allrounder": ["Andile Jafta", "Ruben Kruger", "Mthokozisi Nene"],
    },
    "pakistan": {
        "batsman": ["Zaid Mahmood", "Bilal Ahmed", "Imran Sheikh"],
        "bowler": ["Usman Qadir", "Hassan Raza", "Naveed Iqbal"],
        "wicketkeeper": ["Amir Farooq", "Kamran Yousuf", "Saadullah Khan"],
        "allrounder": ["Fawad Ali", "Shahid Mahmood", "Arsam Butt"],
    },
    "new_zealand": {
        "batsman": ["Finn Wilson", "Hamish Noble", "Jonty Carter"],
        "bowler": ["Lockie Fraser", "Mason Rowe", "Tane Whitaker"],
        "wicketkeeper": ["Reuben Foster", "Kieran Parry", "Samuel Ewen"],
        "allrounder": ["Mitchell Cross", "Ethan Gillies", "Noah Sinclair"],
    },
    "west_indies": {
        "batsman": ["Marcus Haynes", "Dwayne Holder", "Kevon Best"],
        "bowler": ["Shamar Williams", "Oshane Thomas", "Ronaldo Kurton"],
        "wicketkeeper": ["Andre Foster", "Dervon Smith", "Kirk Charles"],
        "allrounder": ["Keiron Pollard", "Romario Holder", "Daren Brathwaite"],
    },
    "sri_lanka": {
        "batsman": ["Nuwan Perera", "Kavindu Silva", "Thisara Fernando"],
        "bowler": ["Dilan Ratnayake", "Ashen Wickramasinghe", "Chamika Karunaratne"],
        "wicketkeeper": ["Saman Jayawardene", "Kusal Mendis", "Avishka Fernando"],
        "allrounder": ["Angelo Mathews", "Dhananjaya Silva", "Ramesh Pathirana"],
    },
}

# Clean stray non-ASCII characters accidentally introduced above.
for _c, _roles in _NAME_BANK.items():
    for _r, _names in _roles.items():
        for _i, _n in enumerate(_names):
            _NAME_BANK[_c][_r][_i] = "".join(ch for ch in _n if ord(ch) < 128)

# Tier profiles: [overall range, cost]
_TIER_PROFILE = {
    "bronze": {"rating": (52, 64), "cost": 70},
    "silver": {"rating": (65, 77), "cost": 130},
    "gold": {"rating": (78, 91), "cost": 220},
}


def _deterministic(value: int, salt: int) -> int:
    x = (value * 1103515245 + salt * 12345 + 7919) & 0x7FFFFFFF
    return x % 100


def _abilities(role: str, base: int, seed: int) -> dict[str, int]:
    def a(offset: int, cap: int = 98) -> int:
        return min(cap, max(28, base + (_deterministic(seed, offset) % 13) - 6))
    if role == "batsman":
        return {"power": a(1), "timing": a(2), "vs_pace": a(3), "vs_spin": a(4),
                "consistency": a(5), "finishing": a(6), "strike_rotation": a(7)}
    if role == "bowler":
        return {"pace": a(1), "swing": a(2), "spin": a(3), "accuracy": a(4),
                "variations": a(5), "death_bowling": a(6), "wicket_taking": a(7)}
    if role == "wicketkeeper":
        return {"keeping": a(1), "reflexes": a(2), "fielding": a(3),
                "batting": a(4), "leadership": a(5)}
    return {"batting": a(1), "bowling": a(2), "fielding": a(3),
            "fitness": a(4), "versatility": a(5)}


def build_players() -> list[dict]:
    players: list[dict] = []
    for ci, (country, cdata) in enumerate(COUNTRIES.items()):
        for ri, role in enumerate(ROLES):
            for ti, tier in enumerate(TIERS):
                seed = ci * 1000 + ri * 100 + ti * 11 + 7
                profile = _TIER_PROFILE[tier]
                lo, hi = profile["rating"]
                overall = lo + (_deterministic(seed, 3) % (hi - lo + 1))
                batting = min(98, max(25, overall + (_deterministic(seed, 4) % 11) - 5))
                bowling = min(98, max(25, overall + (_deterministic(seed, 5) % 11) - 5))
                fielding = min(98, max(30, overall + (_deterministic(seed, 6) % 9) - 4))
                if role == "bowler":
                    batting = min(95, max(18, batting - 22))
                    bowling = min(99, bowling + 6)
                elif role == "batsman":
                    bowling = min(90, max(18, bowling - 24))
                    batting = min(99, batting + 6)
                elif role == "wicketkeeper":
                    bowling = min(80, max(15, bowling - 30))
                    fielding = min(99, fielding + 5)
                players.append({
                    "id": f"{country}_{role}_{tier}",
                    "name": _NAME_BANK[country][role][ti],
                    "country": country,
                    "flag": cdata["flag"],
                    "role": role,
                    "tier": tier,
                    "overall": overall,
                    "batting": batting,
                    "bowling": bowling,
                    "fielding": fielding,
                    "fitness": min(99, max(50, overall + (_deterministic(seed, 8) % 9) - 3)),
                    "consistency": min(98, max(35, overall + (_deterministic(seed, 9) % 13) - 6)),
                    "form": 50 + (_deterministic(seed, 10) % 41) - 20,
                    "confidence": 50 + (_deterministic(seed, 11) % 31) - 15,
                    "abilities": _abilities(role, overall, seed),
                    "value": profile["cost"] + (_deterministic(seed, 12) % 25),
                    "portrait_hue": (_deterministic(seed, 13) % 360),
                })
    assert len(players) == 96, len(players)
    return players


PLAYERS: list[dict] = build_players()
PLAYERS_BY_ID: dict[str, dict] = {p["id"]: p for p in PLAYERS}

SPONSORS: list[dict] = [
    {"id": "global_sports", "name": "Global Sports Co.", "icon": "🏅", "per_round": 18, "reputation": 2},
    {"id": "cricket_world", "name": "Cricket World Weekly", "icon": "📰", "per_round": 14, "reputation": 3},
    {"id": "stadium_partners", "name": "Stadium Partners", "icon": "🏟️", "per_round": 22, "reputation": 1},
    {"id": "energy_drink", "name": "Pulse Energy", "icon": "⚡", "per_round": 16, "reputation": 2},
]

TRAINING: dict[str, dict] = {
    "batting": {"name": "Batting Camp", "cost": 60, "attr": "batting", "gain": 3, "icon": "🏏"},
    "bowling": {"name": "Bowling Camp", "cost": 60, "attr": "bowling", "gain": 3, "icon": "🎯"},
    "fielding": {"name": "Fielding Camp", "cost": 45, "attr": "fielding", "gain": 3, "icon": "🧤"},
    "fitness": {"name": "Fitness Camp", "cost": 50, "attr": "fitness", "gain": 4, "icon": "🏋️"},
    "specialist": {"name": "Specialist Training", "cost": 75, "attr": "specialist", "gain": 4, "icon": "⭐"},
}

INJURIES: dict[str, dict] = {
    "minor": {"name": "Minor Strain", "matches": 1, "cost": 30, "icon": "🩹"},
    "moderate": {"name": "Moderate Injury", "matches": 2, "cost": 70, "icon": "🩼"},
    "major": {"name": "Major Injury", "matches": 3, "cost": 130, "icon": "🚑"},
}

# Tactical cards earned from the Strategy Room. Each card biases one phase of
# the submitted match plan; the match engine still resolves every ball.
TACTICAL_CARDS: dict[str, dict] = {
    "tactical_1": {"id": "tactical_1", "name": "Powerplay Surge", "icon": "⚡",
                   "desc": "Attack the first six overs and push the field up.",
                   "phase": "powerplay", "changes": {"bat": "aggressive", "field": "attacking"}},
    "tactical_2": {"id": "tactical_2", "name": "Death Bowling Blueprint", "icon": "🎯",
                   "desc": "Save yorkers for the final five overs.",
                   "phase": "death", "changes": {"bowl": "yorkers", "field": "defensive"}},
    "tactical_3": {"id": "tactical_3", "name": "Spin Web", "icon": "🕸️",
                   "desc": "Turn the middle overs to your spinner.",
                   "phase": "middle", "changes": {"bowl": "spin", "field": "defensive"}},
    "tactical_4": {"id": "tactical_4", "name": "Anchor Innings", "icon": "⚓",
                   "desc": "Protect wickets through the middle overs.",
                   "phase": "middle", "changes": {"bat": "defensive", "field": "balanced"}},
    "tactical_5": {"id": "tactical_5", "name": "Slip Cordon", "icon": "🧤",
                   "desc": "Attack the new ball with an catching field.",
                   "phase": "powerplay", "changes": {"bowl": "pace", "field": "attacking"}},
    "tactical_6": {"id": "tactical_6", "name": "Finisher's License", "icon": "🚀",
                   "desc": "Give your finisher free rein at the death.",
                   "phase": "death", "changes": {"bat": "aggressive", "field": "attacking"}},
}

RULES: dict = {
    "min_players": 2,
    "max_players": 6,
    "starting_credits": 1500,
    "squad_capacity": 15,
    "xi_size": 11,
    "overs": 20,
    "powerplay": 6,
    "middle_end": 15,
    "season_start_income": 200,
    "win_points": 3,
    "tie_points": 1,
    "loss_points": 0,
    "xi_roles": {
        "batsman": {"min": 3, "max": 5},
        "bowler": {"min": 3, "max": 5},
        "wicketkeeper": {"min": 1, "max": 2},
        "allrounder": {"min": 1, "max": 3},
    },
    "final_weights": {
        "championship": 40, "finance": 25, "squad": 20, "infrastructure": 10, "collections": 5,
    },
}


# Base snapshots are kept immutable so host overrides can be applied to one
# room at a time without corrupting the shipped fictional roster.
_BASE_PLAYERS = deepcopy(PLAYERS)
_BASE_RULES = deepcopy(RULES)
_BASE_PLAYERS_BY_ID = {p["id"]: p for p in _BASE_PLAYERS}

PLAYER_EDIT_FIELDS = {
    "name", "country", "role", "tier", "overall", "batting", "bowling",
    "fielding", "fitness", "consistency", "form", "confidence", "value",
    "portrait_hue", "abilities",
}
SAFE_RULE_FIELDS = {
    "starting_credits", "squad_capacity", "xi_size", "overs", "powerplay",
    "middle_end", "season_start_income", "win_points", "tie_points", "loss_points",
}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def sanitise_player_override(pid: str, changes: dict) -> dict:
    """Return only legal, bounded edits for one fictional player."""
    base = _BASE_PLAYERS_BY_ID.get(pid)
    if not base or not isinstance(changes, dict):
        return {}
    out: dict = {}
    for key in PLAYER_EDIT_FIELDS & changes.keys():
        value = changes[key]
        if key in ("name", "country", "role", "tier"):
            if isinstance(value, str) and 1 <= len(value) <= 40:
                out[key] = value
        elif key == "abilities":
            if isinstance(value, dict):
                merged = dict(base.get("abilities", {}))
                for a_key, a_val in value.items():
                    if a_key in merged:
                        try:
                            merged[a_key] = _clamp(a_val, 1, 99)
                        except (TypeError, ValueError):
                            continue
                out[key] = merged
        else:
            try:
                limits = {
                    "overall": (1, 100), "batting": (1, 99), "bowling": (1, 99),
                    "fielding": (1, 99), "fitness": (1, 99), "consistency": (1, 99),
                    "form": (1, 100), "confidence": (1, 100), "value": (1, 1000),
                    "portrait_hue": (0, 359),
                }[key]
                out[key] = _clamp(value, *limits)
            except (TypeError, ValueError, KeyError):
                continue
    return out


def merged_players(overrides: dict | None = None) -> list[dict]:
    """Deep copy of shipped players with a room's edits applied."""
    players = deepcopy(_BASE_PLAYERS)
    edits = (overrides or {}).get("players", {})
    if not isinstance(edits, dict):
        return players
    for player in players:
        change = sanitise_player_override(player["id"], edits.get(player["id"], {}))
        if change:
            player.update(deepcopy(change))
    return players


def apply_global_overrides(overrides: dict | None = None) -> None:
    """Apply one room's edits to the shared engine tables before an action.

    Engine modules import the PLAYERS list and PLAYERS_BY_ID/RULES dicts by
    reference, so mutating them in place keeps every engine consistent while
    still allowing per-room overrides on a single-process server.
    """
    fresh = merged_players(overrides)
    PLAYERS[:] = fresh
    PLAYERS_BY_ID.clear()
    PLAYERS_BY_ID.update({p["id"]: p for p in fresh})
    rules = deepcopy(_BASE_RULES)
    safe = (overrides or {}).get("rules", {})
    if isinstance(safe, dict):
        for key in SAFE_RULE_FIELDS & safe.keys():
            try:
                rules[key] = _clamp(safe[key], 1, 10000)
            except (TypeError, ValueError):
                continue
    RULES.clear()
    RULES.update(rules)


def gamedata(overrides: dict | None = None) -> dict:
    """Serializable payload for the frontend, optionally with room edits."""
    return {
        "countries": deepcopy(COUNTRIES),
        "roles": list(ROLES),
        "role_labels": deepcopy(ROLE_LABELS),
        "role_short": deepcopy(ROLE_SHORT),
        "tiers": list(TIERS),
        "pitches": deepcopy(PITCHES),
        "board": deepcopy(BOARD),
        "players": merged_players(overrides),
        "stadiums": deepcopy(STADIUMS),
        "stadium_upgrades": deepcopy(STADIUM_UPGRADES),
        "events": deepcopy(EVENTS),
        "sponsors": deepcopy(SPONSORS),
        "training": deepcopy(TRAINING),
        "injuries": deepcopy(INJURIES),
        "tactical_cards": deepcopy(TACTICAL_CARDS),
        "rules": deepcopy(RULES),
    }


def fresh_copies() -> dict:
    return gamedata()
