import { API_CONFIG, buildApiUrl } from '@/config/api';
import type { AuthStatus, User } from '@/types/api';

/**
 * Authentication Service
 * Handles OAuth authentication with Google and GitHub
 */

export class AuthService {
  /**
   * Check current authentication status
   */
  static async checkAuthStatus(): Promise<AuthStatus> {
    try {
      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.AUTH_STATUS), {
        credentials: 'include', // Important: include cookies for session
      });

      // 403 = Not authenticated (normal state - user can still use the app)
      if (response.status === 403) {
        console.log('Not authenticated - you can still use QueryWeaver, sign in to save databases');
        return { authenticated: false };
      }

      if (!response.ok) {
        return { authenticated: false };
      }

      const data = await response.json();
      return data;
    } catch (error) {
      // Backend not available - return unauthenticated for demo mode
      console.log('Backend not available for auth - using demo mode');
      return { authenticated: false };
    }
  }

  /**
   * Check if backend is available
   */
  static async checkBackendAvailable(): Promise<boolean> {
    try {
      const response = await fetch(buildApiUrl('/health').replace('/health', ''), {
        method: 'HEAD',
        mode: 'no-cors'
      });
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Initiate Google OAuth login
   * Redirects to Google OAuth flow
   */
  static async loginWithGoogle(): Promise<void> {
    try {
      // First check if backend is available
      const url = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GOOGLE);
      console.log('Redirecting to Google OAuth:', url);
      
      // Just redirect - let the backend handle the OAuth flow
      window.location.href = url;
    } catch (error) {
      console.error('Failed to initiate Google login:', error);
      throw new Error('Failed to connect to authentication service. Please ensure the backend is running and OAuth is configured.');
    }
  }

  /**
   * Initiate GitHub OAuth login
   * Redirects to GitHub OAuth flow
   */
  static async loginWithGithub(): Promise<void> {
    try {
      const url = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GITHUB);
      console.log('Redirecting to GitHub OAuth:', url);
      
      // Just redirect - let the backend handle the OAuth flow
      window.location.href = url;
    } catch (error) {
      console.error('Failed to initiate GitHub login:', error);
      throw new Error('Failed to connect to authentication service. Please ensure the backend is running and OAuth is configured.');
    }
  }

  /**
   * Logout current user
   */
  static async logout(): Promise<void> {
    try {
      await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.LOGOUT), {
        method: 'POST',
        credentials: 'include',
      });
    } catch (error) {
      console.error('Failed to logout:', error);
      throw error;
    }
  }

  /**
   * Get current user information
   */
  static async getCurrentUser(): Promise<User | null> {
    try {
      const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.USER), {
        credentials: 'include',
      });

      if (!response.ok) {
        return null;
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Failed to get current user:', error);
      return null;
    }
  }
}

