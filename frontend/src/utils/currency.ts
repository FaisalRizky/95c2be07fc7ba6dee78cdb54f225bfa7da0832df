/**
 * utils/currency.ts
 *
 * Custom AngularJS filter that formats a numeric value based on the configured currency.
 */

app.filter("formatCurrency", ["APP_CONFIG", function (APP_CONFIG: any) {
  return function (value: number | null | undefined, currencyOverride?: string): string {
    if (value === null || value === undefined) return "—";
    
    const currencyCode = (currencyOverride || APP_CONFIG.CURRENCY_CODE || "GBP").toUpperCase();
    
    let symbol = "£";
    let locale = "en-GB";

    switch (currencyCode) {
      case "USD":
        symbol = "$";
        locale = "en-US";
        break;
      case "EUR":
        symbol = "€";
        locale = "en-IE";
        break;
      case "GBP":
      default:
        symbol = "£";
        locale = "en-GB";
        break;
    }

    return (
      symbol +
      Math.round(value).toLocaleString(locale, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      })
    );
  };
}]);
