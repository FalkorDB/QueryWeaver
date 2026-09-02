import { API_CONFIG, buildApiUrl } from '@/config/api';
import { csrfHeaders } from '@/lib/csrf';
import type { AuthStatus, SignupResult, User } from '@/types/api';

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

      // 503 = the backend could not check, not a verdict that you are logged
      // out. Keep the two apart so the UI can offer a retry rather than
      // bouncing a still-valid login to the sign-in screen.
      if (response.status === 503) {
        console.log('Authentication service temporarily unavailable');
        return { authenticated: false, unavailable: true };
      }

      if (!response.ok) {
        return { authenticated: false };
      }

      const data = await response.json();
      return data;
    } catch (error) {
      // Backend not available - return unauthenticated for demo mode
      console.log('Backend not available for auth - using demo mode');
      return { authenticated: false, unavailable: true };
    }
  }

  /**
   * Check if backend is available
   */
  static async checkBackendAvailable(): Promise<boolean> {
    try {
      await fetch(buildApiUrl('/health').replace('/health', ''), {
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
   * Sign up with an email address and password.
   *
   * A successful call creates nothing: the backend holds the details and mails
   * a confirmation code, and the account comes into existence when that code is
   * typed back in here. So there is no session to refresh yet.
   */
  static async signupWithEmail(details: {
    firstName: string;
    lastName: string;
    email: string;
    password: string;
  }): Promise<SignupResult> {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.SIGNUP_EMAIL), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify(details),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return {
        success: false,
        error: data.error || 'Could not create your account. Please try again.',
        retryAfterSeconds: data.retryAfterSeconds,
      };
    }
    return data as SignupResult;
  }

  /**
   * Log in with an email address and password.
   */
  static async loginWithEmail(email: string, password: string): Promise<{ success: boolean; error?: string }> {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_EMAIL), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { success: false, error: data.error || 'Could not sign you in. Please try again.' };
    }
    return { success: true };
  }

  /**
   * Ask for another copy of the signup confirmation code.
   *
   * The backend answers identically whether or not the address is waiting to be
   * confirmed, so the caller cannot use this to probe for accounts -- and
   * neither can the UI report anything more specific than "sent".
   */
  static async resendVerification(
    email: string
  ): Promise<{ success: boolean; message?: string; error?: string; retryAfterSeconds?: number }> {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.RESEND_VERIFICATION), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify({ email }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return {
        success: false,
        error: data.error || 'Could not send the email. Please try again.',
        retryAfterSeconds: data.retryAfterSeconds,
      };
    }
    return { success: true, message: data.message, retryAfterSeconds: data.retryAfterSeconds };
  }

  /**
   * Hand back the confirmation code that was mailed.
   *
   * This is what creates the account, so a success means the caller is now
   * logged in and the session should be refreshed.
   */
  static async verifyEmail(
    email: string,
    code: string
  ): Promise<{ success: boolean; error?: string }> {
    const response = await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.VERIFY_EMAIL), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
      body: JSON.stringify({ email, code }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return {
        success: false,
        error: data.error || 'Could not confirm your email address. Please try again.',
      };
    }
    return { success: true };
  }

  /**
   * Logout current user
   */
  static async logout(): Promise<void> {
    try {
      await fetch(buildApiUrl(API_CONFIG.ENDPOINTS.LOGOUT), {
        method: 'POST',
        credentials: 'include',
        headers: {
          ...csrfHeaders(),
        },
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

