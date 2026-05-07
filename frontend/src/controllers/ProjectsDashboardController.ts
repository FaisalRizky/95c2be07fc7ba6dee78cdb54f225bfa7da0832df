/**
 * components/projectsDashboard.ts
 *
 * Modern AngularJS (1.5+) component for the project list page.
 * Replaces the deprecated ng-controller + $scope approach with
 * isolated Controller As syntax and lifecycle hooks.
 */

class ProjectsDashboardController {
  // Dependencies
  static $inject = ["$scope", "$location", "ProjectService", "APP_CONFIG"];
  
  // State
  projects: Project[] = [];
  areas: string[] = [];
  companies: string[] = [];
  loading: boolean = false;
  error: string | null = null;

  // Filters
  filters = {
    area: "",
    keyword: "",
    company: "",
  };

  // Pagination
  pagination: PaginationMeta | null = null;
  currentPage: number = 1;
  perPage: number;
  perPageOptions = [
    { label: "10", value: 10 },
    { label: "20", value: 20 },
    { label: "50", value: 50 },
    { label: "100", value: 100 }
  ];

  // Sorting - Renamed to match API exactly
  sort_by: string | null = "project_start";
  order: "asc" | "desc" = "desc";

  constructor(
    private $scope: angular.IScope,
    private $location: angular.ILocationService,
    private ProjectService: any,
    private APP_CONFIG: any
  ) {
    this.perPage = this.APP_CONFIG.DEFAULT_PER_PAGE || 20;
    
    // Initialize from URL parameters
    const search = this.$location.search();
    if (search.area) this.filters.area = search.area;
    if (search.keyword) this.filters.keyword = search.keyword;
    if (search.company) this.filters.company = search.company;
    if (search.page) this.currentPage = parseInt(search.page, 10);
    if (search.sort_by) this.sort_by = search.sort_by;
    if (search.order) this.order = search.order;

    this.init();

    // Handle browser Back/Forward buttons when reloadOnSearch is false
    this.$scope.$on("$routeUpdate", () => {
      const newSearch = this.$location.search();
      
      // Compare URL state with current filter state to avoid loops
      const hasChanged = 
        (newSearch.area || "") !== this.filters.area ||
        (newSearch.keyword || "") !== this.filters.keyword ||
        (newSearch.company || "") !== this.filters.company ||
        (parseInt(newSearch.page || "1", 10)) !== this.currentPage ||
        (newSearch.sort_by || "project_start") !== this.sort_by ||
        (newSearch.order || "desc") !== this.order;

      if (hasChanged) {
        this.filters.area = newSearch.area || "";
        this.filters.keyword = newSearch.keyword || "";
        this.filters.company = newSearch.company || "";
        this.currentPage = parseInt(newSearch.page || "1", 10);
        this.sort_by = newSearch.sort_by || "project_start";
        this.order = newSearch.order || "desc";
        this.fetchProjects(this.currentPage);
      }
    });
  }

  private init() {
    this.loadAreas();
    this.loadCompanies();
    this.fetchProjects(this.currentPage);
  }

  private loadAreas() {
    // Only load if empty to prevent redundant calls on controller re-init
    if (this.areas.length > 0) return;
    this.ProjectService.getAreas().then((areas: string[]) => { this.areas = areas; });
  }

  private loadCompanies() {
    // Only load if empty to prevent redundant calls on controller re-init
    if (this.companies.length > 0) return;
    this.ProjectService.getCompanies().then((companies: string[]) => { this.companies = companies; });
  }

  private fetchProjects(page: number) {
    this.loading = true;
    this.error = null;

    const requestFilters: ProjectFilters = {
      page: page,
      per_page: this.perPage,
      area: this.filters.area || undefined,
      keyword: this.filters.keyword || undefined,
      company: this.filters.company || undefined,
      sort_by: this.sort_by || undefined,
      order: this.order,
    };

    // Update URL to make the search linkable
    this.$location.search({
      area: this.filters.area || null,
      keyword: this.filters.keyword || null,
      company: this.filters.company || null,
      page: page > 1 ? page : null,
      sort_by: this.sort_by || null,
      order: this.order
    });

    this.ProjectService.getProjects(requestFilters).then(
      (response: BaseResponse<Project[]>) => {
        // Every response is now a BaseResponse envelope — no Array.isArray guard needed.
        this.projects = response.data ?? [];
        this.pagination = response.pagination;
        this.currentPage = page;
        this.loading = false;
      },
      (error: any) => {
        this.loading = false;
        // Error shape: { success: false, data: null, error: { code, message } }
        this.error = error.data?.error?.message ?? "An unexpected error occurred.";
        this.projects = [];
        this.pagination = null;
      }
    );
  }

  search() {
    this.fetchProjects(1);
  }

  toggleSort(column: string) {
    if (this.sort_by === column) {
      this.order = this.order === "asc" ? "desc" : "asc";
    } else {
      this.sort_by = column;
      // UX: Date columns default to newest first, text/value default to asc
      this.order = (column === "project_start" || column === "project_end") ? "desc" : "asc";
    }
    this.fetchProjects(1);
  }

  clearFilters() {
    this.filters = { area: "", keyword: "", company: "" };
    this.sort_by = "project_start";
    this.order = "desc";
    this.$location.search({});
    this.fetchProjects(1);
  }

  goToPage(page: number) {
    if (page < 1 || (this.pagination && page > this.pagination.total_pages)) return;
    this.fetchProjects(page);
  }

  hasNextPage() { return !!this.pagination && this.currentPage < this.pagination.total_pages; }
  hasPrevPage() { return this.currentPage > 1; }

  pageRange() {
    if (!this.pagination) return [];
    const total = this.pagination.total_pages;
    const current = this.currentPage;
    const delta = 2;
    const range: number[] = [];
    for (let i = Math.max(1, current - delta); i <= Math.min(total, current + delta); i++) {
      range.push(i);
    }
    return range;
  }
}

app.controller("ProjectsDashboardController", ProjectsDashboardController);
