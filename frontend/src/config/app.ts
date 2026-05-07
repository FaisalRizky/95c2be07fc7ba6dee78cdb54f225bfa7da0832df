/**
 * config.ts
 *
 * Centralized application configuration.
 */
app.constant("APP_CONFIG", {
  // Relative URL — nginx proxies /api/ → backend on the internal Docker network.
  // No hostname or port needed in the browser bundle; works regardless of which
  // host port the frontend container is mapped to.
  API_BASE_URL: "/api/v1",
  DEFAULT_PER_PAGE: 20,
  CURRENCY_CODE: "GBP",
});
