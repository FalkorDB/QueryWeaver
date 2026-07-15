import { API_CONFIG, buildApiUrl } from '@/config/api';

/**
 * Metadata Service
 * Reads public application metadata (e.g. the running backend version)
 * from the unauthenticated /version endpoint.
 */

export interface VersionInfo {
  name: string;
  version: string;
}

export class MetaService {
  /**
   * Fetch the running backend version. Returns null if the backend is
   * unavailable or the request fails (the UI should degrade gracefully).
   */
  static async getVersion(): Promise<VersionInfo | null> {
    try {
      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.VERSION));
      if (!response.ok) {
        return null;
      }
      return await response.json();
    } catch (error) {
      console.error('Failed to fetch version:', error);
      return null;
    }
  }
}
