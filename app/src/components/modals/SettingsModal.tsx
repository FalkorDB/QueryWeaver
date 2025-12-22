import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSettings, AIVendor } from '@/contexts/SettingsContext';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, CheckCircle2, XCircle, Sparkles, Key, Cpu } from 'lucide-react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// AI Vendor configurations
const AI_VENDORS = [
  { value: 'openai' as AIVendor, label: 'OpenAI', keyPrefix: 'sk-', exampleModel: 'gpt-4.1' },
  { value: 'google' as AIVendor, label: 'Google', keyPrefix: '', exampleModel: 'gemini-2.5-pro' },
  { value: 'anthropic' as AIVendor, label: 'Anthropic', keyPrefix: 'sk-ant-', exampleModel: 'claude-4-5-sonnet-20241022' },
];

const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const {
    vendor,
    apiKey,
    modelName,
    isApiKeyValid,
    setVendor,
    setApiKey,
    setModelName,
    setIsApiKeyValid,
    clearSettings,
  } = useSettings();

  const [tempVendor, setTempVendor] = useState<AIVendor>(vendor);
  const [tempApiKey, setTempApiKey] = useState(apiKey || '');
  const [tempModelName, setTempModelName] = useState(modelName);
  const [isValidating, setIsValidating] = useState(false);
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [validationStatus, setValidationStatus] = useState<'success' | 'error' | null>(null);

  // Update model placeholder when vendor changes
  useEffect(() => {
    const vendorConfig = getVendorConfig(tempVendor);
    // Auto-update model name when vendor changes
    if (vendorConfig) {
      setTempModelName(vendorConfig.exampleModel);
    }
  }, [tempVendor]);

  const getVendorConfig = (vendorType: AIVendor) => {
    return AI_VENDORS.find(v => v.value === vendorType);
  };

  const validateApiKey = async (key: string, vendorType: AIVendor) => {
    if (!key.trim()) {
      setValidationMessage('Please enter an API key');
      setValidationStatus('error');
      return false;
    }

    const vendorConfig = getVendorConfig(vendorType);
    if (vendorConfig?.keyPrefix && !key.startsWith(vendorConfig.keyPrefix)) {
      setValidationMessage(`Invalid API key format. ${vendorConfig.label} keys should start with "${vendorConfig.keyPrefix}"`);
      setValidationStatus('error');
      return false;
    }

    setIsValidating(true);
    setValidationMessage(null);
    setValidationStatus(null);

    try {
      // Map vendor to LiteLLM prefix (google -> gemini)
      const vendorPrefix = vendorType === 'google' ? 'gemini' : vendorType;
      
      const response = await fetch('/api/validate-api-key', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ 
          api_key: key,
          vendor: vendorPrefix,
          model: tempModelName,
        }),
      });

      const result = await response.json();

      if (response.ok && result.valid) {
        setValidationMessage('API key is valid!');
        setValidationStatus('success');
        setIsValidating(false);
        return true;
      } else {
        setValidationMessage(result.error || 'Invalid API key');
        setValidationStatus('error');
        setIsValidating(false);
        return false;
      }
    } catch (error) {
      setValidationMessage('Failed to validate API key. Please try again.');
      setValidationStatus('error');
      setIsValidating(false);
      return false;
    }
  };

  const handleSave = async () => {
    const isValid = await validateApiKey(tempApiKey, tempVendor);
    
    if (isValid) {
      setVendor(tempVendor);
      setApiKey(tempApiKey);
      setModelName(tempModelName);
      setIsApiKeyValid(true);
      setTimeout(() => {
        onClose();
      }, 500);
    }
  };

  const handleClear = () => {
    setTempVendor('openai');
    setTempApiKey('');
    setTempModelName('gpt-4o');
    setValidationMessage(null);
    setValidationStatus(null);
    clearSettings();
  };

  const handleClose = () => {
    setTempVendor(vendor);
    setTempApiKey(apiKey || '');
    setTempModelName(modelName);
    setValidationMessage(null);
    setValidationStatus(null);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[650px]">
        <DialogHeader className="space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-primary" />
            <DialogTitle className="text-2xl font-semibold">AI Model Configuration</DialogTitle>
          </div>
          <DialogDescription className="text-base">
            Connect your preferred AI provider to power natural language queries. Your credentials are stored only in memory.
          </DialogDescription>
        </DialogHeader>
        
        <div className="grid gap-6 py-6">
          {/* Provider Selection Card */}
          <div className="space-y-3 rounded-lg border bg-muted/50 p-4">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="vendor" className="text-sm font-medium">AI Provider</Label>
            </div>
            <Select
              value={tempVendor}
              onValueChange={(value) => setTempVendor(value as AIVendor)}
            >
              <SelectTrigger id="vendor" className="h-11">
                <SelectValue placeholder="Select a provider" />
              </SelectTrigger>
              <SelectContent>
                {AI_VENDORS.map((vendor) => (
                  <SelectItem key={vendor.value} value={vendor.value} className="py-3">
                    <div className="flex flex-col items-start">
                      <span className="font-medium">{vendor.label}</span>
                      <span className="text-xs text-muted-foreground">Example: {vendor.exampleModel}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* API Key Card */}
          <div className="space-y-3 rounded-lg border bg-muted/50 p-4">
            <div className="flex items-center gap-2">
              <Key className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="api-key" className="text-sm font-medium">API Key</Label>
            </div>
            <Input
              id="api-key"
              type="password"
              placeholder={getVendorConfig(tempVendor)?.keyPrefix ? `${getVendorConfig(tempVendor)?.keyPrefix}...` : 'Enter your API key'}
              value={tempApiKey}
              onChange={(e) => {
                setTempApiKey(e.target.value);
                setValidationMessage(null);
                setValidationStatus(null);
              }}
              className="h-11 font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <span className="inline-block w-1 h-1 rounded-full bg-green-500"></span>
              Session-only storage • Never persisted
            </p>
          </div>

          {/* Model Name Card */}
          <div className="space-y-3 rounded-lg border bg-muted/50 p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="model" className="text-sm font-medium">Model Name</Label>
            </div>
            <Input
              id="model"
              type="text"
              placeholder={getVendorConfig(tempVendor)?.exampleModel || 'Enter model name'}
              value={tempModelName}
              onChange={(e) => setTempModelName(e.target.value)}
              disabled={!tempApiKey.trim()}
              className="h-11 font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              {tempApiKey.trim() 
                ? `Any ${getVendorConfig(tempVendor)?.label} model (e.g., ${getVendorConfig(tempVendor)?.exampleModel})` 
                : 'Enter an API key first to enable model selection'}
            </p>
          </div>

          {/* Validation Message */}
          {validationMessage && (
            <Alert variant={validationStatus === 'error' ? 'destructive' : 'default'} className="border-2">
              <div className="flex items-center gap-2">
                {validationStatus === 'success' ? (
                  <CheckCircle2 className="h-5 w-5" />
                ) : (
                  <XCircle className="h-5 w-5" />
                )}
                <AlertDescription className="font-medium">{validationMessage}</AlertDescription>
              </div>
            </Alert>
          )}

          {/* Current Configuration Status */}
          {isApiKeyValid && apiKey && (
            <Alert className="border-2 border-green-200 bg-green-50 dark:bg-green-950 dark:border-green-800">
              <CheckCircle2 className="h-5 w-5 text-green-600 dark:text-green-400" />
              <AlertDescription className="text-green-800 dark:text-green-200 font-medium">
                Active: {getVendorConfig(vendor)?.label} • {modelName}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter className="flex justify-between sm:justify-between gap-2">
          <Button 
            variant="outline" 
            onClick={handleClear}
            disabled={!apiKey && !tempApiKey}
            className="h-11"
          >
            Clear Settings
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleClose} className="h-11">
              Cancel
            </Button>
            <Button 
              onClick={handleSave} 
              disabled={isValidating || !tempApiKey.trim() || !tempModelName.trim()}
              className="h-11 min-w-[100px]"
            >
              {isValidating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isValidating ? 'Validating...' : 'Save & Validate'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SettingsModal;
