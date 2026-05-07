/**
 * services/ProjectService.ts
 *
 * AngularJS factory that wraps all HTTP calls to the backend.
 * All endpoints return BaseResponse — the canonical server envelope.
 *
 * Design choice: factory (not service class) — idiomatic AngularJS 1.x pattern,
 * easier to mock in unit tests with $httpBackend.
 */

interface Project {
  project_id: string;
  project_name: string;
  project_start: string;
  project_end: string;
  company: string;
  description: string | null;
  project_value: number;
  area: string;
}

interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

interface ApiError {
  code: string;
  message: string;
}

// Canonical response envelope — mirrors backend BaseResponse[T].
interface BaseResponse<T = Project[]> {
  success: boolean;
  data: T | null;
  pagination: PaginationMeta | null;
  error: ApiError | null;
}

interface ProjectFilters {
  area?: string;
  keyword?: string;
  company?: string;
  page?: number;
  per_page?: number;
  sort_by?: string;
  order?: "asc" | "desc";
}

app.factory(
  "ProjectService",
  function ($http: angular.IHttpService, $q: angular.IQService, APP_CONFIG: any) {
    const API_BASE = APP_CONFIG.API_BASE_URL;

    function getProjects(filters: ProjectFilters): angular.IPromise<BaseResponse<Project[]>> {
      const params: Record<string, string | number> = {};
      if (filters.area) params["area"] = filters.area;
      if (filters.keyword) params["keyword"] = filters.keyword;
      if (filters.company) params["company"] = filters.company;
      if (filters.page !== undefined) params["page"] = filters.page;
      if (filters.per_page !== undefined) params["per_page"] = filters.per_page;
      if (filters.sort_by) params["sort_by"] = filters.sort_by;
      if (filters.order) params["order"] = filters.order;

      return $http
        .get<BaseResponse<Project[]>>(`${API_BASE}/projects`, { params })
        .then((response) => response.data)
        .catch((error) => $q.reject(error));
    }

    // Unwrap data[] from the envelope so callers receive a plain string array.
    function getAreas(): angular.IPromise<string[]> {
      return $http
        .get<BaseResponse<string[]>>(`${API_BASE}/areas`)
        .then((response) => response.data.data as string[])
        .catch((error) => $q.reject(error));
    }

    function getCompanies(): angular.IPromise<string[]> {
      return $http
        .get<BaseResponse<string[]>>(`${API_BASE}/companies`)
        .then((response) => response.data.data as string[])
        .catch((error) => $q.reject(error));
    }

    return { getProjects, getAreas, getCompanies };
  }
);
