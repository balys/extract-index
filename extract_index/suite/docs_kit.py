"""Building blocks for the `docs` generator: fictional pools, value formatting and `Doc`.

Every name, company, city and product here is invented. Nothing reads a clock or external data;
callers pass a seeded `random.Random`, so the same seed gives the same documents.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from typing import Any, Sequence

# ---------------------------------------------------------------- pools (all fictional)

FIRST = (
    "Dana", "Priya", "Marcus", "Elena", "Tomas", "Aisha", "Kenji", "Lena", "Omar", "Sofia",
    "Rafael", "Ingrid", "Malik", "Hana", "Victor", "Nadia", "Jonas", "Leila", "Mateo", "Freya",
    "Desmond", "Yuki", "Callum", "Amara", "Bastian", "Celine", "Dmitri", "Esme", "Farid", "Greta",
    "Hugo", "Imani", "Jasper", "Keira", "Luca", "Mira", "Nikolai", "Odette", "Pavel", "Quinn",
    "Rosa", "Stellan", "Tamsin", "Umar", "Vera", "Wendell", "Ximena", "Yusuf", "Zara", "Anouk",
    "Bruno", "Clara", "Dario", "Elif", "Felix", "Gemma", "Idris", "Juno", "Kofi", "Linnea",
)
LAST = (
    "Ruiz", "Shah", "Okafor", "Lindqvist", "Brennan", "Haddad", "Moreau", "Tanaka", "Kowalski",
    "Adeyemi", "Castellano", "Fischer", "Nakamura", "Oyelaran", "Petrov", "Quintero", "Rasmussen",
    "Sorensen", "Thorne", "Underwood", "Varga", "Whitlock", "Yilmaz", "Zielinski", "Abernathy",
    "Bellamy", "Calder", "Delacroix", "Ekwueme", "Fairbanks", "Galbraith", "Holloway", "Iversen",
    "Jablonski", "Kaminski", "Laurent", "Marchetti", "Novak", "Ostrowski", "Pemberton", "Ramirez",
    "Szabo", "Toivonen", "Vasquez", "Wexley", "Achterberg", "Brandt", "Corrigan", "Duvall", "Eklund",
)
# Invented company stems; combined with a trade word and a legal suffix.
STEMS = (
    "Alvarin", "Brekka", "Corvane", "Dellmont", "Esterly", "Fennick", "Halvarth", "Iveldon",
    "Jorrin", "Lunmark", "Marrowind", "Norcastle", "Orvella", "Pellridge", "Quarrin", "Rossmere",
    "Silvane", "Tarrowby", "Ulmstead", "Vennick", "Wexmoor", "Yarrowdale", "Zellbrook", "Ambrell",
    "Brisora", "Caddoway", "Dunvarre", "Elsworne", "Farrowgate", "Gildmere", "Hestervale",
    "Kellbrook", "Larrowin", "Mossbray", "Nethercott", "Oakvenn", "Pinnacrest", "Ravelstoke",
    "Saltmere", "Thistlewick", "Umbervale", "Vantrell", "Wyncombe", "Zephram",
)
LEGAL = ("Ltd", "LLC", "Inc.", "Co.", "Ltd.", "Group")
STREETS = (
    "Alder", "Kestrel", "Juniper", "Harbor", "Mill", "Quarry", "Linden", "Copper", "Foundry",
    "Orchard", "Beacon", "Granite", "Willow", "Signal", "Tannery", "Ferry", "Chapel", "Meadow",
)
STREET_KINDS = ("Street", "Avenue", "Road", "Lane", "Way", "Row", "Drive", "Court")
# Fictional cities with made-up airport codes.
CITIES = (
    ("Port Halden", "PHD"), ("Eastmere", "EMR"), ("Corrin Bay", "CRB"), ("Lindmoor", "LDM"),
    ("Ashford Vale", "AFV"), ("Brightwater", "BWT"), ("Calder Springs", "CSP"), ("Dunrow", "DNW"),
    ("Elmhaven", "EHV"), ("Fairhollow", "FHL"), ("Greystone Harbor", "GSH"), ("Hollin", "HLN"),
    ("Juniper Point", "JNP"), ("Kelmont", "KMT"), ("Larkspur", "LKS"), ("Norhaven", "NHV"),
    ("Oakridge Crossing", "ORX"), ("Pinecrest", "PCR"), ("Ravensholt", "RVH"), ("Saltcombe", "SLC"),
    ("Tarnwick", "TRW"), ("Vellmouth", "VLM"), ("Westerby", "WBY"), ("Yarrow Falls", "YRF"),
)

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
MON = tuple(m[:3] for m in MONTHS)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WD = tuple(w[:3] for w in WEEKDAYS)

# ---------------------------------------------------------------- dates

YEAR_STYLES = ("dmy", "mdy_long", "iso", "dmy_long", "mdy", "wd_dmy")
NOYEAR_STYLES = ("md", "wd_md", "dm")


def fdate(d: dt.date, style: str) -> str:
    m, wd = d.month - 1, d.weekday()
    if style == "dmy":
        return f"{d.day} {MON[m]} {d.year}"
    if style == "dmy_long":
        return f"{d.day} {MONTHS[m]} {d.year}"
    if style == "mdy_long":
        return f"{MONTHS[m]} {d.day}, {d.year}"
    if style == "mdy":
        return f"{MON[m]} {d.day}, {d.year}"
    if style == "iso":
        return d.isoformat()
    if style == "wd_dmy":
        return f"{WD[wd]} {d.day} {MON[m]} {d.year}"
    if style == "wd_long":
        return f"{WEEKDAYS[wd]}, {MONTHS[m]} {d.day}, {d.year}"
    if style == "md":
        return f"{MON[m]} {d.day}"
    if style == "wd_md":
        return f"{WD[wd]}, {MON[m]} {d.day}"
    if style == "dm":
        return f"{d.day} {MON[m]}"
    if style == "wd_dm":
        return f"{WEEKDAYS[wd]} {d.day} {MON[m]}"
    raise ValueError(style)


def rand_date(r: random.Random, lo: dt.date = dt.date(2025, 1, 6),
              hi: dt.date = dt.date(2026, 12, 18)) -> dt.date:
    return lo + dt.timedelta(days=r.randint(0, (hi - lo).days))


def add_months(d: dt.date, n: int) -> dt.date:
    """Same day-of-month `n` months later (callers keep the day <= 28)."""
    if d.day > 28:
        raise ValueError("add_months needs a day <= 28")
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, d.day)


def yearless_ok(dates: Sequence[dt.date], ref: dt.date) -> bool:
    """Dates written without a year are unambiguous next to `ref`: same year, within ~4 months."""
    return all(d.year == ref.year and abs((d - ref).days) <= 120 for d in dates)


def iso(d: dt.date) -> str:
    return d.isoformat()


# ---------------------------------------------------------------- times (minutes since midnight)

TIME_STYLES = ("24", "12", "12l", "12dot")


def ftime(minutes: int, style: str) -> str:
    h, m = divmod(minutes % 1440, 60)
    if style == "24":
        return f"{h:02d}:{m:02d}"
    if style == "24h":
        return f"{h:02d}{m:02d}h"
    h12 = h % 12 or 12
    if style == "12":
        return f"{h12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    if style == "12l":
        return f"{h12}:{m:02d}{'am' if h < 12 else 'pm'}"
    if style == "12dot":
        return f"{h12}:{m:02d} {'a.m.' if h < 12 else 'p.m.'}"
    if style == "12short":  # "3pm" on the hour, else "3:30pm"
        tail = "am" if h < 12 else "pm"
        return f"{h12}{tail}" if m == 0 else f"{h12}:{m:02d}{tail}"
    raise ValueError(style)


def hhmm(minutes: int) -> str:
    h, m = divmod(minutes % 1440, 60)
    return f"{h:02d}:{m:02d}"


def iso_dt(d: dt.date, minutes: int) -> str:
    """`YYYY-MM-DDTHH:MM`; minutes past 1440 roll into the following days."""
    days, rest = divmod(minutes, 1440)
    return f"{(d + dt.timedelta(days=days)).isoformat()}T{hhmm(rest)}"


def rand_minutes(r: random.Random, lo: str, hi: str, step: int = 5) -> int:
    """A time of day between `lo` and `hi` ("HH:MM"), on a `step`-minute grid."""
    a = int(lo[:2]) * 60 + int(lo[3:])
    b = int(hi[:2]) * 60 + int(hi[3:])
    return a + step * r.randint(0, (b - a) // step)


def fdur_hm(minutes: int, style: str) -> str:
    h, m = divmod(minutes, 60)
    if style == "hm":
        return f"{h}h {m:02d}m"
    if style == "hr_min":
        return f"{h} hr {m} min" if m else f"{h} hr"
    if style == "min":
        return f"{minutes} min"
    if style == "colon":
        return f"{h}:{m:02d}"
    raise ValueError(style)


# ---------------------------------------------------------------- money (integer cents)

MONEY_STYLES = ("sym", "code_pre", "code_post", "sym_plain")
SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}


def fnum(cents: int, sep: bool = True) -> str:
    c = abs(cents)
    whole = f"{c // 100:,}" if sep else str(c // 100)
    return ("-" if cents < 0 else "") + f"{whole}.{c % 100:02d}"


def fmoney(cents: int, style: str, cur: str = "USD") -> str:
    neg, body = cents < 0, fnum(abs(cents), sep=style != "sym_plain")
    if style in ("sym", "sym_plain"):
        s = SYMBOL[cur] + body
    elif style == "code_pre":
        s = f"{cur} {body}"
    elif style == "code_post":
        s = f"{body} {cur}"
    else:
        raise ValueError(style)
    return "-" + s if neg else s


def amount(cents: int) -> float:
    """Gold form of a money amount."""
    return round(cents / 100, 2)


def pct_of(cents: int, basis_points: int) -> int:
    """`cents * bp / 10000`, rounded half up (bp: 825 = 8.25%)."""
    return (cents * basis_points + 5000) // 10000


def fpct(basis_points: int) -> str:
    s = f"{basis_points / 100:.2f}".rstrip("0").rstrip(".")
    return f"{s}%"


# ---------------------------------------------------------------- codes

def code(r: random.Random, pattern: str) -> str:
    """'#' -> digit, '@' -> letter (no I or O), '*' -> letter or digit; other chars literal."""
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    out = []
    for ch in pattern:
        if ch == "#":
            out.append(str(r.randint(0, 9)))
        elif ch == "@":
            out.append(r.choice(letters))
        elif ch == "*":
            out.append(r.choice(letters + "23456789"))
        else:
            out.append(ch)
    return "".join(out)


def slug(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def number_word(n: int) -> str:
    words = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
             "ten", "eleven", "twelve")
    return words[n] if 0 <= n < len(words) else str(n)


# ---------------------------------------------------------------- the document and its field candidates

@dataclass
class Cand:
    name: str
    spec: dict
    value: Any
    alternatives: list | None = None
    item_alternatives: list | None = None
    weight: float = 1.0

    def gold(self) -> dict:
        g: dict[str, Any] = {"value": self.value}
        if self.value is not None and self.alternatives:
            g["alternatives"] = self.alternatives
        if self.value is not None and self.item_alternatives:
            g["item_alternatives"] = self.item_alternatives
        return g


class Doc:
    """One generated document: its text, its candidate fields (gold computed from the
    structured values, never parsed from the text) and an optional reference date."""

    def __init__(self, r: random.Random, family: str, layout: str):
        self.r = r
        self.family = family
        self.layout = layout
        self.state = ""
        self.reference_date: dt.date | None = None
        self.cands: list[Cand] = []
        self._firsts: set[str] = set()
        self._lasts: set[str] = set()
        self._stems: set[str] = set()

    # -- pools without repeats inside one document
    def person(self) -> str:
        r = self.r
        first = r.choice([f for f in FIRST if f not in self._firsts])
        last = r.choice([x for x in LAST if x not in self._lasts])
        self._firsts.add(first)
        self._lasts.add(last)
        return f"{first} {last}"

    def stem(self) -> str:
        s = self.r.choice([x for x in STEMS if x not in self._stems])
        self._stems.add(s)
        return s

    def company(self, trades: Sequence[str], legal: bool = True) -> tuple[str, str]:
        """(full name, short name), e.g. ("Wexmoor Supply Ltd", "Wexmoor Supply")."""
        short = f"{self.stem()} {self.r.choice(trades)}"
        return (f"{short} {self.r.choice(LEGAL)}" if legal else short), short

    def street(self) -> str:
        r = self.r
        return f"{r.randint(2, 980)} {r.choice(STREETS)} {r.choice(STREET_KINDS)}"

    def city(self, avoid: Sequence[str] = ()) -> tuple[str, str]:
        return self.r.choice([c for c in CITIES if c[0] not in avoid])

    # -- field candidates. A value of None makes a null candidate (the document does not
    #    determine it); the spec is the same either way.
    def _add(self, name: str, spec: dict, value: Any, alternatives=None, item_alternatives=None,
             w: float = 1.0) -> None:
        if any(c.name == name for c in self.cands):
            raise ValueError(f"{self.family}: duplicate field {name}")
        spec = {k: v for k, v in spec.items() if v is not None}
        alts = None
        if alternatives:
            alts = [a for a in dict.fromkeys(alternatives) if a != value]
        self.cands.append(Cand(name, spec, value, alts or None, item_alternatives, w))

    def text(self, name, value, alts=None, instr=None, w=1.0):
        self._add(name, {"type": "text", "instructions": instr}, value, alts, w=w)

    def number(self, name, value, *, decimals=None, unit=None, integer=None, instr=None, w=1.0):
        self._add(name, {"type": "number", "instructions": instr, "unit": unit,
                         "integer": integer, "decimals": decimals}, value, w=w)

    def money(self, name, cents, cur="USD", instr=None, w=1.0):
        self.number(name, None if cents is None else amount(cents), decimals=2, unit=cur,
                    instr=instr, w=w)

    def date(self, name, d, instr=None, w=1.0):
        self._add(name, {"type": "date", "instructions": instr}, None if d is None else iso(d), w=w)

    def time(self, name, minutes, instr=None, w=1.0):
        self._add(name, {"type": "time", "instructions": instr},
                  None if minutes is None else hhmm(minutes), w=w)

    def datetime(self, name, d, minutes=None, instr=None, w=1.0):
        self._add(name, {"type": "datetime", "instructions": instr},
                  None if d is None else iso_dt(d, minutes), w=w)

    def duration(self, name, value, unit, *, integer=None, decimals=None, instr=None, w=1.0):
        self._add(name, {"type": "duration", "instructions": instr, "unit": unit,
                         "integer": integer, "decimals": decimals}, value, w=w)

    def items(self, name, values, item_type, *, decimals=None, unit=None, instr=None,
              item_alts=None, w=1.0):
        value = list(values) if values else None
        if item_type == "date" and value:
            value = [iso(d) for d in value]
        if item_type == "number" and value:
            value = [float(v) if not isinstance(v, int) else v for v in value]
        ia = None
        if value and item_alts and any(item_alts):
            ia = [list(x) for x in item_alts]
        self._add(name, {"type": "list", "items": item_type, "instructions": instr, "unit": unit,
                         "decimals": decimals}, value, item_alternatives=ia, w=w)

    def money_items(self, name, cents_list, cur="USD", instr=None, w=1.0):
        self.items(name, [amount(c) for c in cents_list] if cents_list else None, "number",
                   decimals=2, unit=cur, instr=instr, w=w)


# ---------------------------------------------------------------- boilerplate (no numbers, dates or names)

EMAIL_FOOTERS = (
    "CONFIDENTIALITY NOTICE: This message and any attachments are intended only for the named "
    "recipient and may contain information that is confidential or legally privileged. If you have "
    "received it by mistake, please tell the sender by replying, delete it from your system and do "
    "not copy, forward or disclose its contents. Email is not guaranteed to be secure or free of "
    "errors, and the sender accepts no liability for any damage caused by viruses or by changes "
    "made after it was sent.",
    "You are receiving this email because of a transaction on your account. This is a service "
    "message, so it is sent even if you have opted out of marketing emails. To change how we contact "
    "you, update your preferences in your account settings. Please do not reply directly to this "
    "address: replies to this mailbox are not monitored. For help, use the contact form on our "
    "website and a member of the team will get back to you.",
)
FOOTERS = (
    "Privacy: we process your personal data to provide the service you asked for, to meet our legal "
    "obligations and, where you agreed, to keep you informed about related offers. You can ask for a "
    "copy of the data we hold about you, ask us to correct or delete it, or object to marketing at "
    "any time from the privacy page of your account. We keep records only for as long as the law or "
    "our accounting rules require, and we never sell your data to third parties.",
    "Be alert to payment fraud. We will never ask you to change bank details by email or phone. If "
    "you receive a message that appears to come from us asking for a payment to a new account, do "
    "not reply and do not pay; call your usual contact on a number you already know and check first. "
    "Our staff will also never ask for your password or a one-time code.",
    "Please consider the environment before printing this message. Paper copies of statements and "
    "invoices are available on request, but switching to electronic documents in your online "
    "account is faster, keeps a searchable history and reduces the paper we send out each year.",
    "Terms: all goods and services are supplied under our standard terms and conditions, which are "
    "available on request and on our website. Title in any goods passes only when payment has been "
    "received in full. Any query about this document should be raised promptly so that it can be "
    "resolved before the payment is due. Nothing in this document limits your statutory rights.",
    "Accessibility: this document is available in large print, braille and audio formats. If you "
    "need it in another format or language, or need any other adjustment to use our services, let "
    "us know and we will arrange it at no extra cost.",
)


def add_footer(doc: "Doc", p: float = 0.33) -> None:
    """Sometimes append one or two neutral boilerplate paragraphs (a realistic long tail).
    Email notices go only on documents that are emails (they have a Subject line)."""
    r = doc.r
    if r.random() < p:
        pool = FOOTERS + (EMAIL_FOOTERS if "Subject:" in doc.state else ())
        k = 1 if r.random() < 0.6 else 2
        doc.state = doc.state.rstrip() + "\n\n" + "\n\n".join(r.sample(pool, k))
