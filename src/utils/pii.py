"""Personal data out, hashes in - the same hashes the database stores.

One string does two jobs: it is the join key for a database whose PII columns are
hashed, and it is a safe pseudonym to put in front of a model.

The normalisation below is the integration contract. The database must hash the
SAME normalised string, because OCR does not reproduce Vietnamese diacritics
reliably: a statement naming "Trần Thị Mai Hương" comes back from OCR as
"Trần Thị Mai Hưỡng", and the raw strings hash differently while the folded
ones do not.
"""

import hashlib
import re
import unicodedata
from typing import Any

from src.rules._compare import norm_digits
from src.utils.common import normalize_text

NAME, IDENTIFIER, CONTACT = "name", "identifier", "contact"

TOKEN_PREFIX = "__PII_"
TOKEN_PATTERN = re.compile(r"__PII_[0-9a-f]{64}__")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


def normalise_for_hash(value: str, kind: str) -> str:
    """The exact string that gets hashed. Must match what the database hashes."""

    if kind == IDENTIFIER:
        return norm_digits(value)
    if kind == CONTACT:
        return re.sub(r"\s+", "", str(value)).lower()
    return normalize_text(value)


def pii_hash(value: str, kind: str = NAME) -> str:
    key = normalise_for_hash(value, kind)
    return hashlib.sha256(key.encode("utf-8")).hexdigest() if key else ""


def as_hash(value: Any, kind: str = NAME) -> str:
    """Hash a value, or pass it through if it already IS one.

    Idempotent on purpose: the same comparison then works whether the database
    column holds a hash or still holds plaintext, so switching the column over
    does not change a single rule.
    """

    text = str(value or "").strip()
    if DIGEST_PATTERN.fullmatch(text):
        return text
    return pii_hash(text, kind)


def show(value: Any) -> str:
    """A hash, shortened, so a report line stays readable."""

    text = str(value)
    return f"(đã hash) {text[:12]}…" if DIGEST_PATTERN.fullmatch(text) else text


def token_for(value: str, kind: str = NAME) -> str:
    digest = pii_hash(value, kind)
    return f"{TOKEN_PREFIX}{digest}__" if digest else ""


# --- detection -------------------------------------------------------------
# Every pattern is anchored to a cue word. Measured on a real dossier: an
# unanchored phone pattern matched 7 times in one ledger and was wrong every
# time - all inside amounts written 441.404.102.877 - and an unanchored 9-12
# digit pattern swallows the tax code and every figure on the balance sheet.

_UPPER = "A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
_LOWER = "a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
_WORD = f"[{_UPPER}][{_LOWER}{_UPPER}]{{1,14}}"
# A name can end on an initial - "Nguyễn Văn A" - but cannot START on one, or the
# row markers A, B, I, II on a balance sheet become names.
_NAME_WORD = f"(?:{_WORD}|[{_UPPER}](?![{_LOWER}{_UPPER}]))"

DEFAULT_PERSON_CUES = (
    "Ông", "Ong", "Ủng", "Ung", "Bà", "Ba", "Bả",
    "Giám đốc", "Giảm đốc", "Giảm đắc", "Tổng Giám đốc",
    "Kế toán trưởng", "Kế trán trưởng", "Kẻ toán trưởng",
    "Người lập", "Người lập biểu", "Chủ tịch", "Đại diện", "Người đại diện",
    "Kiểm toán viên",
)
# Vietnamese personal names open with a small closed set of surnames, and a
# surname followed by given names is a strong signal that does NOT collide with
# money the way a bare digit run does. Measured necessary: cue words alone caught
# only 6 of 16 name occurrences in a real statement - the rest sit in signature
# blocks and body text with no "Ông" or "Giám đốc" in front of them.
DEFAULT_SURNAMES = (
    "Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng",
    "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Đào", "Đoàn", "Vương", "Trịnh",
    "Đinh", "Lâm", "Mai", "Tạ", "Chu", "Kiều", "Cao", "Thái", "Lưu", "Hà",
)

# Words that follow a name in a signature table but are never part of one. A
# scanned table separates the name from the role beside it with spaces only, so
# "Nguyễn Thị Thu    Chủ tịch" reads as one run: the name is what comes BEFORE the
# first of these. Trimming keeps the name masked - rejecting the whole run left it
# in the clear, which is how "Nguyễn Thị Thu" leaked on a real statement.
NON_NAME_WORDS = frozenset({
    "chu", "tich", "giam", "doc", "pho", "tong", "ke", "truong", "hoi", "dong",
    "quan", "cong", "ty", "tnhh", "ban", "kiem", "vien", "nguoi", "lap", "bieu",
    "dai", "dien", "co",
})

MAX_NAME_WORDS = 4

DEFAULT_IDENTIFIER_CUES = ("CCCD", "CMND", "Căn cước công dân", "Căn cước",
                           "Chứng minh nhân dân", "Số CCCD", "Số CMND")
DEFAULT_CONTACT_CUES = ("Điện thoại", "Đien thoai", "ĐT", "SĐT", "Tel", "Mobile", "Email")


def _fold(text: str) -> tuple[str, list[int]]:
    """Diacritic-free copy, plus the original index of every character in it."""

    folded: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        stripped = "".join(
            c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c)
        )
        for c in stripped.lower().replace("đ", "d"):
            folded.append(c)
            index.append(position)
    return "".join(folded), index


def _cue_group(cues: tuple[str, ...]) -> str:
    """Cue alternation, WORD-BOUNDED.

    Without the boundary the two-letter cues match inside ordinary words: "ba"
    inside "bang" and "ong" inside "phuong", which on a real statement masked
    "NGUỒN VỐN", "TỔNG CỘNG TÀI SẢN" and every ward name on the letterhead.
    """

    folded = sorted({_fold(cue)[0] for cue in cues}, key=len, reverse=True)
    return r"\b(?:" + "|".join(re.escape(cue) for cue in folded) + r")\b"


class PiiVault:
    """Finds personal data in document text, hashes it, and remembers the way back.

    The plaintext it learns comes from the documents only: the database returns
    hashes, so there is nothing to learn from that side.
    """

    def __init__(
        self,
        person_cues: tuple[str, ...] = DEFAULT_PERSON_CUES,
        surnames: tuple[str, ...] = DEFAULT_SURNAMES,
        identifier_cues: tuple[str, ...] = DEFAULT_IDENTIFIER_CUES,
        contact_cues: tuple[str, ...] = DEFAULT_CONTACT_CUES,
    ):
        self.plaintext_by_token: dict[str, str] = {}
        # Cues are matched on the diacritic-free copy, so one entry catches every
        # way OCR spells it. What FOLLOWS a cue is then matched on the original
        # text, because capitalisation is the signal that a word is a name and
        # the folded copy has thrown it away.
        self._person_cue = re.compile(rf"{_cue_group(person_cues)}[\s.:]+")
        self._identifier_cue = re.compile(
            rf"{_cue_group(identifier_cues)}[\s.:]*(?:so|no)?[\s.:]*"
        )
        self._contact_cue = re.compile(rf"{_cue_group(contact_cues)}[\s.:]*")
        folded_surnames = sorted({_fold(n)[0] for n in surnames}, key=len, reverse=True)
        # Anchored folded, but the words AFTER it are checked on the original text
        # for capitals. Folding alone cannot tell the surname "Chu" from the word
        # "Chủ", so without that check every "Chủ tịch" and "Hà Nội" was masked -
        # 113 values on one statement instead of 7.
        self._surname_cue = re.compile(
            r"\b(?:" + "|".join(re.escape(n) for n in folded_surnames) + r")\b"
        )
        # A scanned table separates words by several spaces, so the run is matched
        # wide and cut back in _name_span.
        self._person_value = re.compile(rf"({_WORD}(?:[ ]{{1,4}}{_NAME_WORD}){{1,5}})")
        # One signature row's cue can point at the NEXT row, which opens with a cue
        # of its own: "Phó Chủ tịch\nBà Hoàng Thị Lan" made "Bà" the first word of
        # the name, and the same name elsewhere then no longer matched.
        # Minus the surnames: "Chu" opens both "Chủ tịch" and the name "Chu Quang
        # Huy", and dropping it left the surname standing.
        self._cue_words = {
            word for cue in person_cues for word in _fold(cue)[0].split()
        } - set(folded_surnames)
        self._identifier_value = re.compile(r"([0-9][0-9 .\-]{7,16}[0-9])")
        self._contact_value = re.compile(
            r"([0-9][0-9 .\-]{8,14}[0-9]|[\w.\-]+@[\w.\-]+\.\w+)"
        )

    def _name_span(self, text: str, start: int) -> tuple[int, int] | None:
        """The person name starting at `start`, trimmed of any role words after it."""

        match = self._person_value.match(text, start)
        if match is None:
            return None
        offset = match.start(1)
        words = [(m.group(0), offset + m.start(), offset + m.end())
                 for m in re.finditer(rf"{_NAME_WORD}", match.group(1))]
        # A WIDER GAP is a table-cell boundary, not a space inside a name. A scanned
        # signature block reads "Trần Mai Hương  Lê Vũ Thành" as one run, and
        # masking it whole produces a hash that matches nothing in the database.
        while words and _fold(words[0][0])[0] in self._cue_words:
            words = words[1:]
        gap = words[1][1] - words[0][2] if len(words) > 1 else 1
        kept: list[tuple[str, int, int]] = []
        for position, word in enumerate(words):
            if position and word[1] - words[position - 1][2] > gap:
                break
            # Never at position 0: "Chu" is both a surname and the start of
            # "Chủ tịch", and stopping there dropped a real name.
            if position and _fold(word[0])[0] in NON_NAME_WORDS:
                break
            kept.append(word)
        # TRUNCATE, never reject: a run longer than a name is a name with a role
        # beside it, and rejecting it leaves the name in the clear.
        kept = kept[:MAX_NAME_WORDS]
        if len(kept) < 2:
            return None
        # A heading is not a name: no SHOUTED word, and not every word in capitals.
        if any(w.isupper() and len(w) > 2 for w, _, _ in kept):
            return None
        if all(w.isupper() for w, _, _ in kept):
            return None
        return kept[0][1], kept[-1][2]

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        folded, index = _fold(text)
        found: list[tuple[int, int, str]] = []
        for cue, value, kind in (
            (self._person_cue, self._person_value, NAME),
            (self._identifier_cue, self._identifier_value, IDENTIFIER),
            (self._contact_cue, self._contact_value, CONTACT),
        ):
            for hit in cue.finditer(folded):
                if hit.end() >= len(index):
                    continue
                start = index[hit.end()]
                if kind == NAME:
                    span = self._name_span(text, start)
                    if span:
                        found.append((span[0], span[1], kind))
                    continue
                match = value.match(text, start)
                if match:
                    found.append((match.start(1), match.end(1), kind))

        # Surname-anchored: catches the occurrences no cue precedes.
        for hit in self._surname_cue.finditer(folded):
            span = self._name_span(text, index[hit.start()])
            if span:
                found.append((span[0], span[1], NAME))

        # Everything already learned, swept across the whole text: one cue hit
        # teaches a name, and the name is then masked everywhere it appears,
        # diacritics folded so OCR variants go too.
        for plaintext in self.plaintext_by_token.values():
            if not self._looks_like_name(plaintext):
                continue
            needle = _fold(plaintext)[0]
            position = folded.find(needle)
            while position != -1:
                start = index[position]
                # The occurrence must be capitalised HERE too. Without this the
                # sweep matched ordinary prose and masked the document's own title.
                match = self._person_value.match(text, start)
                if match and match.start(1) == start:
                    found.append((start, index[position + len(needle) - 1] + 1, NAME))
                position = folded.find(needle, position + len(needle))
        return found

    def _looks_like_name(self, value: str) -> bool:
        """Two to four capitalised words, none of them SHOUTED - a heading is not a name."""

        words = value.split()
        if not 2 <= len(words) <= MAX_NAME_WORDS:
            return False
        if any(word.isupper() and len(word) > 2 for word in words):
            return False
        if all(word.isupper() for word in words):
            return False
        return all(re.fullmatch(_WORD, word) for word in words)

    def mask(self, text: str) -> str:
        """Replace every detected personal value with its hash token."""

        if not text:
            return text
        # Twice: the first pass learns names from cues and surnames, the second
        # sweeps those learned values across text the first pass did not anchor on.
        for _ in range(2):
            # LONGEST span wins. "Vũ" is itself a surname, so "Lê Vũ Thành" is
            # found both whole and as "Vũ Trụ"; taking the shorter one first leaves
            # the surname in the clear. Chosen longest-first, applied back-to-front
            # so the earlier offsets stay valid.
            chosen: list[tuple[int, int, str]] = []
            for span in sorted(set(self._spans(text)), key=lambda s: (s[0] - s[1], s[0])):
                start, end, _ = span
                if not any(start < b and a < end for a, b, _ in chosen):
                    chosen.append(span)
            for start, end, kind in sorted(chosen, key=lambda s: -s[0]):
                plaintext = text[start:end].strip()
                token = token_for(plaintext, kind)
                if not token:
                    continue
                self.plaintext_by_token[token] = plaintext
                text = text[:start] + token + text[end:]
        return text

    def unmask(self, payload: Any) -> Any:
        """Put the plaintext back, wherever this vault has seen it."""

        if isinstance(payload, str):
            return TOKEN_PATTERN.sub(
                lambda m: self.plaintext_by_token.get(m.group(0), m.group(0)), payload
            )
        if isinstance(payload, dict):
            return {key: self.unmask(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self.unmask(item) for item in payload]
        return payload


def vault_from_settings(settings: dict) -> PiiVault:
    """A vault using the cue lists declared in config/programs.yaml."""

    def cues(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        declared = settings.get(key)
        return tuple(declared) if declared else default

    return PiiVault(
        person_cues=cues("pii_person_cues", DEFAULT_PERSON_CUES),
        surnames=cues("pii_surnames", DEFAULT_SURNAMES),
        identifier_cues=cues("pii_identifier_cues", DEFAULT_IDENTIFIER_CUES),
        contact_cues=cues("pii_contact_cues", DEFAULT_CONTACT_CUES),
    )
