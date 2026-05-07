/**
 * routes/index.ts
 *
 * Centralized JSON-based routing configuration.
 */

interface AppRoute {
  path: string;
  component?: string;
  templateUrl?: string;
  controller?: string;
  controllerAs?: string;
  redirectTo?: string;
  reloadOnSearch?: boolean;
}

const APP_ROUTES: AppRoute[] = [
  {
    path: "/",
    templateUrl: "/templates/projects-dashboard.html",
    controller: "ProjectsDashboardController",
    controllerAs: "$ctrl",
    reloadOnSearch: false
  },
  /* 
   * Example of a legacy route definition:
   * {
   *   path: "/legacy",
   *   templateUrl: "templates/legacy.html",
   *   controller: "LegacyController",
   *   controllerAs: "$ctrl"
   * }
   */
];
