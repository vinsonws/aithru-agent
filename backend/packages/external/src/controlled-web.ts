export interface ControlledWebResponse {
  status: number;
  text(): Promise<string>;
}

export type ControlledWebFetch = (
  url: string,
  init?: { method?: string; headers?: Record<string, string>; body?: string },
) => Promise<ControlledWebResponse>;

export interface ControlledWebProviderConfig {
  allowedHosts: string[];
  fetcher: ControlledWebFetch;
  searchEndpoint?: string;
}

export interface ControlledFetchResult {
  url: string;
  status: number;
  content: string;
}

export class ControlledWebProvider {
  private allowedHosts: Set<string>;

  constructor(private config: ControlledWebProviderConfig) {
    this.allowedHosts = new Set(
      config.allowedHosts.map((host) => host.toLowerCase()),
    );
  }

  async fetchUrl(url: string): Promise<ControlledFetchResult> {
    const parsed = this.validateAllowedUrl(url);
    const response = await this.config.fetcher(parsed.toString(), { method: "GET" });
    return {
      url: parsed.toString(),
      status: response.status,
      content: await response.text(),
    };
  }

  async search(query: string): Promise<ControlledFetchResult> {
    if (!this.config.searchEndpoint) {
      throw new Error("WEB_SEARCH_NOT_CONFIGURED");
    }
    const endpoint = this.validateAllowedUrl(this.config.searchEndpoint);
    endpoint.searchParams.set("q", query);
    const response = await this.config.fetcher(endpoint.toString(), { method: "GET" });
    return {
      url: endpoint.toString(),
      status: response.status,
      content: await response.text(),
    };
  }

  private validateAllowedUrl(url: string): URL {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      throw new Error(`WEB_URL_SCHEME_DENIED: ${parsed.protocol}`);
    }
    if (!this.allowedHosts.has(parsed.host.toLowerCase())) {
      throw new Error(`WEB_HOST_DENIED: ${parsed.host}`);
    }
    return parsed;
  }
}
