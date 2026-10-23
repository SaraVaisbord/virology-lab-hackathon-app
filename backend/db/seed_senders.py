from __future__ import annotations

from sqlalchemy import select

from domain.vocabulary import SENDER_KINDS
from .models import Sender
from .session import SessionLocal

SEED_SENDERS = [
    ("כללית", "health_fund"),
    ("מכבי", "health_fund"),
    ("מאוחדת", "health_fund"),
    ("לאומית", "health_fund"),
    ("המרכז הרפואי ע\"ש חיים שיבא - תל השומר", "hospital"),
    ("המרכז הרפואי תל אביב ע\"ש סוראסקי (איכילוב)", "hospital"),
    ("רמב\"ם - הקריה הרפואית לבריאות האדם", "hospital"),
    ("מרכז רפואי ברזילי", "hospital"),
    ("המרכז הרפואי הלל יפה", "hospital"),
    ("המרכז הרפואי לגליל", "hospital"),
    ("המרכז הרפואי האוניברסיטאי ע\"ש אדית וולפסון", "hospital"),
    ("מרכז רפואי בני ציון", "hospital"),
    ("מרכז רפואי צפון - פוריה", "hospital"),
    ("המרכז הרפואי זיו", "hospital"),
    ("בית החולים שמואל הרופא", "hospital"),
    ("המרכז הרפואי שמיר", "hospital"),
    ("מרכז רפואי הדסה", "hospital"),
    ("המרכז הרפואי שערי צדק", "hospital"),
    ("מרכז רפואי רבין (בילינסון והשרון)", "hospital"),
    ("המרכז הרפואי האוניברסיטאי סורוקה", "hospital"),
    ("מרכז רפואי כרמל", "hospital"),
    ("מרכז רפואי מאיר", "hospital"),
    ("המרכז הרפואי קפלן", "hospital"),
    ("מרכז רפואי העמק", "hospital"),
    ("המרכז הרפואי יוספטל", "hospital"),
    ("מרכז שניידר לרפואת ילדים בישראל", "hospital"),
    ("המרכז הרפואי לשיקום לוינשטיין", "hospital"),
    ("המרכז הרפואי שיקומי גריאטרי הרצפלד", "hospital"),
    ("מרכז לבריאות הנפש גהה", "hospital"),
    ("מרכז לבריאות הנפש שלוותה", "hospital"),
    ("בית רבקה", "hospital"),
    ("אסותא ראשון לציון", "hospital"),
    ("אסותא אשדוד", "hospital"),
    ("אסותא חיפה", "hospital"),
    ("אסותא באר שבע", "hospital"),
    ("הרצליה מדיקל סנטר", "hospital"),
    ("לניאדו - מרכז רפואי צאנז", "hospital"),
    ("מרכז רפואי מעיני הישועה", "hospital"),
    ("מדיקה ת\"א", "hospital"),
    ("מדיקה רפאל", "hospital"),
    ("אלישע חיפה", "hospital"),
    ("RMC עפולה", "hospital"),
    ("המרכז הרפואי לבריאות הנפש אברבנאל", "hospital"),
    ("בית החולים איתנים", "hospital"),
    ("המרכז לבריאות הנפש באר שבע", "hospital"),
    ("המרכז הירושלמי לבריאות הנפש", "hospital"),
    ("בית החולים כפר שאול", "hospital"),
    ("מרכז רפואי לבריאות הנפש לב השרון", "hospital"),
    ("המרכז הרפואי לבריאות הנפש מעלה הכרמל", "hospital"),
    ("המרכז לבריאות הנפש שער מנשה", "hospital"),
    ("רוזנבלט מעבדה רפואית", "lab"),
    ("המרכז הלאומי לרפואה משפטית", "government"),
    ("צה\"ל - חיל הרפואה", "military"),
]


def seed_senders() -> tuple[int, int]:
    added = 0
    existing = 0

    with SessionLocal() as session:
        with session.begin():
            for name, kind in SEED_SENDERS:
                if kind not in SENDER_KINDS:
                    raise ValueError(f"Unexpected sender kind: {kind!r}")
                normalized_name = name.strip()
                existing_sender = session.execute(select(Sender).where(Sender.name == normalized_name)).scalar_one_or_none()
                if existing_sender is not None:
                    existing += 1
                    continue
                session.add(Sender(name=normalized_name, kind=kind))
                added += 1

    print(f"Added {added} senders; already existed {existing}.")
    return added, existing


if __name__ == "__main__":
    seed_senders()
