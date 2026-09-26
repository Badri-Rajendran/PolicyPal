import { Info, MapPin } from "lucide-react";
import TextField from "../../components/TextField";
import { todayIso } from "../../utils/age";
import { exchangeFor } from "../plans/exchanges";

export default function ProfileFields({ fields, errors }) {
  const { values, lookup, setZipCode, setField } = fields;
  const [onlyCounty] = lookup.counties;

  return (
    <fieldset className="profile-fields">
      <legend>For comparing plans</legend>
      <TextField
        id="zip-code"
        label="ZIP code"
        inputMode="numeric"
        autoComplete="postal-code"
        maxLength={5}
        value={values.zipCode}
        onChange={(e) => setZipCode(e.target.value.trim())}
        error={errors.zip_code || (lookup.status === "not-found" ? "We don't recognise this ZIP code." : "")}
      />
      {lookup.status === "loading" && <p className="field-hint" role="status">Finding your county…</p>}
      {lookup.status === "error" && (
        <p className="field-hint">Couldn't look up this ZIP code right now. You can still continue.</p>
      )}
      {lookup.counties.length === 1 && (
        <p className="field-hint county-found">
          <MapPin className="i sm" aria-hidden="true" />
          <span>
            {onlyCounty.county_name} County, {onlyCounty.state}
          </span>
        </p>
      )}
      {lookup.counties.length > 1 && (
        <div className="field">
          <label htmlFor="county">County</label>
          <select
            id="county"
            value={values.countyFips}
            onChange={(e) => setField("countyFips", e.target.value)}
            aria-invalid={Boolean(errors.county_fips)}
            aria-describedby={errors.county_fips ? "county-error" : undefined}
          >
            <option value="">This ZIP code spans counties — choose yours</option>
            {lookup.counties.map((county) => (
              <option key={county.county_fips} value={county.county_fips}>
                {county.county_name} County, {county.state}
              </option>
            ))}
          </select>
          {errors.county_fips && (
            <p className="field-error" id="county-error">
              {errors.county_fips}
            </p>
          )}
        </div>
      )}
      {lookup.status === "ready" && lookup.marketplaceState && exchangeFor(onlyCounty?.state).filedRates && (
        <p className="field-note">
          <Info className="i sm" aria-hidden="true" />
          <span>
            Plans in {onlyCounty.state} are sold on {exchangeFor(onlyCounty.state).name}. PolicyPal compares them from
            CMS's published plan data.
          </span>
        </p>
      )}
      {lookup.status === "ready" && !lookup.marketplaceState && (
        <p className="field-note">
          <Info className="i sm" aria-hidden="true" />
          <span>
            Your state runs its own health insurance exchange, so plan comparison isn't available there. You can still
            ask any insurance question.
          </span>
        </p>
      )}
      <TextField
        id="date-of-birth"
        label="Date of birth"
        type="date"
        autoComplete="bday"
        max={todayIso()}
        value={values.dateOfBirth}
        onChange={(e) => setField("dateOfBirth", e.target.value)}
        error={errors.date_of_birth}
        hint="Used to work out your age for prices. Never shown to the AI model."
      />
    </fieldset>
  );
}
