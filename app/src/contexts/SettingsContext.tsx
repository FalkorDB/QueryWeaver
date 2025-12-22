import React, { createContext, useContext, useState, ReactNode } from 'react';

export type AIVendor = 'openai' | 'google' | 'anthropic';

// Map UI vendor names to LiteLLM prefixes
export const VENDOR_PREFIX_MAP: Record<AIVendor, string> = {
  openai: 'openai',
  google: 'gemini',
  anthropic: 'anthropic',
};

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
  const [vendor, setVendor] = useState<AIVendor>('openai');
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string>('gpt-4o-mini');
  const [isApiKeyValid, setIsApiKeyValid] = useState<boolean>(false);

  const clearSettings = () => {
    setVendor('openai');
    setApiKey(null);
    setModelName('gpt-4.1');
    setIsApiKeyValid(false);
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
