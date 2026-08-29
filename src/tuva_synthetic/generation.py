"""Deterministic generation of a coherent commercial claims population."""

from __future__ import annotations

import calendar
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import count
from typing import Iterable

from tuva_synthetic.model import CanonicalDataset, Row


@dataclass(frozen=True)
class GenerationConfig:
    payer: str
    member_count: int = 10_000
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2025, 12, 31)
    seed: int = 20260829


@dataclass(frozen=True)
class PayerProfile:
    key: str
    label: str
    member_prefix: str
    states: tuple[tuple[str, float], ...]
    products: tuple[tuple[str, float], ...]
    source_systems: tuple[tuple[str, float], ...]
    network_rate: float


PAYER_PROFILES = {
    "aetna": PayerProfile(
        key="aetna",
        label="Aetna",
        member_prefix="AE",
        states=(("TX", .14), ("FL", .12), ("CA", .11), ("NY", .10), ("PA", .08),
                ("NJ", .07), ("IL", .07), ("GA", .06), ("OH", .06), ("VA", .05),
                ("AZ", .05), ("CO", .04), ("MA", .03), ("NC", .02)),
        products=(("PPO", .45), ("HMO", .21), ("POS", .14), ("HDHP", .17), ("EPO", .03)),
        source_systems=(("AETNA_CORE", .86), ("AETNA_LEGACY", .14)),
        network_rate=.925,
    ),
    "priority_health": PayerProfile(
        key="priority_health",
        label="Priority Health",
        member_prefix="PH",
        states=(("MI", .88), ("OH", .04), ("IN", .03), ("WI", .025), ("IL", .025)),
        products=(("HMO", .42), ("PPO", .29), ("POS", .08), ("HDHP", .18), ("EPO", .03)),
        source_systems=(("FACETS", .82), ("LEGACY_MIGRATION", .18)),
        network_rate=.946,
    ),
    "hcci": PayerProfile(
        key="hcci",
        label="HCCI Commercial",
        member_prefix="HC",
        states=(("CA", .12), ("TX", .10), ("FL", .08), ("NY", .07), ("PA", .06),
                ("IL", .06), ("OH", .05), ("GA", .05), ("NC", .05), ("MI", .05),
                ("NJ", .04), ("VA", .04), ("WA", .04), ("AZ", .04), ("MA", .04),
                ("CO", .04), ("TN", .03), ("MN", .02), ("OR", .02), ("UT", .02)),
        products=(("PPO", .51), ("HMO", .18), ("POS", .11), ("HDHP", .17), ("EPO", .03)),
        source_systems=(("CONTRIBUTOR_A", .40), ("CONTRIBUTOR_B", .34), ("CONTRIBUTOR_C", .26)),
        network_rate=.918,
    ),
}


FIRST_NAMES_F = (
    "Olivia", "Emma", "Amelia", "Sophia", "Mia", "Charlotte", "Isabella",
    "Ava", "Evelyn", "Luna", "Harper", "Camila", "Sofia", "Gianna",
    "Eleanor", "Maria", "Aaliyah", "Priya", "Mei", "Fatima",
)
FIRST_NAMES_M = (
    "Liam", "Noah", "Oliver", "James", "Elijah", "Mateo", "Theodore",
    "Henry", "Lucas", "William", "Benjamin", "Levi", "Sebastian", "Daniel",
    "Jack", "Jose", "Omar", "Arjun", "Wei", "Malik",
)
LAST_NAMES = (
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Patel", "Kim", "Singh", "Chen", "Ali",
)


ZIP_BY_STATE = {
    "AZ": ("85001", "85201"), "CA": ("90001", "92101", "94102"),
    "CO": ("80202", "80903"), "FL": ("33101", "32801", "33602"),
    "GA": ("30303", "31401"), "IL": ("60601", "62701"),
    "IN": ("46204", "46802"), "MA": ("02108", "01608"),
    "MI": ("49503", "48201", "48912", "48104", "49423"),
    "MN": ("55401", "55101"), "NC": ("27601", "28202"),
    "NJ": ("07102", "08608"), "NY": ("10001", "14202"),
    "OH": ("43215", "44113", "45202"), "OR": ("97205", "97401"),
    "PA": ("19103", "15222"), "TN": ("37203", "38103"),
    "TX": ("75201", "77002", "78701", "78205"), "UT": ("84101",),
    "VA": ("23219", "22201"), "WA": ("98101", "99201"),
    "WI": ("53202", "53703"),
}


@dataclass(frozen=True)
class Condition:
    code: str
    label: str
    base: float
    age_slope: float
    female_multiplier: float = 1.0


CONDITIONS = {
    "hypertension": Condition("I10", "Essential hypertension", .006, .255),
    "type_2_diabetes": Condition("E119", "Type 2 diabetes", .002, .102),
    "hyperlipidemia": Condition("E785", "Hyperlipidemia", .004, .185),
    "asthma": Condition("J45909", "Asthma", .065, .025, 1.10),
    "copd": Condition("J449", "COPD", .001, .050),
    "ckd": Condition("N1830", "Chronic kidney disease", .001, .038),
    "cad": Condition("I2510", "Coronary artery disease", .001, .042),
    "heart_failure": Condition("I509", "Heart failure", .0005, .022),
    "depression": Condition("F329", "Major depression", .055, .050, 1.25),
    "anxiety": Condition("F419", "Anxiety disorder", .070, .030, 1.35),
    "obesity": Condition("E669", "Obesity", .075, .180, 1.15),
    "osteoarthritis": Condition("M1990", "Osteoarthritis", .004, .105, 1.15),
    "migraine": Condition("G43909", "Migraine", .025, .015, 2.20),
    "sleep_apnea": Condition("G4733", "Obstructive sleep apnea", .010, .050),
}


MEDICATIONS = {
    # NDC11/concept pairs were verified as active with the public NLM RxNorm
    # API on 2026-08-29. Labels stay within the shortest payer field (Aetna's
    # 25-character label name).
    "hypertension": ("00093111310", "Lisinopril 10mg tablet", "ACE inhibitor", 9.0, .84),
    "type_2_diabetes": ("00093104801", "Metformin 500mg tablet", "Biguanide", 11.0, .80),
    "hyperlipidemia": ("00093505910", "Atorvastatin 20mg tab", "Statin", 10.0, .82),
    "asthma": ("00093317431", "Albuterol 90mcg inhaler", "Bronchodilator", 48.0, .58),
    "copd": ("68180096411", "Tiotropium 18mcg cap", "Anticholinergic", 410.0, .76),
    "heart_failure": ("00054429925", "Furosemide 40mg tablet", "Loop diuretic", 8.0, .83),
    "depression": ("00378418701", "Sertraline 50mg tablet", "SSRI", 13.0, .67),
    "anxiety": ("00143980801", "Escitalopram 10mg tab", "SSRI", 16.0, .63),
    "osteoarthritis": ("00378045101", "Naproxen 500mg tablet", "NSAID", 12.0, .44),
    "migraine": ("00378563159", "Sumatriptan 50mg tablet", "Triptan", 36.0, .48),
    "sleep_apnea": ("00000000000", "No drug therapy", "None", 0.0, 0.0),
}


ACUTE_DIAGNOSES = (
    ("J069", "99213", "Acute upper respiratory infection"),
    ("N390", "99214", "Urinary tract infection"),
    ("M5450", "99213", "Low back pain"),
    ("R079", "99215", "Chest pain"),
    ("H6690", "99213", "Otitis media"),
    ("K529", "99213", "Gastroenteritis"),
)


INPATIENT_TEMPLATES = (
    ("J189", "194", "99223", "Pneumonia", 17_500.0),
    ("I509", "291", "99223", "Heart failure", 28_000.0),
    ("A419", "871", "99223", "Sepsis", 42_000.0),
    ("K3580", "343", "44970", "Appendicitis", 24_000.0),
    ("M1711", "470", "27447", "Knee replacement", 38_000.0),
    ("O80", "775", "59400", "Delivery", 16_000.0),
)


SPECIALTIES = (
    ("Family Medicine", "01"), ("Internal Medicine", "11"),
    ("Pediatrics", "37"), ("Cardiology", "06"),
    ("Endocrinology", "46"), ("Orthopedic Surgery", "20"),
    ("Emergency Medicine", "93"), ("Radiology", "30"),
    ("Obstetrics/Gynecology", "16"), ("Psychiatry", "26"),
)


def _weighted_choice(rng: random.Random, values: Iterable[tuple[str, float]]) -> str:
    items = tuple(values)
    point = rng.random() * sum(weight for _, weight in items)
    upto = 0.0
    for value, weight in items:
        upto += weight
        if point <= upto:
            return value
    return items[-1][0]


def _poisson(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    limit = math.exp(-mean)
    product = 1.0
    value = 0
    while product > limit:
        value += 1
        product *= rng.random()
    return value - 1


def _months(start: date, end: date) -> list[date]:
    output: list[date] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        output.append(current)
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
    return output


def _month_end(month: date) -> date:
    return date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])


def _date_in_month(rng: random.Random, month: date) -> date:
    return date(month.year, month.month, rng.randint(1, calendar.monthrange(month.year, month.month)[1]))


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)


def _date_in_covered_month(
    rng: random.Random,
    month: date,
    period_start: date,
    period_end: date,
) -> date:
    lower = max(month, period_start)
    upper = min(_month_end(month), period_end)
    return lower + timedelta(days=rng.randint(0, (upper - lower).days))


def _coverage_segments(
    active_months: Iterable[date],
    period_start: date,
    period_end: date,
) -> dict[date, tuple[date, date]]:
    """Map each active month to the bounds of its contiguous coverage span."""

    ordered = sorted(active_months)
    output: dict[date, tuple[date, date]] = {}
    segment: list[date] = []
    for month in ordered:
        if segment and month != _next_month(segment[-1]):
            start = max(segment[0], period_start)
            end = min(_month_end(segment[-1]), period_end)
            output.update({item: (start, end) for item in segment})
            segment = []
        segment.append(month)
    if segment:
        start = max(segment[0], period_start)
        end = min(_month_end(segment[-1]), period_end)
        output.update({item: (start, end) for item in segment})
    return output


def _birth_date(rng: random.Random, age: int, as_of: date) -> date:
    year = as_of.year - age
    month = rng.randint(1, 12)
    day = rng.randint(1, calendar.monthrange(year, month)[1])
    born = date(year, month, day)
    if born > as_of:
        born = date(year - 1, month, day)
    return born


def _luhn_check_digit(number: str) -> str:
    digits = [int(char) for char in number]
    total = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def synthetic_npi(index: int) -> str:
    """Return a checksum-valid but clearly synthetic, 9-prefixed NPI."""

    base = f"9{index % 100_000_000:08d}"
    return base + _luhn_check_digit("80840" + base)


def _age_band(age: int) -> str:
    for low, high, label in (
        (0, 17, "0-17"), (18, 24, "18-24"), (25, 34, "25-34"),
        (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64"),
        (65, 74, "65-74"), (75, 84, "75-84"), (85, 200, "85+"),
    ):
        if low <= age <= high:
            return label
    return "Unknown"


def _condition_set(rng: random.Random, age: int, sex: str) -> list[str]:
    conditions: list[str] = []
    normalized_age = min(max(age - 18, 0) / 47.0, 1.0)
    for key, spec in CONDITIONS.items():
        probability = spec.base + spec.age_slope * normalized_age ** 1.65
        if sex == "F":
            probability *= spec.female_multiplier
        if rng.random() < min(probability, .72):
            conditions.append(key)
    if "type_2_diabetes" in conditions and rng.random() < .70 and "hyperlipidemia" not in conditions:
        conditions.append("hyperlipidemia")
    if "cad" in conditions and rng.random() < .72 and "hypertension" not in conditions:
        conditions.append("hypertension")
    return sorted(conditions)


def _make_providers(
    rng: random.Random,
    profile: PayerProfile,
) -> tuple[tuple[Row, ...], tuple[Row, ...]]:
    providers: list[Row] = []
    for index in range(1, 801):
        specialty, category = SPECIALTIES[(index - 1) % len(SPECIALTIES)]
        sex = "F" if rng.random() < .49 else "M"
        state = _weighted_choice(rng, profile.states)
        providers.append({
            "provider_id": f"PRV{index:06d}",
            "npi": synthetic_npi(index),
            "first_name": rng.choice(FIRST_NAMES_F if sex == "F" else FIRST_NAMES_M),
            "last_name": rng.choice(LAST_NAMES),
            "specialty": specialty,
            "provider_category": category,
            "state": state,
            "zip_code": rng.choice(ZIP_BY_STATE[state]),
            "network_id": f"NW{1 + index % 8:02d}",
            "tin": f"98{index:07d}",
        })
    facilities: list[Row] = []
    types = ("Acute Care Hospital", "Ambulatory Surgery Center", "Diagnostic Center", "Urgent Care")
    for index in range(1, 81):
        state = _weighted_choice(rng, profile.states)
        facilities.append({
            "facility_id": f"FAC{index:05d}",
            "npi": synthetic_npi(20_000 + index),
            "name": f"Synthetic {rng.choice(('Regional', 'Community', 'Memorial', 'University'))} {types[(index - 1) % len(types)]}",
            "facility_type": types[(index - 1) % len(types)],
            "state": state,
            "zip_code": rng.choice(ZIP_BY_STATE[state]),
            "tin": f"97{index:07d}",
        })
    return tuple(providers), tuple(facilities)


def _household_size(rng: random.Random) -> int:
    return int(_weighted_choice(rng, (("1", .29), ("2", .32), ("3", .16), ("4", .15), ("5", .06), ("6", .02))))


def _member_age(rng: random.Random, relation: str, subscriber_age: int) -> int:
    if relation == "18":
        return subscriber_age
    if relation == "01":
        return max(18, min(64, subscriber_age + rng.randint(-7, 7)))
    return rng.randint(0, min(25, max(1, subscriber_age - 18)))


def _generate_members(
    rng: random.Random,
    config: GenerationConfig,
    profile: PayerProfile,
    providers: tuple[Row, ...],
) -> tuple[tuple[Row, ...], tuple[Row, ...]]:
    all_months = _months(config.start_date, config.end_date)
    members: list[Row] = []
    enrollments: list[Row] = []
    member_index = 1
    household_index = 1
    while member_index <= config.member_count:
        size = min(_household_size(rng), config.member_count - member_index + 1)
        subscriber_age = max(22, min(64, round(rng.triangular(22, 64, 43))))
        subscriber_id = f"{profile.member_prefix}S{household_index:07d}"
        last_name = rng.choice(LAST_NAMES)
        state = _weighted_choice(rng, profile.states)
        zip_code = rng.choice(ZIP_BY_STATE[state])
        product = _weighted_choice(rng, profile.products)
        funding = "ASO" if rng.random() < .64 else "FI"
        group_id = f"GRP{1 + household_index % 750:05d}"
        source_system = _weighted_choice(rng, profile.source_systems)
        for household_position in range(size):
            relation = "18" if household_position == 0 else ("01" if household_position == 1 and size > 1 and rng.random() < .82 else "19")
            age = _member_age(rng, relation, subscriber_age)
            sex = "F" if rng.random() < .508 else "M"
            birth_date = _birth_date(rng, age, config.end_date)
            conditions = _condition_set(rng, age, sex)
            risk_score = round(.35 + age / 72 + sum(
                0.65 if condition in {"heart_failure", "ckd", "copd", "cad"} else .24
                for condition in conditions
            ), 3)
            member_id = f"{profile.member_prefix}M{member_index:08d}"
            latest_start_index = min(8, len(all_months) - 1)
            start_index = (
                0
                if rng.random() < .86 or latest_start_index == 0
                else rng.randint(1, latest_start_index)
            )
            end_index = len(all_months) - 1
            if rng.random() < .13 and start_index + 5 < end_index:
                end_index = rng.randint(start_index + 5, end_index - 1)
            active_months = all_months[start_index:end_index + 1]
            if len(active_months) > 12 and rng.random() < .035:
                gap_start = rng.randint(5, len(active_months) - 5)
                gap_length = 1 if rng.random() < .78 else 2
                active_months = active_months[:gap_start] + active_months[gap_start + gap_length:]
            pcp_specialties = (
                {"Pediatrics", "Family Medicine"}
                if age < 18
                else {"Family Medicine", "Internal Medicine"}
            )
            pcp_pool = [
                row for row in providers
                if row["specialty"] in pcp_specialties and row["state"] == state
            ]
            if not pcp_pool:
                pcp_pool = [row for row in providers if row["specialty"] in pcp_specialties]
            pcp = rng.choice(pcp_pool)
            plan_code = "HDP" if product == "HDHP" else product
            member = {
                "person_id": f"P{profile.member_prefix}{member_index:08d}",
                "member_id": member_id,
                "subscriber_id": subscriber_id,
                "relation_code": relation,
                "sex": sex,
                "birth_date": birth_date,
                "death_date": None,
                "age": age,
                "age_band": _age_band(age),
                "state": state,
                "zip_code": zip_code,
                "cbsa": f"{10000 + int(zip_code[:3]) % 89999:05d}",
                "product": product,
                "funding": funding,
                "plan_id": f"{plan_code}{1 + household_index % 12:02d}",
                "plan_name": f"Synthetic {product} {1 + household_index % 12}",
                "plan_type": "commercial",
                "group_id": group_id,
                "group_name": f"Synthetic Employer {1 + household_index % 750}",
                "rx_coverage": "Y" if rng.random() < .93 else "N",
                "mh_coverage": "Y" if rng.random() < .97 else "N",
                "risk_score": risk_score,
                "conditions": conditions,
                "first_name": rng.choice(FIRST_NAMES_F if sex == "F" else FIRST_NAMES_M),
                "last_name": last_name,
                "race": _weighted_choice(rng, (("white", .56), ("black", .13), ("asian", .07), ("other", .06), ("unknown", .18))),
                "ethnicity": "hispanic" if rng.random() < .19 else "not hispanic",
                "source_system": source_system,
                "active_months": tuple(active_months),
                "pcp_npi": pcp["npi"],
            }
            members.append(member)
            coverage_by_month = _coverage_segments(
                active_months, config.start_date, config.end_date
            )
            for month in active_months:
                span_start, span_end = coverage_by_month[month]
                enrollments.append({
                    **{key: value for key, value in member.items() if key not in {"active_months", "conditions"}},
                    "conditions": tuple(conditions),
                    "enrollment_month": month,
                    "enrollment_year": month.year,
                    "enrollment_start_date": span_start,
                    "enrollment_end_date": span_end,
                    "enrollment_status": "active",
                    "pcp_npi": pcp["npi"],
                    "source_system": source_system,
                    "file_name": f"eligibility_{month:%Y%m}.csv",
                    "file_date": _month_end(month),
                })
            member_index += 1
        household_index += 1
    return tuple(members), tuple(enrollments)


def _choose_provider(
    rng: random.Random,
    providers: tuple[Row, ...],
    specialty: str | None = None,
    state: str | None = None,
    local_probability: float = .94,
) -> Row:
    options = tuple(
        row for row in providers
        if specialty is None or row["specialty"] == specialty
    ) or providers
    local = tuple(row for row in options if row["state"] == state)
    if local and rng.random() < local_probability:
        return rng.choice(local)
    return rng.choice(options)


def _choose_facility(
    rng: random.Random,
    facilities: tuple[Row, ...],
    *,
    setting: str,
    state: str,
    local_probability: float,
) -> Row:
    allowed_types = {
        "inpatient": {"Acute Care Hospital"},
        "emergency": {"Acute Care Hospital", "Urgent Care"},
        "outpatient": {"Acute Care Hospital", "Ambulatory Surgery Center", "Diagnostic Center"},
    }[setting]
    compatible = tuple(
        row for row in facilities if row["facility_type"] in allowed_types
    )
    local = tuple(row for row in compatible if row["state"] == state)
    if local and rng.random() < local_probability:
        return rng.choice(local)
    return rng.choice(compatible)


def _plan_cost_share(
    rng: random.Random,
    *,
    allowed: float,
    product: str,
    setting: str,
    service_date: date,
) -> tuple[float, float, float, float]:
    copay_base = {
        "professional": 25.0, "outpatient": 55.0, "emergency": 240.0, "inpatient": 450.0,
    }[setting]
    copay = 0.0 if product == "HDHP" else min(allowed, copay_base * rng.uniform(.8, 1.2))
    deductible_rate = {"HDHP": .28, "PPO": .08, "POS": .07, "EPO": .05, "HMO": .025}.get(product, .07)
    deductible_rate *= max(.25, 1.3 - service_date.timetuple().tm_yday / 250)
    deductible = min(max(allowed - copay, 0), allowed * deductible_rate * rng.uniform(.45, 1.45))
    remainder = max(allowed - copay - deductible, 0)
    coins_rate = {"HDHP": .18, "PPO": .19, "POS": .16, "EPO": .14, "HMO": .08}.get(product, .18)
    coinsurance = remainder * coins_rate
    member = min(allowed, copay + deductible + coinsurance)
    return tuple(round(value, 2) for value in (member, copay, deductible, coinsurance))


def _line_financials(
    rng: random.Random,
    *,
    base_charge: float,
    product: str,
    setting: str,
    network: bool,
    service_date: date,
    denied: bool,
) -> dict[str, float]:
    charge = round(rng.lognormvariate(math.log(max(base_charge, 1)), .34), 2)
    if denied:
        return {
            "charge_amount": charge, "allowed_amount": 0.0, "plan_paid_amount": 0.0,
            "member_paid_amount": 0.0, "coinsurance_amount": 0.0,
            "copay_amount": 0.0, "deductible_amount": 0.0, "other_payer_amount": 0.0,
        }
    ratio = rng.uniform(.48, .73) if network else rng.uniform(.24, .52)
    allowed = round(charge * ratio, 2)
    other = round(allowed * rng.uniform(.10, .35), 2) if rng.random() < .018 else 0.0
    primary_allowed = round(max(allowed - other, 0), 2)
    member, copay, deductible, coinsurance = _plan_cost_share(
        rng,
        allowed=primary_allowed,
        product=product,
        setting=setting,
        service_date=service_date,
    )
    plan_paid = round(primary_allowed - member, 2)
    return {
        "charge_amount": charge,
        "allowed_amount": allowed,
        "plan_paid_amount": plan_paid,
        "member_paid_amount": member,
        "coinsurance_amount": coinsurance,
        "copay_amount": copay,
        "deductible_amount": deductible,
        "other_payer_amount": other,
    }


def _diagnoses_for_member(rng: random.Random, member: Row, primary: str | None = None) -> list[str]:
    diagnoses = [primary] if primary else []
    chronic = [CONDITIONS[key].code for key in member["conditions"]]
    rng.shuffle(chronic)
    diagnoses.extend(chronic[: rng.randint(0, min(4, len(chronic)))])
    output: list[str] = []
    for code in diagnoses:
        if code and code not in output:
            output.append(code)
    return output or ["Z0000"]


def _base_claim_row(
    *,
    claim_id: str,
    line_number: int,
    member: Row,
    setting: str,
    service_date: date,
    end_date: date,
    provider: Row,
    facility: Row | None,
    diagnoses: list[str],
    network: bool,
    denied: bool,
) -> Row:
    institutional = setting in {"inpatient", "outpatient", "emergency"}
    paid_date = end_date + timedelta(days=7 + (sum(ord(char) for char in claim_id) % 39))
    return {
        "claim_id": claim_id,
        "original_claim_id": claim_id,
        "adjustment_sequence": 0,
        "final_action": True,
        "line_number": line_number,
        "person_id": member["person_id"],
        "member_id": member["member_id"],
        "claim_type": "institutional" if institutional else "professional",
        "setting": setting,
        "claim_form_type": "U" if institutional else "P",
        "first_service_date": service_date,
        "last_service_date": end_date,
        "claim_first_date": service_date,
        "claim_line_start_date": service_date,
        "claim_line_end_date": end_date,
        "payer": member.get("payer"),
        "plan": member["plan_name"],
        "admission_date": service_date if setting == "inpatient" else None,
        "discharge_date": end_date if setting == "inpatient" else None,
        "paid_date": paid_date,
        "admit_source": "1" if setting == "inpatient" else None,
        "admit_type": "1" if setting == "inpatient" else None,
        "discharge_status": "01" if setting == "inpatient" else None,
        "bill_type": "111" if setting == "inpatient" else ("131" if institutional else None),
        "place_of_service": None if institutional else "11",
        "revenue_code": None,
        "hcpcs_code": None,
        "modifier_1": None,
        "modifier_2": None,
        "modifier_3": None,
        "modifier_4": None,
        "diagnosis_codes": list(diagnoses),
        "diagnosis_code_type": "icd-10-cm",
        "poa_codes": ["Y"] * len(diagnoses) if setting == "inpatient" else [],
        "procedure_codes": [],
        "procedure_code_type": None,
        "procedure_dates": [],
        "drg_code_type": None,
        "drg_code": None,
        "rendering_npi": provider["npi"],
        "billing_npi": facility["npi"] if institutional and facility else provider["npi"],
        "facility_npi": facility["npi"] if institutional and facility else None,
        "provider_category": provider["provider_category"],
        "provider_state": provider["state"],
        "provider_zip_code": provider["zip_code"],
        "units": 1,
        "network_flag": 1 if network else 0,
        "primary_coverage_indicator": "P",
        "claim_status": "denied" if denied else "paid",
        "denied_flag": 1 if denied else 0,
        "service_category": setting,
        "source_system": member["source_system"],
        "file_name": f"medical_{paid_date:%Y%m}.csv",
        "file_date": _month_end(paid_date.replace(day=1)),
    }


def _professional_claim(
    rng: random.Random,
    claim_id: str,
    member: Row,
    service_date: date,
    providers: tuple[Row, ...],
    profile: PayerProfile,
) -> list[Row]:
    if member["conditions"] and rng.random() < .72:
        condition_key = rng.choice(member["conditions"])
        primary = CONDITIONS[condition_key].code
        hcpcs = "99214" if member["risk_score"] > 1.8 else "99213"
        specialty = {
            "heart_failure": "Cardiology", "cad": "Cardiology",
            "type_2_diabetes": "Endocrinology", "depression": "Psychiatry",
            "anxiety": "Psychiatry", "osteoarthritis": "Orthopedic Surgery",
        }.get(condition_key)
    elif rng.random() < .34:
        primary, hcpcs = "Z0000", "99395" if member["age"] < 40 else "99396"
        specialty = "Pediatrics" if member["age"] < 18 else "Family Medicine"
    else:
        primary, hcpcs, _ = rng.choice(ACUTE_DIAGNOSES)
        specialty = "Pediatrics" if member["age"] < 18 else "Family Medicine"
    network = rng.random() < profile.network_rate
    if specialty is None:
        specialty = "Pediatrics" if member["age"] < 18 else rng.choice(
            ("Family Medicine", "Internal Medicine")
        )
    provider = _choose_provider(
        rng,
        providers,
        specialty,
        state=member["state"],
        local_probability=.975 if network else .62,
    )
    diagnoses = _diagnoses_for_member(rng, member, primary)
    denied = rng.random() < .025
    line_count = 1 + (rng.random() < .18) + (rng.random() < .04)
    lines: list[Row] = []
    codes = [hcpcs, "36415", "80053"]
    for line_number in range(1, int(line_count) + 1):
        row = _base_claim_row(
            claim_id=claim_id, line_number=line_number, member=member,
            setting="professional", service_date=service_date, end_date=service_date,
            provider=provider, facility=None, diagnoses=diagnoses, network=network,
            denied=denied,
        )
        row["hcpcs_code"] = codes[line_number - 1]
        row["place_of_service"] = "02" if rng.random() < .09 else ("22" if specialty in {"Cardiology", "Orthopedic Surgery"} and rng.random() < .25 else "11")
        row.update(_line_financials(
            rng, base_charge=(185.0 if line_number == 1 else 75.0),
            product=member["product"], setting="professional", network=network,
            service_date=service_date, denied=denied,
        ))
        lines.append(row)
    return lines


def _facility_claim(
    rng: random.Random,
    claim_id: str,
    member: Row,
    service_date: date,
    setting: str,
    providers: tuple[Row, ...],
    facilities: tuple[Row, ...],
    profile: PayerProfile,
    coverage_end: date,
) -> list[Row]:
    network = rng.random() < profile.network_rate
    local_probability = .98 if network else .68
    facility = _choose_facility(
        rng,
        facilities,
        setting=setting,
        state=member["state"],
        local_probability=local_probability,
    )
    specialty = (
        "Emergency Medicine"
        if setting == "emergency"
        else ("Pediatrics" if member["age"] < 18 else "Internal Medicine")
    )
    provider = _choose_provider(
        rng,
        providers,
        specialty,
        state=facility["state"],
        local_probability=.985 if network else .72,
    )
    denied = rng.random() < (.018 if setting == "inpatient" else .035)
    if setting == "inpatient":
        candidates = list(INPATIENT_TEMPLATES)
        if member["sex"] != "F" or not 18 <= member["age"] <= 45:
            candidates = [item for item in candidates if item[0] != "O80"]
        primary, drg, procedure, _, base_total = rng.choice(candidates)
        stay = max(1, min(12, round(rng.lognormvariate(math.log(3.2), .45))))
        end_date = min(service_date + timedelta(days=stay), coverage_end)
        line_count = rng.randint(4, 9)
        revenue_codes = ["0100", "0250", "0300", "0320", "0360", "0450", "0636", "0762", "0270"]
    elif setting == "emergency":
        primary, _, _ = rng.choice(ACUTE_DIAGNOSES)
        drg, procedure, base_total, end_date = None, "99285", 3_400.0, service_date
        line_count, revenue_codes = rng.randint(2, 5), ["0450", "0250", "0300", "0320", "0762"]
    else:
        primary = rng.choice(_diagnoses_for_member(rng, member))
        drg, procedure, base_total, end_date = None, rng.choice(("72148", "74177", "45378", "43239", "66984")), 2_700.0, service_date
        line_count, revenue_codes = rng.randint(2, 6), ["0360", "0320", "0300", "0250", "0762", "0490"]
    diagnoses = _diagnoses_for_member(rng, member, primary)
    weights = [rng.random() + .2 for _ in range(line_count)]
    weight_total = sum(weights)
    lines: list[Row] = []
    for line_number in range(1, line_count + 1):
        row = _base_claim_row(
            claim_id=claim_id, line_number=line_number, member=member,
            setting=setting, service_date=service_date, end_date=end_date,
            provider=provider, facility=facility, diagnoses=diagnoses, network=network,
            denied=denied,
        )
        row["revenue_code"] = revenue_codes[(line_number - 1) % len(revenue_codes)]
        row["hcpcs_code"] = procedure if line_number == 1 else rng.choice(("80053", "85025", "36415", "J3490", "71046"))
        row["drg_code"] = drg
        row["drg_code_type"] = "ms-drg" if drg else None
        if setting == "inpatient" and line_number == 1 and procedure in {"27447", "44970", "59400"}:
            row["procedure_codes"] = [{"27447": "0SRC0J9", "44970": "0DTJ4ZZ", "59400": "10E0XZZ"}[procedure]]
            row["procedure_code_type"] = "icd-10-pcs"
            row["procedure_dates"] = [service_date]
        row.update(_line_financials(
            rng, base_charge=base_total * weights[line_number - 1] / weight_total,
            product=member["product"], setting=setting, network=network,
            service_date=service_date, denied=denied,
        ))
        lines.append(row)
    return lines


def _generate_medical_claims(
    rng: random.Random,
    members: tuple[Row, ...],
    providers: tuple[Row, ...],
    facilities: tuple[Row, ...],
    profile: PayerProfile,
    config: GenerationConfig,
) -> tuple[Row, ...]:
    rows: list[Row] = []
    claim_sequence = count(1)
    for member in members:
        coverage_by_month = _coverage_segments(
            member["active_months"], config.start_date, config.end_date
        )
        months_by_year: dict[int, list[date]] = defaultdict(list)
        for month in member["active_months"]:
            months_by_year[month.year].append(month)
        for year, active_months in months_by_year.items():
            exposure_fraction = len(active_months) / 12
            age_factor = max(member["age"] - 35, 0) / 35
            condition_count = len(member["conditions"])
            event_counts = {
                "professional": _poisson(
                    rng, (1.55 + .40 * condition_count + .35 * age_factor) * exposure_fraction
                ),
                "outpatient": _poisson(
                    rng, (.28 + .08 * condition_count + .10 * age_factor) * exposure_fraction
                ),
                "emergency": _poisson(
                    rng, (.10 + .025 * condition_count + .035 * age_factor) * exposure_fraction
                ),
                "inpatient": _poisson(
                    rng, (.012 + .010 * condition_count + .018 * age_factor) * exposure_fraction
                ),
            }
            for setting, event_count in event_counts.items():
                for _ in range(event_count):
                    month = rng.choice(active_months)
                    span_start, coverage_end = coverage_by_month[month]
                    service_date = _date_in_covered_month(
                        rng, month, max(config.start_date, span_start), coverage_end
                    )
                    if (
                        setting == "inpatient"
                        and service_date == coverage_end
                        and service_date > span_start
                    ):
                        service_date -= timedelta(days=1)
                    claim_id = f"{profile.member_prefix}C{next(claim_sequence):010d}"
                    if setting == "professional":
                        rows.extend(_professional_claim(rng, claim_id, member, service_date, providers, profile))
                    else:
                        rows.extend(_facility_claim(
                            rng,
                            claim_id,
                            member,
                            service_date,
                            setting,
                            providers,
                            facilities,
                            profile,
                            coverage_end,
                        ))
    return tuple(rows)


def _pharmacy_row(
    rng: random.Random,
    *,
    claim_id: str,
    member: Row,
    fill_date: date,
    medication: tuple[str, str, str, float, float],
    refill: int,
    profile: PayerProfile,
) -> Row:
    ndc, drug_name, therapeutic_class, base_cost, _ = medication
    mail = rng.random() < .17
    days_supply = 90 if mail else 30
    generic = base_cost < 75
    charge = round(max(4.0, rng.lognormvariate(math.log(max(base_cost, 4)), .22)) * (days_supply / 30), 2)
    allowed = round(charge * rng.uniform(.72, .94), 2)
    # The three public pharmacy layouts represent paid/adjudicated extracts;
    # rejected transactions are not emitted without a native status contract.
    denied = False
    deductible = round(min(allowed, allowed * rng.uniform(.05, .28) if member["product"] == "HDHP" else 0), 2)
    copay = round(min(max(allowed - deductible, 0), 10.0 if generic else 45.0), 2)
    coinsurance = round(max(allowed - deductible - copay, 0) * (.08 if generic else .18), 2)
    member_paid = round(min(allowed, deductible + copay + coinsurance), 2)
    plan_paid = round(allowed - member_paid, 2)
    paid_date = fill_date + timedelta(days=rng.randint(0, 3))
    return {
        "claim_id": claim_id,
        "original_claim_id": claim_id,
        "adjustment_sequence": 0,
        "final_action": True,
        "line_number": 1,
        "person_id": member["person_id"],
        "member_id": member["member_id"],
        "payer": member.get("payer"),
        "plan": member["plan_name"],
        "fill_date": fill_date,
        "paid_date": paid_date,
        "ndc_code": ndc,
        "drug_name": drug_name,
        "therapeutic_class": therapeutic_class,
        "quantity": 90 if days_supply == 90 else 30,
        "days_supply": days_supply,
        "refill_number": refill,
        "daw_code": "0",
        "prescriber_npi": member["pcp_npi"],
        "pharmacy_npi": synthetic_npi(40_000 + int(member["member_id"][-5:]) % 500),
        "network_flag": 1 if rng.random() < profile.network_rate else 0,
        "mail_order_flag": 1 if mail else 0,
        "generic_flag": 1 if generic else 0,
        "maintenance_flag": 1,
        "claim_status": "denied" if denied else "paid",
        "denied_flag": 1 if denied else 0,
        "charge_amount": charge,
        "allowed_amount": allowed,
        "plan_paid_amount": plan_paid,
        "member_paid_amount": member_paid,
        "coinsurance_amount": coinsurance,
        "copay_amount": copay,
        "deductible_amount": deductible,
        "ingredient_cost": round(max(allowed - 1.75, 0), 2),
        "dispensing_fee": 0.0 if denied else min(1.75, allowed),
        "source_system": member["source_system"],
        "file_name": f"pharmacy_{paid_date:%Y%m}.csv",
        "file_date": _month_end(paid_date.replace(day=1)),
    }


def _generate_pharmacy_claims(
    rng: random.Random,
    members: tuple[Row, ...],
    profile: PayerProfile,
    config: GenerationConfig,
) -> tuple[Row, ...]:
    rows: list[Row] = []
    sequence = count(1)
    for member in members:
        active_months = set(member["active_months"])
        if member["rx_coverage"] != "Y" or not active_months:
            continue
        for condition_key in member["conditions"]:
            medication = MEDICATIONS.get(condition_key)
            if not medication or medication[4] == 0 or rng.random() > medication[4]:
                continue
            adherence = min(.96, max(.28, rng.betavariate(6, 2.1)))
            first_month = min(active_months)
            fill = _date_in_covered_month(
                rng, first_month, config.start_date, config.end_date
            )
            refill = 0
            while fill <= min(_month_end(max(active_months)), config.end_date):
                if fill.replace(day=1) in active_months and rng.random() < adherence:
                    claim_id = f"{profile.member_prefix}R{next(sequence):010d}"
                    row = _pharmacy_row(
                        rng, claim_id=claim_id, member=member, fill_date=fill,
                        medication=medication, refill=refill, profile=profile,
                    )
                    rows.append(row)
                    refill += 1
                    fill += timedelta(days=row["days_supply"])
                else:
                    fill += timedelta(days=30)
        if rng.random() < .14:
            # Sets are intentionally used for fast coverage checks above, but
            # their iteration order varies with PYTHONHASHSEED.  Sort before
            # sampling so identical generator seeds are reproducible across
            # separate Python processes as well as within one process.
            month = rng.choice(tuple(sorted(active_months)))
            acute = ("00093310901", "Amoxicillin 500mg cap", "Antibiotic", 14.0, 1.0)
            claim_id = f"{profile.member_prefix}R{next(sequence):010d}"
            row = _pharmacy_row(
                rng,
                claim_id=claim_id,
                member=member,
                fill_date=_date_in_covered_month(
                    rng, month, config.start_date, config.end_date
                ),
                medication=acute, refill=0, profile=profile,
            )
            row["days_supply"] = 10
            row["quantity"] = 30
            row["maintenance_flag"] = 0
            rows.append(row)
    return tuple(rows)


def generate_canonical(config: GenerationConfig) -> CanonicalDataset:
    """Generate one clean deterministic cohort before issue injection."""

    if config.payer not in PAYER_PROFILES:
        raise ValueError(f"Unknown payer profile: {config.payer}")
    if config.member_count <= 0:
        raise ValueError("member_count must be positive")
    if config.start_date > config.end_date:
        raise ValueError("start_date must not be after end_date")
    profile = PAYER_PROFILES[config.payer]
    rng = random.Random(config.seed)
    providers, facilities = _make_providers(rng, profile)
    members, enrollments = _generate_members(rng, config, profile, providers)
    for member in members:
        member["payer"] = profile.label
    for enrollment in enrollments:
        enrollment["payer"] = profile.label
    medical_claims = _generate_medical_claims(
        rng, members, providers, facilities, profile, config
    )
    pharmacy_claims = _generate_pharmacy_claims(rng, members, profile, config)
    return CanonicalDataset(
        members=members,
        enrollment_months=enrollments,
        providers=providers,
        facilities=facilities,
        medical_claim_lines=medical_claims,
        pharmacy_claims=pharmacy_claims,
        start_date=config.start_date,
        end_date=config.end_date,
        seed=config.seed,
    )
