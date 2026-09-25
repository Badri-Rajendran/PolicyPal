from datetime import date

from pydantic import BaseModel, Field


class ProfileFields(BaseModel):
    zip_code: str = Field(pattern=r"^[0-9]{5}$")
    # A `date`, so an impossible one (2010-02-30) fails here; the age rules
    # are in services.profile, which knows what "today" means.
    date_of_birth: date
    # Required only when the ZIP code spans several counties.
    county_fips: str | None = Field(default=None, pattern=r"^[0-9]{5}$")


class ProfileUpdateRequest(ProfileFields):
    pass


class ProfileResponse(BaseModel):
    zip_code: str | None
    date_of_birth: date | None
    county_fips: str | None
    county_name: str | None
    state: str | None
    # Whether plan comparison is available: a HealthCare.gov state or a filed-rate one
    # (California). The name predates California and is kept for the frontend.
    marketplace_state: bool


class CountyResponse(BaseModel):
    county_fips: str
    county_name: str
    state: str


class CountiesResponse(BaseModel):
    counties: list[CountyResponse]
    marketplace_state: bool
