"""PII guard: mask personal data before any model sees it; restore it only in the final rendered output.

What is masked
  - people's names (client contacts and staff), full and first names -> [PERSON_n]
  - email addresses -> [EMAIL_n]
  - phone numbers -> [PHONE_n]

The same person always gets the same token within one briefing, so the model can still reason
("[PERSON_1] asked for pricing; [PERSON_1] chased it on 3 Nov"). Tokens are swapped back to real
values only when the finished briefing is shown to an authorised user.
"""
import re
import sqlite3

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)\d{3,4}[\s-]?\d{3,4}(?!\w)")
TOKEN = re.compile(r"\[(PERSON|EMAIL|PHONE)_\d+\]")


class PiiMasker:
    def __init__(self, people: list[str]):
        """`people`: full names to protect. First names are masked too, mapped to the same person."""
        self.to_token: dict[str, str] = {}
        self.to_value: dict[str, str] = {}
        self._person_of: dict[str, str] = {}      # any name form (lower-case) -> canonical full name
        for full in sorted({p.strip() for p in people if p and p.strip()}, key=len, reverse=True):
            canon = full.title() if full.isupper() else full
            self._person_of.setdefault(canon.lower(), canon)
            first = canon.split()[0]
            if len(canon.split()) > 1 and len(first) > 2:
                self._person_of.setdefault(first.lower(), canon)
            # 'J. Park' style references
            if len(canon.split()) > 1:
                self._person_of.setdefault(f"{first[0]}. {canon.split()[-1]}".lower(), canon)
        names = sorted(self._person_of, key=len, reverse=True)
        # Not inside identifiers: 'Ana' must match the person, never the 'ANA' in the user id 'U-ANA'.
        self._name_rx = (re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.IGNORECASE)
                         if names else None)
        self._counts = {"PERSON": 0, "EMAIL": 0, "PHONE": 0}

    @classmethod
    def from_db(cls, conn: sqlite3.Connection) -> "PiiMasker":
        people = [r[0] for r in conn.execute("SELECT name FROM contacts UNION SELECT name FROM users")]
        return cls(people)

    def _token(self, kind: str, value: str) -> str:
        if value not in self.to_token:
            self._counts[kind] += 1
            tok = f"[{kind}_{self._counts[kind]}]"
            self.to_token[value] = tok
            self.to_value[tok] = value
        return self.to_token[value]

    def mask(self, text: str) -> str:
        if not text:
            return text
        text = EMAIL.sub(lambda m: self._token("EMAIL", m.group(0).lower()), text)
        text = PHONE.sub(lambda m: self._token("PHONE", m.group(0)) if sum(c.isdigit() for c in m.group(0)) >= 9 else m.group(0), text)
        if self._name_rx:
            text = self._name_rx.sub(lambda m: self._token("PERSON", self._person_of[m.group(0).lower()]), text)
        return text

    def unmask(self, text: str) -> str:
        return TOKEN.sub(lambda m: self.to_value.get(m.group(0), m.group(0)), text or "")

    def leaks(self, text: str) -> list[str]:
        """Real names/emails still present in text that should have been masked (used by the eval)."""
        found = []
        if self._name_rx:
            found += [m.group(0) for m in self._name_rx.finditer(text or "")]
        found += EMAIL.findall(text or "")
        return found
