import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { DEFAULT_MODEL } from '@/utils/vendorConfig';

export type AIVendor = 'openai' | 'google' | 'anthropic';

const STORAGE_KEY = 'queryweaver_ai_settings';

interface StoredSettings {
  vendor: AIVendor;
  modelName: string;
}

function loadStoredSettings(): StoredSettings {
  if (typeof window === 'undefined') {
    return { vendor: 'openai', modelName: DEFAULT_MODEL };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        vendor: parsed.vendor || 'openai',
        modelName: parsed.modelName || DEFAULT_MODEL,
      };
    }
  } catch { /* ignore corrupt storage */ }
  return { vendor: 'openai', modelName: DEFAULT_MODEL };
}

interface SettingsContextType {
  vendor: AIVendor;
  apiKey: string | null;
  modelName: string;
  isApiKeyValid: boolean;
  setVendor: (vendor: AIVendor) => void;
  setApiKey: (key: string | null) => void;
  setModelName: (model: string) => void;
  setIsApiKeyValid: (valid: boolean) => void;
  clearSettings: () => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};

interface SettingsProviderProps {
  children: ReactNode;
}

export const SettingsProvider: React.FC<SettingsProviderProps> = ({ children }) => {
  const stored = loadStoredSettings();
  const [vendor, setVendor] = useState<AIVendor>(stored.vendor);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string>(stored.modelName);
  const [isApiKeyValid, setIsApiKeyValid] = useState<boolean>(false);

  // Persist vendor + model to localStorage (never persist the API key)
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ vendor, modelName }));
  }, [vendor, modelName]);

  const clearSettings = () => {
    setVendor('openai');
    setApiKey(null);
    setModelName(DEFAULT_MODEL);
    setIsApiKeyValid(false);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <SettingsContext.Provider
      value={{
        vendor,
        apiKey,
        modelName,
        isApiKeyValid,
        setVendor,
        setApiKey,
        setModelName,
        setIsApiKeyValid,
        clearSettings,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
};
