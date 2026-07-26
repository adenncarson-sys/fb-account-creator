#!/usr/bin/env python3
"""
Random account profile generator using Faker.
"""

from faker import Faker
import random
import string
from typing import Dict


class AccountProfile:
    """Holds a single generated account profile."""

    def __init__(self, first_name: str, last_name: str, email: str,
                 password: str, gender: str, dob_day: str, dob_month: str,
                 dob_year: str, custom_email: str = ""):
        self.first_name = first_name
        self.last_name = last_name
        self.email = email if not custom_email else custom_email
        self.password = password
        self.gender = gender
        self.dob_day = dob_day
        self.dob_month = dob_month
        self.dob_year = dob_year

    def to_dict(self) -> Dict[str, str]:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "password": self.password,
            "gender": self.gender,
            "dob": f"{self.dob_year}-{self.dob_month.zfill(2)}-{self.dob_day.zfill(2)}",
        }

    def __repr__(self):
        return (f"Account({self.first_name} {self.last_name}, "
                f"{self.email}, {self.gender})")


class ProfileGenerator:
    """Generates randomized Facebook account profiles."""

    MONTHS = {
        "Jan": "1", "Feb": "2", "Mar": "3", "Apr": "4",
        "May": "5", "Jun": "6", "Jul": "7", "Aug": "8",
        "Sep": "9", "Oct": "10", "Nov": "11", "Dec": "12"
    }

    def __init__(self, locale: str = "en_US", min_age: int = 18, max_age: int = 65):
        self.fake = Faker(locale)
        self.min_age = min_age
        self.max_age = max_age

    @staticmethod
    def random_password(length: int = 14) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(random.choice(chars) for _ in range(length))

    def random_gender(self) -> str:
        """2 = male, 1 = female (Facebook's gender values)."""
        return random.choice(["1", "2"])

    def generate(self, email: str = "", password: str = "",
                 gender: str = "", custom_email: str = "") -> AccountProfile:
        """Generate a random profile, overriding fields when supplied."""
        first = self.fake.first_name()
        last = self.fake.last_name()

        dob = self.fake.date_of_birth(
            minimum_age=self.min_age, maximum_age=self.max_age
        )
        dob_day = str(dob.day)
        dob_month = self.MONTHS[self.fake.month_name()]
        dob_year = str(dob.year)

        if gender.lower() in ("1", "2"):
            final_gender = gender
        elif gender.lower() in ("male", "m"):
            final_gender = "2"
        elif gender.lower() in ("female", "f"):
            final_gender = "1"
        else:
            final_gender = self.random_gender()

        final_pass = password if password else self.random_password()

        return AccountProfile(
            first_name=first,
            last_name=last,
            email=email,
            password=final_pass,
            gender=final_gender,
            dob_day=dob_day,
            dob_month=dob_month,
            dob_year=dob_year,
            custom_email=custom_email,
        )
