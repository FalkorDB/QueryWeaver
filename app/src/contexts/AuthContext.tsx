import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { AuthService } from '@/services/auth';
import type { User } from '@/types/api';

// How long to wait before re-checking while the backend cannot answer. The
// login survives the outage, so the session comes back on its own once the
// backend does -- without this the user stays in limbo until they reload.
const UNAVAILABLE_RETRY_MS = 15000;

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  /** The check could not be made, as opposed to answering "not logged in". */
  isUnavailable: boolean;
  isLoading: boolean;
  login: {
    google: () => Promise<void>;
    github: () => Promise<void>;
  };
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const checkAuth = async () => {
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
    try {
      setIsLoading(true);
      const status = await AuthService.checkAuthStatus();
      setUser(status.user || null);
      setIsUnavailable(!!status.unavailable);
      if (status.unavailable) {
        retryTimer.current = setTimeout(checkAuth, UNAVAILABLE_RETRY_MS);
      }
    } catch (error) {
      console.log('Backend not available - running in demo mode');
      // Silently fail - this is expected when backend isn't running
      setUser(null);
      setIsUnavailable(false);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, []);

  const handleLogout = async () => {
    try {
      await AuthService.logout();
      setUser(null);
      setIsUnavailable(false);
    } catch (error) {
      console.error('Logout failed:', error);
      throw error;
    }
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isUnavailable,
    isLoading,
    login: {
      google: AuthService.loginWithGoogle,
      github: AuthService.loginWithGithub,
    },
    logout: handleLogout,
    refreshAuth: checkAuth,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

