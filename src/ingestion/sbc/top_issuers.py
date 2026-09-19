"""The parent companies Phase 3 reads SBCs for, with their HIOS issuer IDs (ADR 0015).

The ten largest by average monthly enrollment in the 30 HealthCare.gov states,
from CMS's 2025 Issuer Level Enrollment PUF, the newest published. Aetna
(sixth) is left out: it withdrew from the marketplace for 2026. The ranking
and how each issuer was assigned to its parent are in
docs/findings/sbc-documents.md.
"""
from itertools import chain

TOP_ISSUERS: dict[str, tuple[str, ...]] = {
    "Centene (Ambetter)": (
        "53932", "37903", "62141", "70525", "91450", "64004", "49004", "86382", "48286", "35065", "34368", "90787",
        "58594", "99723", "90714", "77264", "26289", "75841", "41047", "62505", "79222", "70111", "29418", "87226",
    ),
    "Oscar Health": (
        "13877", "40572", "45819", "43490", "77739", "69512", "69803", "57424", "29341", "45845", "91908", "23552",
        "20069",
    ),
    "UnitedHealth Group": (
        "69461", "40702", "68398", "56610", "72850", "94968", "69842", "71667", "95426", "97560", "54332", "73102",
        "33931", "45480", "33764", "69443", "40220", "80180", "49714",
    ),
    "Health Care Service Corporation (BCBS TX, OK, MT)": ("33602", "87571", "30751"),
    "Florida Blue": ("16842", "30252"),
    "Molina Healthcare": ("54172", "40047", "79975", "64353", "42326", "45786", "18167", "52697"),
    "Elevance Health (Anthem, Wellpoint)": ("44228", "17575", "32753", "96751", "29276", "47501", "79475"),
    "Blue Cross and Blue Shield of North Carolina": ("11512",),
    "BlueCross BlueShield of South Carolina": ("26065",),
    "Select Health": ("68781",),
}

TOP_ISSUER_IDS = frozenset(chain.from_iterable(TOP_ISSUERS.values()))
