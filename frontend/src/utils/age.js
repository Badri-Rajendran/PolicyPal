// Mirrors src/services/profile.py. The server's check is the one that counts;
// this one answers before a request is sent.
export const MIN_SIGNUP_AGE = 13;
const MAX_AGE = 120;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

function parts(isoDate) {
  const match = ISO_DATE.exec(isoDate);
  return match ? match.slice(1).map(Number) : null;
}

export function todayIso(now = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function ageOn(dateOfBirth, on) {
  const [by, bm, bd] = parts(dateOfBirth);
  const [y, m, d] = parts(on);
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0);
}

export function dateOfBirthError(dateOfBirth, today = todayIso()) {
  if (!parts(dateOfBirth)) return "Enter your date of birth.";
  if (dateOfBirth > today) return "Date of birth can't be in the future.";
  const age = ageOn(dateOfBirth, today);
  if (age < MIN_SIGNUP_AGE) return `You must be at least ${MIN_SIGNUP_AGE} to use PolicyPal.`;
  if (age > MAX_AGE) return "Enter a real date of birth.";
  return "";
}
