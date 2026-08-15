// Indian-format currency/number helpers. MSME users read amounts in lakhs,
// so large values render as "Rs 4.8L" rather than "Rs 480,000".

export function formatLakhs(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  if (abs >= 10000000) return `${sign}₹${(abs / 10000000).toFixed(2)}Cr`;
  if (abs >= 100000) return `${sign}₹${(abs / 100000).toFixed(1)}L`;
  return `${sign}₹${abs.toLocaleString("en-IN")}`;
}

export function formatFullCurrency(amount: number): string {
  return `₹${amount.toLocaleString("en-IN")}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
