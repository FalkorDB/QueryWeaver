import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buildApiUrl, API_CONFIG } from "@/config/api";
import { useAuth } from "@/contexts/AuthContext";
import { Eye, EyeOff } from "lucide-react";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canClose?: boolean;
  startInSignupMode?: boolean;
}

const LoginModal = ({ open, onOpenChange, canClose = true, startInSignupMode = false }: LoginModalProps) => {
  const { login, signup, refreshAuth, isAuthenticated } = useAuth();
  
  const [mode, setMode] = useState<'signin' | 'signup'>(startInSignupMode ? 'signup' : 'signin');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showEmailForm, setShowEmailForm] = useState(false);
  const [justAuthenticated, setJustAuthenticated] = useState(false);

  useEffect(() => {
    if (open) {
      setMode(startInSignupMode ? 'signup' : 'signin');
      setShowEmailForm(false);
      setError('');
      setFirstName('');
      setLastName('');
      setEmail('');
      setPassword('');
      setConfirmPassword('');
      setShowPassword(false);
      setShowConfirmPassword(false);
      setJustAuthenticated(false);
    }
  }, [open, startInSignupMode]);

  // Close modal automatically when authentication succeeds
  useEffect(() => {
    if (justAuthenticated && isAuthenticated && open) {
      onOpenChange(false);
      setJustAuthenticated(false);
    }
  }, [justAuthenticated, isAuthenticated, open, onOpenChange]);

  const handleGoogleAuth = () => {
    window.location.href = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GOOGLE);
  };

  const handleGithubAuth = () => {
    window.location.href = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GITHUB);
  };

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email.trim() || !password) {
      setError('Email and password are required');
      return;
    }
    setIsLoading(true);
    try {
      const result = await login.email(email, password);
      if (result.success) {
        // Refresh auth state and mark as authenticated
        await refreshAuth();
        setJustAuthenticated(true);
        // Clear form fields
        setEmail('');
        setPassword('');
        setShowEmailForm(false);
        setShowPassword(false);
      } else {
        setError(result.error || 'Login failed');
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!firstName.trim() || !lastName.trim() || !email.trim() || !password) {
      setError('All fields are required');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters long');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setIsLoading(true);
    try {
      const result = await signup.email(firstName, lastName, email, password);
      if (result.success) {
        // Refresh auth state and mark as authenticated
        await refreshAuth();
        setJustAuthenticated(true);
        // Clear form fields
        setFirstName('');
        setLastName('');
        setEmail('');
        setPassword('');
        setConfirmPassword('');
        setShowEmailForm(false);
        setShowPassword(false);
        setShowConfirmPassword(false);
      } else {
        setError(result.error || 'Signup failed');
      }
    } catch (err) {
      setError('An unexpected error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const switchMode = () => {
    setMode(mode === 'signin' ? 'signup' : 'signin');
    setShowEmailForm(true); // Keep user in email form when switching
    setError('');
    setEmail('');
    setPassword('');
    setConfirmPassword('');
    setFirstName('');
    setLastName('');
    setShowPassword(false);
    setShowConfirmPassword(false);
  };

  const isSignIn = mode === 'signin';

  return (
    <Dialog
      open={open}
      onOpenChange={canClose ? onOpenChange : undefined}
    >
      <DialogContent
        className="sm:max-w-[425px] bg-card border-border"
        onInteractOutside={(e) => {
          if (!canClose) {
            e.preventDefault();
          }
        }}
        onEscapeKeyDown={(e) => {
          if (!canClose) {
            e.preventDefault();
          }
        }}
        data-testid="login-modal"
      >
        <DialogHeader>
          <DialogTitle className="text-2xl font-semibold text-center text-card-foreground">
            {isSignIn ? 'Welcome to QueryWeaver' : 'Create Your Account'}
          </DialogTitle>
          <DialogDescription className="text-center text-muted-foreground pt-2">
            {isSignIn ? 'Sign in to access your databases and start querying' : 'Sign up to start using QueryWeaver'}
          </DialogDescription>
        </DialogHeader>

        {!showEmailForm ? (
          <div className="space-y-4 py-6">
            <Button
              onClick={handleGoogleAuth}
              className="w-full bg-white hover:bg-gray-50 text-gray-900 hover:text-gray-900 border-2 border-gray-300 hover:border-gray-400 font-medium py-6 text-base flex items-center justify-center gap-3 shadow-sm hover:shadow transition-all"
              variant="outline"
              data-testid="google-login-btn"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24">
                <path
                  fill="currentColor"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="currentColor"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="currentColor"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="currentColor"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              {isSignIn ? 'Continue with Google' : 'Sign up with Google'}
            </Button>
            <Button
              onClick={handleGithubAuth}
              className="w-full bg-gradient-to-r from-gray-200 to-gray-300 hover:from-gray-300 hover:to-gray-400 dark:from-[#24292e] dark:to-[#1a1e22] dark:hover:from-[#1b1f23] dark:hover:to-[#161a1d] text-gray-900 dark:text-white font-medium py-6 text-base flex items-center justify-center gap-3 shadow-md hover:shadow-lg transition-all border-2 border-gray-400 hover:border-gray-500 dark:border-gray-600"
              data-testid="github-login-btn"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              {isSignIn ? 'Continue with GitHub' : 'Sign up with GitHub'}
            </Button>
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">Or</span>
              </div>
            </div>
            <Button onClick={() => setShowEmailForm(true)} className="w-full" variant="outline">
              {isSignIn ? 'Sign in with Email' : 'Sign up with Email'}
            </Button>
            <div className="text-center text-sm text-muted-foreground pt-4">
              {isSignIn ? "Don't have an account? " : "Already have an account? "}
              <button onClick={switchMode} className="text-primary hover:underline font-medium">
                {isSignIn ? 'Sign up' : 'Sign in'}
              </button>
            </div>
          </div>
        ) : isSignIn ? (
          <form onSubmit={handleEmailLogin} className="space-y-4 py-6">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="john@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={isLoading} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input id="password" type={showPassword ? "text" : "password"} placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={isLoading} className="pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" tabIndex={-1}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {error && <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">{error}</div>}
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => { setShowEmailForm(false); setError(''); }} disabled={isLoading}>Back</Button>
              <Button type="submit" className="flex-1" disabled={isLoading}>{isLoading ? 'Signing in...' : 'Sign In'}</Button>
            </div>
            <div className="text-center text-sm text-muted-foreground pt-2">
              Don't have an account? <button type="button" onClick={switchMode} className="text-primary hover:underline font-medium" disabled={isLoading}>Sign up</button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleEmailSignUp} className="space-y-4 py-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="firstName">First Name</Label>
                <Input id="firstName" type="text" placeholder="John" value={firstName} onChange={(e) => setFirstName(e.target.value)} required disabled={isLoading} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lastName">Last Name</Label>
                <Input id="lastName" type="text" placeholder="Doe" value={lastName} onChange={(e) => setLastName(e.target.value)} required disabled={isLoading} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="john@example.com" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={isLoading} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input id="password" type={showPassword ? "text" : "password"} placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={isLoading} minLength={8} className="pr-10" />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" tabIndex={-1}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-xs text-muted-foreground">Must be at least 8 characters long</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <div className="relative">
                <Input id="confirmPassword" type={showConfirmPassword ? "text" : "password"} placeholder="••••••••" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required disabled={isLoading} className="pr-10" />
                <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground" tabIndex={-1}>
                  {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {error && <div className="text-sm text-destructive bg-destructive/10 p-3 rounded-md">{error}</div>}
            <div className="flex gap-3">
              <Button type="button" variant="outline" className="flex-1" onClick={() => { setShowEmailForm(false); setError(''); }} disabled={isLoading}>Back</Button>
              <Button type="submit" className="flex-1" disabled={isLoading}>{isLoading ? 'Creating Account...' : 'Create Account'}</Button>
            </div>
            <div className="text-center text-sm text-muted-foreground pt-2">
              Already have an account? <button type="button" onClick={switchMode} className="text-primary hover:underline font-medium" disabled={isLoading}>Sign in</button>
            </div>
          </form>
        )}
        {canClose && !showEmailForm && (
          <div className="text-center text-sm text-muted-foreground pt-2">
            <p>By {isSignIn ? 'signing in' : 'signing up'}, you agree to our Terms of Service and Privacy Policy</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default LoginModal;
