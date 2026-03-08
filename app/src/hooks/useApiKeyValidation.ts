import { useState } from 'react';
import type { AIVendor } from '@/contexts/SettingsContext';
import { getVendorPrefix, validateApiKeyFormat } from '@/utils/vendorConfig';
import { buildApiUrl } from '@/config/api';
import { csrfHeaders } from '@/lib/csrf';

interface ValidationState {
  message: string | null;
  status: 'success' | 'error' | null;
  isValidating: boolean;
}

export function useApiKeyValidation() {
  const [state, setState] = useState<ValidationState>({
    message: null,
    status: null,
    isValidating: false,
  });

  const clearValidation = () => {
    setState({ message: null, status: null, isValidating: false });
  };

  const validateApiKey = async (key: string, vendor: AIVendor, modelName: string): Promise<boolean> => {
    const formatError = validateApiKeyFormat(key, vendor);
    if (formatError) {
      setState({ message: formatError, status: 'error', isValidating: false });
      return false;
    }

    setState({ message: null, status: null, isValidating: true });

    try {
      const vendorPrefix = getVendorPrefix(vendor);
      // Strip vendor prefix if the user already included it
      const model = modelName.startsWith(`${vendorPrefix}/`)
        ? modelName.slice(vendorPrefix.length + 1)
        : modelName;

      const response = await fetch(buildApiUrl('/validate-api-key'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...csrfHeaders(),
        },
        credentials: 'include',
        body: JSON.stringify({
          api_key: key,
          vendor: vendorPrefix,
          model,
        }),
      });

      const result = await response.json();

      if (response.ok && result.valid) {
        setState({ message: 'API key is valid!', status: 'success', isValidating: false });
        return true;
      } else {
        setState({ message: result.error || 'Invalid API key', status: 'error', isValidating: false });
        return false;
      }
    } catch {
      setState({ message: 'Failed to validate API key. Please try again.', status: 'error', isValidating: false });
      return false;
    }
  };

  return {
    message: state.message,
    status: state.status,
    isValidating: state.isValidating,
    validateApiKey,
    clearValidation,
  };
}
