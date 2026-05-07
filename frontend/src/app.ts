/**
 * app.ts — AngularJS 1.8.x application bootstrap
 *
 * Module declaration. All components, services, and filters are registered
 * here or in their own files (compiled into the same outFile bundle).
 *
 * Design choice: We keep everything in a single compiled bundle (dist/app.js)
 * via TypeScript's --outFile flag. This mirrors the low-complexity build
 * pipeline typical of brownfield AngularJS projects. A Webpack/Rollup setup
 * would be overkill for this assignment but is the obvious next step.
 */

/// <reference path="./routes/index.ts" />

const app = angular.module("gleniganApp", ["ngRoute"]);

app.config(["$routeProvider", "$locationProvider", function($routeProvider: any, $locationProvider: angular.ILocationProvider) {
  // Enable clean URLs without the #!/ prefix
  $locationProvider.html5Mode(true);

  APP_ROUTES.forEach(route => {
    if (route.redirectTo) {
      $routeProvider.when(route.path, { redirectTo: route.redirectTo });
    } else if (route.component) {
      // Automatically convert camelCase component name to kebab-case HTML tag
      const tag = route.component.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase();
      $routeProvider.when(route.path, { template: `<${tag}></${tag}>` });
    } else {
      // Fallback for legacy routes defining templateUrl and controller
      $routeProvider.when(route.path, {
        templateUrl: route.templateUrl,
        controller: route.controller,
        controllerAs: route.controllerAs,
        reloadOnSearch: route.reloadOnSearch
      });
    }
  });

  $routeProvider.otherwise({
    templateUrl: "/templates/not-found.html"
  });
}]);
