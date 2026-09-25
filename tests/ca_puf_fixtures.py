"""A synthetic California PUF zip: made-up rows in the real files' column shape.

Only the columns read.py reads. No real PUF row is committed.
"""
import csv
import io
import zipfile

YEAR = 1999


def plan_row(plan_id, *, issuer="40513", name="Silver 70 HMO", metal="Silver", plan_type="HMO",
             variant="Standard Silver On Exchange Plan", area="CAS001", market="Individual", dental="No",
             qhp="On the Exchange", combined="", medical="$2,000 ", drug="$250", moop="$9,200 ", hsa="No",
             year=YEAR):
    return {
        "BUSINESS YEAR": str(year), "STATE CODE": "CA", "ISSUER ID": issuer, "MARKET COVERAGE": market,
        "DENTAL ONLY PLAN": dental, "QHP NONQHP TYPE ID": qhp, "STANDARD COMPONENT ID": plan_id[:14],
        "PLAN ID": plan_id, "PLAN MARKETING NAME": name, "PLAN TYPE": plan_type, "METAL LEVEL": metal,
        "IS HSA ELIGIBLE": hsa, "NATIONAL NETWORK": "No", "SERVICE AREA ID": area,
        "CSR VARIATION TYPE": variant, "TEHB DED INN TIER 1 INDIVIDUAL": combined,
        "MEHB DED INN TIER1 INDIVIDUAL": medical, "DEHB DED INN TIER1 INDIVIDUAL": drug,
        "TEHB INN TIER 1 INDIVIDUAL MOOP": moop,
    }


def rate_row(plan_id, area, age, rate):
    return {"PLAN ID": plan_id, "RATING AREA ID": f"Rating Area {area}", "AGE": age, "INDIVIDUAL RATE": rate,
            "TOBACCO": "No Preference"}


def area_row(county, *, issuer="40513", area="CAS001", partial="", statewide="false",
             market="Individual", dental="No"):
    return {"ISSUER ID": issuer, "SERVICE AREA ID": area, "COVER ENTIRE STATE": statewide,
            "COUNTY": county, "PARTIAL COUNTY": "true" if partial else ("" if statewide == "true" else "false"),
            "ZIP CODE": partial, "MARKET COVERAGE": market, "DENTAL PLAN ONLY": dental}


def _csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def write_puf(tmp_path, *, plans, rates, areas, label="01011999", names=None):
    """The zip, with CMS's member names unless `names` overrides some of them."""
    names = {"Plans": f"CAPlans{label}.csv", "Rates": f"CARates{label}.csv",
             "ServiceAreas": f"CAServiceAreas{label}.csv", **(names or {})}
    path = tmp_path / "ca.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for kind, rows in (("Plans", plans), ("Rates", rates), ("ServiceAreas", areas)):
            if names[kind]:
                archive.writestr(names[kind], _csv(rows))
    return path
