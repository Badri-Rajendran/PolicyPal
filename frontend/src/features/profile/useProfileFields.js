import { useRef, useState } from "react";
import { lookupCounties } from "../../services/profileService";
import { dateOfBirthError } from "../../utils/age";

const ZIP_CODE = /^\d{5}$/;
const IDLE = { status: "idle", counties: [], marketplaceState: true };
const LOADING = { ...IDLE, status: "loading" };

// The shape a lookup is kept in, from the API's answer.
export function lookupFrom(data) {
  return { status: "ready", counties: data.counties, marketplaceState: data.marketplace_state };
}

function fromProfile(profile) {
  return {
    zipCode: profile?.zip_code ?? "",
    dateOfBirth: profile?.date_of_birth ?? "",
    countyFips: profile?.county_fips ?? "",
  };
}

// `counties` is the saved ZIP code's lookup, fetched with the profile, so a
// ZIP code spanning counties shows its choice from the first render.
export function useProfileFields(profile, counties = IDLE) {
  const [values, setValues] = useState(() => fromProfile(profile));
  const [lookup, setLookup] = useState(counties);
  const latestZip = useRef("");

  // An answer for a ZIP code the user has since changed is dropped.
  function fetchCounties(zipCode) {
    latestZip.current = zipCode;
    return lookupCounties(zipCode).then(
      (data) => {
        if (latestZip.current !== zipCode) return;
        setLookup(lookupFrom(data));
        if (data.counties.length === 1) {
          setValues((current) => ({ ...current, countyFips: data.counties[0].county_fips }));
        }
      },
      (err) => {
        if (latestZip.current !== zipCode) return;
        setLookup({ ...IDLE, status: err.status === 404 ? "not-found" : "error" });
      },
    );
  }

  function setZipCode(zipCode) {
    setValues((current) => ({ ...current, zipCode, countyFips: "" }));
    if (ZIP_CODE.test(zipCode)) {
      setLookup(LOADING);
      fetchCounties(zipCode);
    } else {
      latestZip.current = "";
      setLookup(IDLE);
    }
  }

  function setField(name, value) {
    setValues((current) => ({ ...current, [name]: value }));
  }

  function validate() {
    const errors = {};
    if (!ZIP_CODE.test(values.zipCode)) errors.zip_code = "Enter a 5-digit ZIP code.";
    else if (lookup.status === "not-found") errors.zip_code = "We don't recognise this ZIP code.";
    const dobError = dateOfBirthError(values.dateOfBirth);
    if (dobError) errors.date_of_birth = dobError;
    if (lookup.counties.length > 1 && !values.countyFips) errors.county_fips = "Choose your county.";
    return errors;
  }

  const payload = {
    zip_code: values.zipCode,
    date_of_birth: values.dateOfBirth,
    county_fips: values.countyFips || null,
  };

  return { values, lookup, setZipCode, setField, validate, payload };
}
