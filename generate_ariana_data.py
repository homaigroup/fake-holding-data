#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_ariana_data.py
========================
تولید داده فیک برای «هلدینگ آریانا» — یک هلدینگ چندرشته‌ای فرضی با ۶ زیرمجموعه
(خرده‌فروشی، لجستیک، دیجیتال، تولید، مالی، املاک) بر اساس اسکیمای طراحی‌شده در
سند "اسکیمای هلدینگ آریانا". هدف: تولید داده‌ی واقع‌گرایانه برای تست سامانه‌های
Text-to-SQL — با روابط FK درست، سلسله‌مراتب، جدول‌های تاریخچه‌دار (SCD) و درصد
کنترل‌شده‌ای از داده‌ی کثیف (null، فرمت ناهماهنگ، مقادیر پرت، رکورد تکراری).

نصب پیش‌نیازها:
    pip install Faker jdatetime

اجرای پایه:
    python generate_ariana_data.py --scale small --out-dir ./ariana_fake_data

پارامترهای مهم:
    --seed          seed تصادفی برای بازتولیدپذیری (پیش‌فرض 42)
    --scale         tiny | small | medium | large  (حجم جدول‌های تراکنشی)
    --dirty-rate    نسبت داده‌ی کثیف بین 0 تا 1 (پیش‌فرض 0.05 یعنی ۵٪)
    --out-dir       مسیر خروجی
    --csv           تولید خروجی CSV به‌ازای هر جدول (پیش‌فرض: روشن)
    --no-csv        خاموش کردن خروجی CSV
    --sqlite        تولید یک فایل SQLite واحد (ariana.db) از همه‌ی جدول‌ها
    --start-year    سال میلادی شروع بازه تراکنش‌ها (پیش‌فرض 2023)
    --end-year      سال میلادی پایان بازه تراکنش‌ها (پیش‌فرض 2026)

خروجی: هر جدول یک لیست از dict است که هم به CSV و هم (اختیاری) به SQLite
نوشته می‌شود. ترتیب تولید طوری است که همه‌ی FKها همیشه از رکوردهای موجود
انتخاب می‌شوند (کلید ارجاعی نامعتبر تولید نمی‌شود).
"""

import argparse
import csv
import os
import random
import sqlite3
import string
from datetime import date, datetime, timedelta
from itertools import count

try:
    from faker import Faker
except ImportError:
    raise SystemExit("این اسکریپت به Faker نیاز دارد: pip install Faker jdatetime")

try:
    import jdatetime
    HAS_JDATETIME = True
except ImportError:
    HAS_JDATETIME = False


# --------------------------------------------------------------------------
# 1) تنظیمات مقیاس و پارامترها
# --------------------------------------------------------------------------

SCALE_PRESETS = {
    # ضریب اعمال‌شده روی جدول‌های «تراکنشی/فکت»؛ جدول‌های ابعادی (dimension)
    # مستقل از این ضریب یا با ضریب ملایم‌تر رشد می‌کنند.
    "tiny":   0.2,
    "small":  1.0,
    "medium": 5.0,
    "large":  20.0,
}

CITIES = [
    ("تهران", "تهران"), ("مشهد", "خراسان رضوی"), ("اصفهان", "اصفهان"),
    ("شیراز", "فارس"), ("تبریز", "آذربایجان شرقی"), ("کرج", "البرز"),
    ("اهواز", "خوزستان"), ("قم", "قم"), ("کرمانشاه", "کرمانشاه"),
    ("رشت", "گیلان"), ("یزد", "یزد"), ("اردبیل", "اردبیل"),
    ("بندرعباس", "هرمزگان"), ("زاهدان", "سیستان و بلوچستان"),
    ("کرمان", "کرمان"), ("ارومیه", "آذربایجان غربی"), ("همدان", "همدان"),
    ("ساری", "مازندران"), ("قزوین", "قزوین"), ("گرگان", "گلستان"),
]

RETAIL_CATEGORY_TREE = {
    "خوار و بار": ["برنج و حبوبات", "روغن و لبنیات", "نوشیدنی"],
    "لوازم خانگی": ["آشپزخانه", "برقی کوچک", "بهداشتی خانه"],
    "پوشاک": ["مردانه", "زنانه", "بچگانه"],
    "دیجیتال و لوازم جانبی": ["موبایل", "کامپیوتر", "صوتی تصویری"],
}

MFG_PRODUCTS = ["ورق فولادی نوع A", "پروفیل آلومینیومی", "لوله پلیمری",
                "قطعه پلاستیکی تزریقی", "کابل برق خانگی", "پنل کامپوزیت"]
MFG_MATERIALS = ["گرانول پلی‌اتیلن", "ورق روی", "سیم مسی", "رزین اپوکسی",
                 "پودر رنگ", "چسب صنعتی", "فوم عایق", "شمش آلومینیوم"]


# --------------------------------------------------------------------------
# 2) ابزارهای کمکی مشترک
# --------------------------------------------------------------------------

class IDGen:
    """شمارنده‌ی کلید اصلی مستقل برای هر جدول."""
    def __init__(self):
        self._counters = {}

    def next(self, table):
        c = self._counters.setdefault(table, count(1))
        return next(c)


def chance(p):
    return random.random() < p


def maybe_none(value, rate):
    """با احتمال rate مقدار را null می‌کند (شبیه‌سازی داده کثیف)."""
    return None if chance(rate) else value


def dirty_phone(rate):
    """شماره تلفن با فرمت گاهی ناهماهنگ."""
    base = "09" + "".join(random.choice(string.digits) for _ in range(9))
    if chance(rate):
        variants = [
            base[:4] + "-" + base[4:],
            "+98" + base[1:],
            "0098" + base[1:],
            base[:-1],              # یک رقم کم — خطای واقعی داده
        ]
        return random.choice(variants)
    return base


def dirty_amount(value, rate):
    """مقدار پولی که گاهی پرت (outlier) یا منفی اشتباه ثبت شده."""
    if chance(rate):
        return round(value * random.choice([0.01, 10, -1]), 0)
    return round(value, 0)


def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def rand_datetime(start: date, end: date) -> datetime:
    d = rand_date(start, end)
    return datetime.combine(d, datetime.min.time()) + timedelta(
        seconds=random.randint(0, 86399)
    )


def to_shamsi(d) -> str:
    if d is None:
        return None
    if not HAS_JDATETIME:
        return None
    if isinstance(d, datetime):
        d = d.date()
    j = jdatetime.date.fromgregorian(date=d)
    return j.strftime("%Y-%m-%d")


def national_id() -> str:
    """کد ملی ۱۰ رقمی با رقم کنترلی معتبر (الگوریتم رسمی ایران)."""
    digits = [random.randint(0, 9) for _ in range(9)]
    s = sum(d * (10 - i) for i, d in enumerate(digits))
    r = s % 11
    check = r if r < 2 else 11 - r
    digits.append(check)
    return "".join(str(d) for d in digits)


def iban_ir() -> str:
    return "IR" + "".join(random.choice(string.digits) for _ in range(24))


def pick(seq):
    return random.choice(seq)


def weighted_status(pairs):
    """pairs: [(value, weight), ...]"""
    values, weights = zip(*pairs)
    return random.choices(values, weights=weights, k=1)[0]


# --------------------------------------------------------------------------
# 3) موتور اصلی تولید داده
# --------------------------------------------------------------------------

class AriannaDataGenerator:
    def __init__(self, seed=42, scale="small", dirty_rate=0.05,
                 start_year=2023, end_year=2026):
        random.seed(seed)
        self.fk = Faker("fa_IR")
        Faker.seed(seed)
        self.scale = SCALE_PRESETS[scale]
        self.dirty = dirty_rate
        self.start_date = date(start_year, 1, 1)
        self.end_date = date(end_year, 9, 21)
        self.ids = IDGen()
        self.db = {}          # table_name -> list[dict]
        self.pk = {}          # table_name -> list[pk_value]

    # -- helpers ------------------------------------------------------

    def n(self, base):
        """تعداد رکورد یک جدول تراکنشی با اعمال ضریب scale."""
        return max(1, int(round(base * self.scale)))

    def add(self, table, row):
        self.db.setdefault(table, []).append(row)
        self.pk.setdefault(table, []).append(next(iter(row.values())))
        return row

    def any_pk(self, table):
        return pick(self.pk[table])

    # -- 3.1 لایه مشترک هلدینگ ----------------------------------------

    def gen_shared(self):
        subs_meta = [
            ("آریانا خرده‌فروشی", "retail", "تهران"),
            ("آریانا لجستیک", "logistics", "کرج"),
            ("آریانا دیجیتال", "digital", "تهران"),
            ("آریانا تولید", "manufacturing", "اصفهان"),
            ("آریانا مالی", "finance", "تهران"),
            ("آریانا املاک و ساختمان", "real_estate", "مشهد"),
        ]

        # --- departments (نیاز داریم قبل از employee بسازیم، اما manager
        #     و ceo بعد از employee ست می‌شوند -> دو مرحله‌ای) ---
        for name_fa, industry, city in subs_meta:
            sid = self.ids.next("holding_subsidiaries")
            self.add("holding_subsidiaries", {
                "subsidiary_id": sid,
                "name_fa": name_fa,
                "name_en": industry,
                "industry": industry,
                "hq_city": city,
                "ceo_employee_id": None,   # بعداً پر می‌شود
                "established_date": rand_date(date(1995, 1, 1), date(2015, 1, 1)),
                "status": "active",
            })

        dept_names = ["مدیریت", "مالی", "منابع انسانی", "فناوری اطلاعات",
                      "فروش و بازاریابی", "عملیات", "حقوقی", "حراست"]
        for sub in self.db["holding_subsidiaries"]:
            top_dept = self.add("departments", {
                "department_id": self.ids.next("departments"),
                "subsidiary_id": sub["subsidiary_id"],
                "parent_department_id": None,
                "name_fa": "دفتر مرکزی " + sub["name_fa"],
                "cost_center_code": f"CC-{sub['subsidiary_id']}-00",
            })
            for dn in dept_names:
                self.add("departments", {
                    "department_id": self.ids.next("departments"),
                    "subsidiary_id": sub["subsidiary_id"],
                    "parent_department_id": top_dept["department_id"],
                    "name_fa": dn,
                    "cost_center_code": f"CC-{sub['subsidiary_id']}-{dept_names.index(dn)+1:02d}",
                })

        # --- central_employees ---
        n_emp = self.n(250)
        depts_by_sub = {}
        for d in self.db["departments"]:
            depts_by_sub.setdefault(d["subsidiary_id"], []).append(d)

        managers_by_sub = {}
        for sub in self.db["holding_subsidiaries"]:
            sid = sub["subsidiary_id"]
            per_sub_n = max(20, n_emp // len(self.db["holding_subsidiaries"]))
            first_emp_of_sub = None
            for i in range(per_sub_n):
                dept = pick(depts_by_sub[sid])
                emp = self.add("central_employees", {
                    "emp_id": self.ids.next("central_employees"),
                    "personnel_code": f"P-{sid}-{i+1:05d}",
                    "full_name": self.fk.name(),
                    "national_id": national_id(),
                    "subsidiary_id": sid,
                    "department_id": dept["department_id"],
                    "manager_emp_id": None,
                    "job_title": self.fk.job(),
                    "hire_date": rand_date(date(2005, 1, 1), self.end_date),
                    "termination_date": None,
                    "employment_status": weighted_status(
                        [("active", 92), ("on_leave", 5), ("terminated", 3)]
                    ),
                })
                if first_emp_of_sub is None:
                    first_emp_of_sub = emp
                    managers_by_sub[sid] = emp
                else:
                    # ۷۰٪ زیرمجموعه‌ی مدیر مستقیم دارند (چارت سازمانی)
                    if chance(0.7):
                        emp["manager_emp_id"] = managers_by_sub[sid]["emp_id"]
            sub["ceo_employee_id"] = managers_by_sub[sid]["emp_id"]

        # --- central_payroll_history (SCD) ---
        for emp in self.db["central_employees"]:
            base_salary = random.randint(120, 900) * 1_000_000
            n_changes = random.randint(1, 4)
            cur_from = emp["hire_date"]
            for i in range(n_changes):
                cur_to = None if i == n_changes - 1 else rand_date(
                    cur_from, self.end_date
                )
                self.add("central_payroll_history", {
                    "payroll_id": self.ids.next("central_payroll_history"),
                    "emp_id": emp["emp_id"],
                    "base_salary_rial": maybe_none(
                        dirty_amount(base_salary, self.dirty), self.dirty * 0.3
                    ),
                    "bonus_rial": random.randint(0, 50) * 1_000_000,
                    "deductions_rial": random.randint(5, 40) * 1_000_000,
                    "pay_period": to_shamsi(cur_from) or "",
                    "effective_from": cur_from,
                    "effective_to": cur_to,
                })
                base_salary = int(base_salary * random.uniform(1.05, 1.3))
                if cur_to:
                    cur_from = cur_to

        # --- leave_requests ---
        for emp in self.db["central_employees"]:
            for _ in range(random.randint(0, 3)):
                start = rand_date(emp["hire_date"], self.end_date)
                self.add("leave_requests", {
                    "leave_id": self.ids.next("leave_requests"),
                    "emp_id": emp["emp_id"],
                    "leave_type": pick(["استحقاقی", "استعلاجی", "بدون‌حقوق"]),
                    "start_date": start,
                    "end_date": start + timedelta(days=random.randint(1, 14)),
                    "status": weighted_status(
                        [("approved", 75), ("pending", 15), ("rejected", 10)]
                    ),
                    "approved_by_emp_id": emp["manager_emp_id"],
                })

        # --- ownership_structure (SCD) ---
        for sub in self.db["holding_subsidiaries"]:
            remaining = 100.0
            n_owners = random.randint(1, 3)
            for i in range(n_owners):
                pct = round(remaining, 2) if i == n_owners - 1 else round(
                    remaining * random.uniform(0.2, 0.6), 2
                )
                remaining -= pct
                self.add("ownership_structure", {
                    "ownership_id": self.ids.next("ownership_structure"),
                    "subsidiary_id": sub["subsidiary_id"],
                    "owner_type": "holding" if i == 0 else pick(
                        ["minority_investor", "founder"]
                    ),
                    "owner_name": "هلدینگ آریانا" if i == 0 else self.fk.name(),
                    "share_percent": pct,
                    "effective_from": sub["established_date"],
                    "effective_to": None,
                })

        # --- board_members / board_memberships ---
        for _ in range(12):
            self.add("board_members", {
                "member_id": self.ids.next("board_members"),
                "full_name": self.fk.name(),
                "national_id": national_id(),
            })
        for sub in self.db["holding_subsidiaries"]:
            for m in random.sample(self.db["board_members"],
                                    k=min(4, len(self.db["board_members"]))):
                term_start = rand_date(date(2018, 1, 1), date(2023, 1, 1))
                self.add("board_memberships", {
                    "membership_id": self.ids.next("board_memberships"),
                    "member_id": m["member_id"],
                    "subsidiary_id": sub["subsidiary_id"],
                    "role": pick(["رئیس هیئت‌مدیره", "نایب‌رئیس", "عضو"]),
                    "term_start": term_start,
                    "term_end": term_start + timedelta(days=365 * 4),
                })

        # --- chart_of_accounts ---
        top_accounts = [
            ("1", "دارایی‌ها", "asset"), ("2", "بدهی‌ها", "liability"),
            ("3", "حقوق صاحبان سهام", "equity"),
            ("4", "درآمدها", "revenue"), ("5", "هزینه‌ها", "expense"),
        ]
        acc_code_pool = []
        for code, name, typ in top_accounts:
            self.add("chart_of_accounts", {
                "account_code": code, "parent_account_code": None,
                "account_name_fa": name, "account_type": typ,
            })
            for j in range(1, 5):
                sub_code = f"{code}{j}"
                self.add("chart_of_accounts", {
                    "account_code": sub_code, "parent_account_code": code,
                    "account_name_fa": f"{name} - زیرحساب {j}",
                    "account_type": typ,
                })
                acc_code_pool.append(sub_code)

        # --- consolidated_financial_statements ---
        months = []
        cur = self.start_date.replace(day=1)
        while cur <= self.end_date:
            months.append(cur)
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        for sub in self.db["holding_subsidiaries"] + [{"subsidiary_id": None}]:
            for m in months:
                for acc in random.sample(acc_code_pool, k=6):
                    self.add("consolidated_financial_statements", {
                        "statement_id": self.ids.next("consolidated_financial_statements"),
                        "subsidiary_id": sub["subsidiary_id"],
                        "account_code": acc,
                        "fiscal_year": jdatetime.date.fromgregorian(date=m).year if HAS_JDATETIME else m.year,
                        "fiscal_period": m.month,
                        "amount_rial": random.randint(-500, 5000) * 10_000_000,
                        "is_consolidated": sub["subsidiary_id"] is None,
                    })

        # --- intercompany_transactions ---
        sub_ids = [s["subsidiary_id"] for s in self.db["holding_subsidiaries"]]
        for _ in range(self.n(150)):
            a, b = random.sample(sub_ids, 2)
            self.add("intercompany_transactions", {
                "txn_id": self.ids.next("intercompany_transactions"),
                "from_subsidiary_id": a,
                "to_subsidiary_id": b,
                "txn_type": pick(["loan", "service_fee", "goods_transfer"]),
                "amount_rial": random.randint(50, 20000) * 1_000_000,
                "txn_date": rand_date(self.start_date, self.end_date),
            })

        # --- treasury_accounts ---
        self.add("treasury_accounts", {
            "account_id": self.ids.next("treasury_accounts"),
            "subsidiary_id": None, "bank_name": "بانک مرکزی گروه",
            "iban": iban_ir(), "currency": "IRR",
            "balance_rial": random.randint(1000, 50000) * 10_000_000,
        })
        for sub in self.db["holding_subsidiaries"]:
            self.add("treasury_accounts", {
                "account_id": self.ids.next("treasury_accounts"),
                "subsidiary_id": sub["subsidiary_id"],
                "bank_name": pick(["بانک ملت", "بانک صادرات", "بانک پاسارگاد"]),
                "iban": iban_ir(), "currency": "IRR",
                "balance_rial": random.randint(100, 8000) * 10_000_000,
            })

        self._sub_ids = sub_ids
        self._emp_by_sub = {}
        for e in self.db["central_employees"]:
            self._emp_by_sub.setdefault(e["subsidiary_id"], []).append(e)

    # -- 3.2 خرده‌فروشی -------------------------------------------------

    def gen_retail(self):
        sid = next(s["subsidiary_id"] for s in self.db["holding_subsidiaries"]
                   if s["industry"] == "retail")

        # store_regions: کشور -> استان -> شهر
        country = self.add("store_regions", {
            "region_id": self.ids.next("store_regions"),
            "parent_region_id": None, "region_name": "ایران", "region_level": 0,
        })
        province_ids = {}
        for city, province in CITIES:
            if province not in province_ids:
                p = self.add("store_regions", {
                    "region_id": self.ids.next("store_regions"),
                    "parent_region_id": country["region_id"],
                    "region_name": province, "region_level": 1,
                })
                province_ids[province] = p["region_id"]
        city_region_ids = []
        for city, province in CITIES:
            c = self.add("store_regions", {
                "region_id": self.ids.next("store_regions"),
                "parent_region_id": province_ids[province],
                "region_name": city, "region_level": 2,
            })
            city_region_ids.append(c["region_id"])

        # stores
        n_stores = self.n(20)
        for i in range(n_stores):
            self.add("stores", {
                "store_id": self.ids.next("stores"),
                "region_id": pick(city_region_ids),
                "store_name": f"فروشگاه آریانا شماره {i+1}",
                "address": self.fk.address(),
                "store_format": weighted_status(
                    [("hypermarket", 15), ("mini", 60), ("kiosk", 25)]
                ),
                "manager_emp_id": pick(self._emp_by_sub[sid])["emp_id"],
                "opened_date": rand_date(date(2010, 1, 1), self.end_date),
            })

        # product_categories (دو سطح)
        cat_ids = []
        for top, subs in RETAIL_CATEGORY_TREE.items():
            top_row = self.add("product_categories", {
                "category_id": self.ids.next("product_categories"),
                "parent_category_id": None, "category_name_fa": top,
            })
            for s in subs:
                row = self.add("product_categories", {
                    "category_id": self.ids.next("product_categories"),
                    "parent_category_id": top_row["category_id"],
                    "category_name_fa": s,
                })
                cat_ids.append(row["category_id"])

        # suppliers_retail
        for _ in range(40):
            self.add("suppliers_retail", {
                "supplier_id": self.ids.next("suppliers_retail"),
                "company_name": self.fk.company(),
                "tax_id": "".join(random.choice(string.digits) for _ in range(11)),
                "rating": round(random.uniform(2.5, 5.0), 1),
            })

        # products_retail
        n_products = self.n(300)
        for i in range(n_products):
            price = random.randint(50, 5000) * 1000
            self.add("products_retail", {
                "sku": f"SKU-{i+1:06d}",
                "category_id": pick(cat_ids),
                "supplier_id": self.any_pk("suppliers_retail"),
                "product_name": f"کالای {i+1}",
                "unit": pick(["pcs", "kg", "ltr"]),
                "current_price_rial": price,
            })

        # product_price_history (SCD)
        for p in self.db["products_retail"]:
            price = p["current_price_rial"]
            cur_from = rand_date(date(2022, 1, 1), date(2023, 6, 1))
            for i in range(random.randint(1, 3)):
                cur_to = None if i == 2 else rand_date(cur_from, self.end_date)
                self.add("product_price_history", {
                    "price_id": self.ids.next("product_price_history"),
                    "sku": p["sku"],
                    "price_rial": price,
                    "effective_from": cur_from,
                    "effective_to": cur_to,
                })
                price = int(price * random.uniform(1.05, 1.4))
                if cur_to:
                    cur_from = cur_to

        # inventory_stock (هر فروشگاه زیرمجموعه‌ای از کالاها را دارد)
        for store in self.db["stores"]:
            for p in random.sample(self.db["products_retail"],
                                    k=max(1, int(len(self.db["products_retail"]) * 0.5))):
                self.add("inventory_stock", {
                    "stock_id": self.ids.next("inventory_stock"),
                    "store_id": store["store_id"],
                    "sku": p["sku"],
                    "quantity_on_hand": random.randint(0, 500),
                    "reorder_level": random.randint(10, 50),
                    "last_counted_at": rand_datetime(self.start_date, self.end_date),
                })

        # customers_loyalty
        for _ in range(self.n(2000)):
            self.add("customers_loyalty", {
                "customer_id": self.ids.next("customers_loyalty"),
                "full_name": self.fk.name(),
                "phone": dirty_phone(self.dirty),
                "loyalty_tier": weighted_status(
                    [("bronze", 55), ("silver", 30), ("gold", 15)]
                ),
                "joined_date": rand_date(date(2018, 1, 1), self.end_date),
            })

        # promotions
        for _ in range(50):
            start = rand_date(self.start_date, self.end_date)
            self.add("promotions", {
                "promo_id": self.ids.next("promotions"),
                "promo_name": pick(["حراج فصلی", "تخفیف عید", "شب یلدا",
                                     "بلک فرایدی", "پیش‌خرید"]),
                "discount_percent": random.choice([5, 10, 15, 20, 30]),
                "start_date": start,
                "end_date": start + timedelta(days=random.randint(3, 20)),
            })

        # pos_transactions + items
        for _ in range(self.n(5000)):
            store = pick(self.db["stores"])
            customer = pick(self.db["customers_loyalty"]) if chance(0.7) else None
            txn = self.add("pos_transactions", {
                "transaction_id": self.ids.next("pos_transactions"),
                "store_id": store["store_id"],
                "customer_id": customer["customer_id"] if customer else None,
                "transaction_ts": rand_datetime(self.start_date, self.end_date),
                "total_amount_rial": 0,
                "payment_method": weighted_status(
                    [("cash", 35), ("card", 55), ("online", 10)]
                ),
            })
            total = 0
            for _ in range(random.randint(1, 5)):
                p = pick(self.db["products_retail"])
                qty = random.randint(1, 4)
                unit_price = dirty_amount(p["current_price_rial"], self.dirty * 0.2)
                promo = pick(self.db["promotions"]) if chance(0.15) else None
                self.add("pos_transaction_items", {
                    "item_id": self.ids.next("pos_transaction_items"),
                    "transaction_id": txn["transaction_id"],
                    "sku": p["sku"],
                    "promo_id": promo["promo_id"] if promo else None,
                    "quantity": qty,
                    "unit_price_rial": unit_price,
                })
                total += qty * unit_price
            txn["total_amount_rial"] = total

    # -- 3.3 لجستیک -------------------------------------------------------

    def gen_logistics(self):
        sid = next(s["subsidiary_id"] for s in self.db["holding_subsidiaries"]
                   if s["industry"] == "logistics")

        for city, _ in CITIES[:10]:
            self.add("warehouses", {
                "warehouse_id": self.ids.next("warehouses"),
                "city": city,
                "capacity_sqm": random.randint(500, 8000),
            })

        for i in range(40):
            self.add("fleet_vehicles", {
                "vehicle_id": self.ids.next("fleet_vehicles"),
                "plate_number": f"{random.randint(10,99)} ایران {random.randint(100,999)} - {random.randint(10,99)}",
                "vehicle_type": pick(["van", "truck", "motor"]),
                "capacity_kg": random.choice([200, 1000, 5000, 12000]),
                "status": weighted_status(
                    [("active", 80), ("maintenance", 15), ("retired", 5)]
                ),
            })

        drivers_pool = self._emp_by_sub.get(sid, [])
        for emp in random.sample(drivers_pool, k=min(40, len(drivers_pool))):
            self.add("drivers", {
                "driver_id": self.ids.next("drivers"),
                "emp_id": emp["emp_id"],
                "license_type": pick(["پایه یک", "پایه دو", "موتورسیکلت"]),
                "license_expiry": rand_date(self.end_date, date(2029, 1, 1)),
            })

        cities_list = [c for c, _ in CITIES]
        for _ in range(25):
            o, d = random.sample(cities_list, 2)
            self.add("routes", {
                "route_id": self.ids.next("routes"),
                "origin_city": o, "dest_city": d,
                "distance_km": round(random.uniform(50, 1400), 1),
            })

        for _ in range(self.n(3000)):
            scheduled = rand_datetime(self.start_date, self.end_date)
            status = weighted_status(
                [("delivered", 70), ("in_transit", 15), ("pending", 10), ("delayed", 5)]
            )
            shp = self.add("shipments", {
                "shipment_id": self.ids.next("shipments"),
                "origin_warehouse_id": self.any_pk("warehouses"),
                "dest_warehouse_id": self.any_pk("warehouses"),
                "vehicle_id": self.any_pk("fleet_vehicles"),
                "driver_id": self.any_pk("drivers"),
                "route_id": self.any_pk("routes"),
                "requested_by_subsidiary_id": pick(self._sub_ids),
                "status": status,
                "scheduled_at": scheduled,
                "delivered_at": scheduled + timedelta(hours=random.randint(2, 72))
                if status == "delivered" else None,
            })
            for _ in range(random.randint(1, 3)):
                self.add("shipment_items", {
                    "item_id": self.ids.next("shipment_items"),
                    "shipment_id": shp["shipment_id"],
                    "description": pick(["پالت کالا", "کارتن مرسوله", "بسته سفارش"]),
                    "weight_kg": round(random.uniform(5, 800), 1),
                    "qty": random.randint(1, 20),
                })
            for ev in ["picked_up", "in_transit", "customs", "out_for_delivery"][
                : random.randint(2, 4)
            ]:
                self.add("shipment_events", {
                    "event_id": self.ids.next("shipment_events"),
                    "shipment_id": shp["shipment_id"],
                    "event_type": ev,
                    "event_ts": scheduled + timedelta(hours=random.randint(0, 60)),
                    "location": pick(cities_list),
                })

        for v in self.db["fleet_vehicles"]:
            for _ in range(self.n(6)):
                self.add("fuel_logs", {
                    "log_id": self.ids.next("fuel_logs"),
                    "vehicle_id": v["vehicle_id"],
                    "liters": round(random.uniform(20, 300), 1),
                    "cost_rial": random.randint(2, 40) * 1_000_000,
                    "logged_at": rand_date(self.start_date, self.end_date),
                })

    # -- 3.4 دیجیتال / تجارت الکترونیک ------------------------------------

    def gen_digital(self):
        for _ in range(self.n(4000)):
            self.add("online_customers", {
                "customer_id": self.ids.next("online_customers"),
                "email": maybe_none(self.fk.email(), self.dirty),
                "phone": dirty_phone(self.dirty),
                "signup_date": rand_date(date(2019, 1, 1), self.end_date),
                "city": pick([c for c, _ in CITIES]),
            })

        for _ in range(80):
            self.add("sellers_marketplace", {
                "seller_id": self.ids.next("sellers_marketplace"),
                "store_display_name": self.fk.company(),
                "commission_rate": round(random.uniform(5, 20), 1),
                "joined_date": rand_date(date(2020, 1, 1), self.end_date),
                "is_verified": chance(0.8),
            })

        for i in range(self.n(500)):
            self.add("product_catalog_digital", {
                "listing_id": self.ids.next("product_catalog_digital"),
                "seller_id": self.any_pk("sellers_marketplace"),
                "title": f"کالای آنلاین {i+1}",
                "price_rial": random.randint(80, 8000) * 1000,
                "stock_qty": random.randint(0, 300),
            })

        for _ in range(self.n(6000)):
            cust = pick(self.db["online_customers"])
            order = self.add("online_orders", {
                "order_id": self.ids.next("online_orders"),
                "customer_id": cust["customer_id"],
                "order_ts": rand_datetime(self.start_date, self.end_date),
                "order_status": weighted_status(
                    [("placed", 10), ("shipped", 25), ("delivered", 55),
                     ("returned", 5), ("cancelled", 5)]
                ),
                "total_amount_rial": 0,
            })
            total = 0
            for _ in range(random.randint(1, 4)):
                listing = pick(self.db["product_catalog_digital"])
                qty = random.randint(1, 3)
                self.add("order_items", {
                    "order_item_id": self.ids.next("order_items"),
                    "order_id": order["order_id"],
                    "listing_id": listing["listing_id"],
                    "quantity": qty,
                    "unit_price_rial": listing["price_rial"],
                })
                total += qty * listing["price_rial"]
            order["total_amount_rial"] = total
            self.add("payments_online", {
                "payment_id": self.ids.next("payments_online"),
                "order_id": order["order_id"],
                "gateway": pick(["زرین‌پال", "به‌پرداخت ملت", "آی‌دی‌پی"]),
                "status": weighted_status(
                    [("success", 85), ("failed", 10), ("refunded", 5)]
                ),
            })

        for _ in range(self.n(2000)):
            cust = pick(self.db["online_customers"])
            listing = pick(self.db["product_catalog_digital"])
            added = rand_datetime(self.start_date, self.end_date)
            self.add("carts_abandoned", {
                "cart_id": self.ids.next("carts_abandoned"),
                "customer_id": cust["customer_id"],
                "listing_id": listing["listing_id"],
                "added_at": added,
                "abandoned_at": added + timedelta(minutes=random.randint(5, 240)),
            })

        for item in random.sample(self.db["order_items"],
                                   k=max(1, int(len(self.db["order_items"]) * 0.3))):
            self.add("reviews_ratings", {
                "review_id": self.ids.next("reviews_ratings"),
                "listing_id": item["listing_id"],
                "customer_id": self.any_pk("online_customers"),
                "rating": random.randint(1, 5),
                "comment": pick(["عالی بود", "کیفیت متوسط", "ارسال سریع",
                                  "مطابق توضیحات نبود", "پیشنهاد می‌کنم"]),
            })

        for _ in range(self.n(8000)):
            cust = pick(self.db["online_customers"]) if chance(0.6) else None
            self.add("website_sessions", {
                "session_id": self.ids.next("website_sessions"),
                "customer_id": cust["customer_id"] if cust else None,
                "device_type": weighted_status(
                    [("mobile", 65), ("desktop", 30), ("tablet", 5)]
                ),
                "utm_source": pick(["instagram", "google", "direct", "email", None]),
                "started_at": rand_datetime(self.start_date, self.end_date),
                "page_views": random.randint(1, 25),
            })

    # -- 3.5 تولید ---------------------------------------------------------

    def gen_manufacturing(self):
        for f in self.db["factories"]:
            for i in range(4):
                self.add("production_lines", {
                    "line_id": self.ids.next("production_lines"),
                    "factory_id": f["factory_id"],
                    "line_name": f"خط تولید {i+1}",
                    "capacity_units_per_day": random.randint(200, 3000),
                })

        for _ in range(25):
            self.add("suppliers_manufacturing", {
                "supplier_id": self.ids.next("suppliers_manufacturing"),
                "company_name": self.fk.company(),
                "lead_time_days": random.randint(3, 45),
            })

        for m in MFG_MATERIALS * 8:
            self.add("raw_materials", {
                "material_id": self.ids.next("raw_materials"),
                "supplier_id": self.any_pk("suppliers_manufacturing"),
                "material_name": m,
                "unit": pick(["kg", "ton", "m", "pcs"]),
                "unit_cost_rial": random.randint(50, 5000) * 1000,
            })

        for p in MFG_PRODUCTS * 7:
            self.add("finished_products_mfg", {
                "product_id": self.ids.next("finished_products_mfg"),
                "product_name": p,
                "unit_price_rial": random.randint(500, 50000) * 1000,
            })

        for prod in self.db["finished_products_mfg"]:
            for mat in random.sample(self.db["raw_materials"],
                                      k=min(4, len(self.db["raw_materials"]))):
                self.add("bill_of_materials", {
                    "bom_id": self.ids.next("bill_of_materials"),
                    "product_id": prod["product_id"],
                    "material_id": mat["material_id"],
                    "quantity_required": round(random.uniform(0.1, 25), 2),
                })

        for _ in range(self.n(1500)):
            start = rand_datetime(self.start_date, self.end_date)
            status = weighted_status(
                [("completed", 70), ("in_progress", 20), ("planned", 10)]
            )
            wo = self.add("work_orders", {
                "work_order_id": self.ids.next("work_orders"),
                "line_id": self.any_pk("production_lines"),
                "product_id": self.any_pk("finished_products_mfg"),
                "planned_qty": random.randint(100, 5000),
                "status": status,
                "start_ts": start,
                "end_ts": start + timedelta(hours=random.randint(4, 96))
                if status == "completed" else None,
            })
            if status != "planned":
                produced = int(wo["planned_qty"] * random.uniform(0.85, 1.0))
                batch = self.add("production_batches", {
                    "batch_id": self.ids.next("production_batches"),
                    "work_order_id": wo["work_order_id"],
                    "produced_qty": produced,
                    "scrap_qty": wo["planned_qty"] - produced,
                })
                for _ in range(random.randint(1, 2)):
                    self.add("quality_checks", {
                        "check_id": self.ids.next("quality_checks"),
                        "batch_id": batch["batch_id"],
                        "result": weighted_status([("pass", 90), ("fail", 10)]),
                        "defect_type": pick(
                            [None, "ترک سطحی", "عدم تطابق ابعاد", "رنگ ناهماهنگ"]
                        ),
                    })

        for line in self.db["production_lines"]:
            for _ in range(self.n(6)):
                self.add("machine_maintenance_logs", {
                    "log_id": self.ids.next("machine_maintenance_logs"),
                    "line_id": line["line_id"],
                    "maintenance_type": pick(["پیشگیرانه", "اضطراری", "دوره‌ای"]),
                    "cost_rial": random.randint(5, 200) * 1_000_000,
                    "logged_at": rand_date(self.start_date, self.end_date),
                })

    # -- 3.6 مالی -----------------------------------------------------------

    def gen_finance(self):
        n_loans = self.n(120)
        for _ in range(n_loans):
            principal = random.randint(500, 50000) * 1_000_000
            issue = rand_date(self.start_date, self.end_date)
            loan = self.add("loan_contracts", {
                "loan_id": self.ids.next("loan_contracts"),
                "borrower_subsidiary_id": pick(self._sub_ids) if chance(0.6) else None,
                "principal_rial": principal,
                "interest_rate": round(random.uniform(12, 24), 1),
                "issue_date": issue,
                "term_months": pick([12, 24, 36, 60]),
                "status": weighted_status(
                    [("active", 60), ("closed", 30), ("defaulted", 10)]
                ),
            })
            n_inst = loan["term_months"]
            monthly = principal / n_inst
            for i in range(n_inst):
                due = issue + timedelta(days=30 * (i + 1))
                self.add("installment_schedule", {
                    "installment_id": self.ids.next("installment_schedule"),
                    "loan_id": loan["loan_id"],
                    "lease_id": None,
                    "due_date": due,
                    "amount_rial": round(monthly),
                    "paid_status": weighted_status(
                        [("paid", 70), ("pending", 20), ("overdue", 10)]
                    ),
                })
            if chance(0.7):
                self.add("collateral_assets", {
                    "collateral_id": self.ids.next("collateral_assets"),
                    "loan_id": loan["loan_id"],
                    "asset_type": pick(["ملک", "خودرو", "سفته", "سهام"]),
                    "value_rial": round(principal * random.uniform(1.1, 1.8)),
                })
            for _ in range(random.randint(1, 2)):
                self.add("credit_risk_assessment", {
                    "assessment_id": self.ids.next("credit_risk_assessment"),
                    "loan_id": loan["loan_id"],
                    "risk_score": random.randint(300, 850),
                    "risk_band": pick(["A", "B", "C", "D"]),
                    "assessed_at": rand_date(issue, self.end_date),
                })

        n_leases = self.n(80)
        for _ in range(n_leases):
            issue = rand_date(self.start_date, self.end_date)
            monthly = random.randint(20, 800) * 1_000_000
            lease = self.add("lease_contracts", {
                "lease_id": self.ids.next("lease_contracts"),
                "lessee_subsidiary_id": pick(self._sub_ids),
                "asset_description": pick(
                    ["دستگاه CNC", "کامیون سنگین", "خط بسته‌بندی", "سرور و تجهیزات IT"]
                ),
                "monthly_rial": monthly,
            })
            for i in range(random.randint(12, 36)):
                due = issue + timedelta(days=30 * (i + 1))
                self.add("installment_schedule", {
                    "installment_id": self.ids.next("installment_schedule"),
                    "loan_id": None,
                    "lease_id": lease["lease_id"],
                    "due_date": due,
                    "amount_rial": monthly,
                    "paid_status": weighted_status(
                        [("paid", 75), ("pending", 15), ("overdue", 10)]
                    ),
                })

    # -- 3.7 املاک و ساختمان -------------------------------------------------

    def gen_realestate(self):
        for _ in range(30):
            self.add("contractors", {
                "contractor_id": self.ids.next("contractors"),
                "company_name": self.fk.company(),
            })

        for i in range(15):
            status = weighted_status(
                [("completed", 30), ("in_progress", 45), ("planning", 15), ("delayed", 10)]
            )
            proj = self.add("construction_projects", {
                "project_id": self.ids.next("construction_projects"),
                "project_name": f"پروژه آریانا {i+1}",
                "city": pick([c for c, _ in CITIES]),
                "status": status,
                "start_date": rand_date(date(2018, 1, 1), self.end_date),
                "expected_end_date": None,
            })
            proj["expected_end_date"] = proj["start_date"] + timedelta(
                days=random.randint(365, 1500)
            )

            for _ in range(random.randint(6, 8)):
                self.add("project_budget_lines", {
                    "budget_line_id": self.ids.next("project_budget_lines"),
                    "project_id": proj["project_id"],
                    "contractor_id": self.any_pk("contractors"),
                    "category": pick(["مصالح", "دستمزد", "تجهیزات", "طراحی"]),
                    "budgeted_rial": random.randint(500, 50000) * 1_000_000,
                    "actual_spent_rial": random.randint(400, 55000) * 1_000_000,
                })

            n_units = random.randint(20, 60)
            for u in range(n_units):
                sale_status = weighted_status(
                    [("sold", 50), ("reserved", 15), ("available", 35)]
                )
                unit = self.add("building_units", {
                    "unit_id": self.ids.next("building_units"),
                    "project_id": proj["project_id"],
                    "unit_type": pick(["۱ خوابه", "۲ خوابه", "۳ خوابه", "پنت‌هاوس"]),
                    "area_sqm": round(random.uniform(65, 240), 1),
                    "floor": random.randint(1, 20),
                    "listed_price_rial": random.randint(3, 60) * 1_000_000_000,
                    "sale_status": sale_status,
                })
                if sale_status in ("sold", "reserved"):
                    contract = self.add("unit_sales_contracts", {
                        "contract_id": self.ids.next("unit_sales_contracts"),
                        "unit_id": unit["unit_id"],
                        "buyer_name": self.fk.name(),
                        "buyer_national_id": national_id(),
                        "final_price_rial": round(
                            unit["listed_price_rial"] * random.uniform(0.92, 1.0)
                        ),
                        "contract_date": rand_date(proj["start_date"], self.end_date),
                    })
                    n_inst = random.randint(12, 36)
                    monthly = contract["final_price_rial"] / n_inst
                    for i in range(n_inst):
                        due = contract["contract_date"] + timedelta(days=30 * (i + 1))
                        self.add("installment_payments_realestate", {
                            "payment_id": self.ids.next("installment_payments_realestate"),
                            "contract_id": contract["contract_id"],
                            "due_date": due,
                            "amount_rial": round(monthly),
                            "paid_status": weighted_status(
                                [("paid", 65), ("pending", 20), ("overdue", 15)]
                            ),
                        })

    # -- 3.x اصلاح factories (اضافه شدن قبل از production_lines) ------------

    def gen_factories_placeholder(self):
        """factories باید پیش از production_lines ساخته شود؛ اینجا به‌صورت
        مجزا فراخوانی می‌شود تا کد gen_manufacturing ساده بماند."""
        for city in ["اصفهان", "تبریز", "کرج"]:
            self.add("factories", {
                "factory_id": self.ids.next("factories"),
                "city": city,
            })

    # -- اجرای کامل -----------------------------------------------------

    def run(self):
        self.gen_shared()
        self.gen_retail()
        self.gen_logistics()
        self.gen_digital()
        self.gen_factories_placeholder()
        self.gen_manufacturing()
        self.gen_finance()
        self.gen_realestate()
        return self.db


# --------------------------------------------------------------------------
# 4) نوشتن خروجی
# --------------------------------------------------------------------------

def infer_sql_type(col_name, sample_value):
    lc = col_name.lower()
    if lc.endswith("_id") or lc in ("floor", "quantity", "qty", "page_views"):
        return "INTEGER"
    if any(k in lc for k in ("rial", "amount", "price", "percent", "rate",
                              "balance", "score", "area_sqm", "distance_km",
                              "capacity", "weight_kg", "liters")):
        return "REAL"
    if isinstance(sample_value, bool):
        return "INTEGER"
    if isinstance(sample_value, int):
        return "INTEGER"
    if isinstance(sample_value, float):
        return "REAL"
    return "TEXT"


def stringify(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


def write_csv(db, out_dir):
    csv_dir = os.path.join(out_dir, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    for table, rows in db.items():
        if not rows:
            continue
        path = os.path.join(csv_dir, f"{table}.csv")
        cols = list(rows[0].keys())
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for row in rows:
                w.writerow({k: stringify(v) for k, v in row.items()})
    print(f"[csv] {len(db)} جدول در {csv_dir} نوشته شد.")


def write_sqlite(db, out_dir):
    db_path = os.path.join(out_dir, "ariana.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for table, rows in db.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        pk_col = cols[0]
        col_defs = []
        for c in cols:
            sample = next((r[c] for r in rows if r.get(c) is not None), None)
            typ = infer_sql_type(c, sample)
            suffix = " PRIMARY KEY" if c == pk_col else ""
            col_defs.append(f'"{c}" {typ}{suffix}')
        ddl = f'CREATE TABLE "{table}" ({", ".join(col_defs)});'
        cur.execute(ddl)
        placeholders = ", ".join(["?"] * len(cols))
        insert_sql = f'INSERT INTO "{table}" ({", ".join(cols)}) VALUES ({placeholders})'
        cur.executemany(
            insert_sql,
            [tuple(stringify(r.get(c)) for c in cols) for r in rows],
        )
    conn.commit()
    conn.close()
    print(f"[sqlite] پایگاه‌داده در {db_path} ساخته شد.")


# --------------------------------------------------------------------------
# 5) CLI
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="تولید داده فیک برای هلدینگ آریانا (تست Text-to-SQL)"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scale", choices=list(SCALE_PRESETS), default="small")
    parser.add_argument("--dirty-rate", type=float, default=0.05)
    parser.add_argument("--out-dir", default="./ariana_fake_data")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--csv", dest="csv", action="store_true", default=True)
    parser.add_argument("--no-csv", dest="csv", action="store_false")
    parser.add_argument("--sqlite", action="store_true", default=False)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    gen = AriannaDataGenerator(
        seed=args.seed,
        scale=args.scale,
        dirty_rate=args.dirty_rate,
        start_year=args.start_year,
        end_year=args.end_year,
    )
    db = gen.run()

    print("خلاصه‌ی تعداد رکورد هر جدول:")
    for table in sorted(db):
        print(f"  {table:38s} {len(db[table]):>8,d}")

    if args.csv:
        write_csv(db, args.out_dir)
    if args.sqlite:
        write_sqlite(db, args.out_dir)


if __name__ == "__main__":
    main()
