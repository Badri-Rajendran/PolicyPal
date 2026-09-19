// The API sends money as exact decimal strings ("620.15"). They are only
// formatted here, never added up, so Number() cannot cost a cent.
const WITH_CENTS = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const WHOLE = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function formatMoney(amount, { cents = false } = {}) {
  if (amount === null || amount === undefined) return null;
  return (cents ? WITH_CENTS : WHOLE).format(Number(amount));
}
