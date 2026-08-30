import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { AuthService } from "@/services/auth";
import { buildApiUrl, API_CONFIG } from "@/config/api";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canClose?: boolean; // Whether user can close the modal (false for required login)
}

const MIN_PASSWORD_LENGTH = 8;

// Only a fallback: the backend reports its own resend interval, and that is
// what the button waits for whenever it is available.
const RESEND_COOLDOWN_SECONDS = 60;

// Likewise a fallback for the code lifetime the backend reports.
const CODE_TTL_MINUTES = 15;

const CODE_LENGTH = 6;

const emptyForm = { firstName: "", lastName: "", email: "", password: "" };

const LoginModal = ({ open, onOpenChange, canClose = true }: LoginModalProps) => {
  const { providers, refreshAuth } = useAuth();
  const { toast } = useToast();

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Set once a signup has been accepted. While it holds an address the modal
  // asks for the mailed code instead of showing the form -- there is no
  // account yet, so there is nothing else to offer.
  const [awaitingEmail, setAwaitingEmail] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [codeTtlMinutes, setCodeTtlMinutes] = useState(CODE_TTL_MINUTES);
  const [cooldown, setCooldown] = useState(0);
  const [resending, setResending] = useState(false);

  const emailEnabled = providers?.email_auth_enabled ?? false;
  // Default to showing the OAuth buttons: a backend that does not report
  // providers at all would otherwise leave the user with no way in.
  const googleEnabled = providers?.google_auth_enabled ?? true;
  const githubEnabled = providers?.github_auth_enabled ?? true;
  const showOAuth = googleEnabled || githubEnabled;

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  // Reopening should not drop the user back into a stale error.
  useEffect(() => {
    if (!open) {
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  const handleGoogleLogin = () => {
    window.location.href = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GOOGLE);
  };

  const handleGithubLogin = () => {
    window.location.href = buildApiUrl(API_CONFIG.ENDPOINTS.LOGIN_GITHUB);
  };

  const switchMode = (next: "login" | "signup") => {
    setMode(next);
    setError(null);
  };

  const update =
    (field: keyof typeof emptyForm) => (event: React.ChangeEvent<HTMLInputElement>) => {
      setForm((current) => ({ ...current, [field]: event.target.value }));
    };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (mode === "signup" && form.password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters long`);
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") {
        const result = await AuthService.loginWithEmail(form.email.trim(), form.password);
        if (!result.success) {
          setError(result.error ?? "Could not sign you in.");
          return;
        }
        await refreshAuth();
        setForm(emptyForm);
        onOpenChange(false);
        return;
      }

      const result = await AuthService.signupWithEmail({
        firstName: form.firstName.trim(),
        lastName: form.lastName.trim(),
        email: form.email.trim(),
        password: form.password,
      });

      if (!result.success) {
        setError(result.error ?? "Could not create your account.");
        return;
      }

      // Deliberately no refreshAuth(): signing up does not sign you in. The
      // account is created when the mailed code is handed back, and that is
      // what establishes the session.
      setAwaitingEmail(result.email ?? form.email.trim());
      setCooldown(result.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
      if (result.codeTtlSeconds) {
        setCodeTtlMinutes(Math.max(1, Math.round(result.codeTtlSeconds / 60)));
      }
      setCode("");
      setForm(emptyForm);
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleVerify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!awaitingEmail || verifying) return;
    setError(null);
    setVerifying(true);
    try {
      const result = await AuthService.verifyEmail(awaitingEmail, code.trim());
      if (!result.success) {
        setError(result.error ?? "Could not confirm your email address.");
        setCode("");
        return;
      }
      // Confirming is what created the account and signed the browser in.
      await refreshAuth();
      setAwaitingEmail(null);
      setCode("");
      setMode("login");
      onOpenChange(false);
      toast({
        title: "Email confirmed",
        description: "Your account is ready and you are signed in.",
      });
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setVerifying(false);
    }
  };

  const handleResend = async () => {
    if (!awaitingEmail || cooldown > 0 || resending) return;
    setResending(true);
    setError(null);
    try {
      const result = await AuthService.resendVerification(awaitingEmail);
      // Only a request the backend actually took starts the clock. Refusing to
      // retry after a failed one would lock the user out over an email that
      // was never sent.
      if (result.success) {
        setCooldown(result.retryAfterSeconds ?? RESEND_COOLDOWN_SECONDS);
        setCode("");
      }
      toast({
        title: result.success ? "Email sent" : "Could not send the email",
        description: result.success
          ? result.message ?? "Check your inbox for the confirmation code."
          : result.error,
        variant: result.success ? undefined : "destructive",
      });
    } catch {
      toast({
        title: "Could not send the email",
        description: "Could not reach the server. Please try again.",
        variant: "destructive",
      });
    } finally {
      setResending(false);
    }
  };

  const backToSignIn = () => {
    setAwaitingEmail(null);
    setCode("");
    setMode("login");
    setError(null);
  };

  const renderAwaitingVerification = () => (
    <form onSubmit={handleVerify} className="space-y-4 py-4" data-testid="verify-email-notice">
      <p className="text-sm text-muted-foreground">
        We sent a {CODE_LENGTH}-digit confirmation code to{" "}
        <span className="font-medium text-card-foreground">{awaitingEmail}</span>. Enter it
        below to finish creating your account &mdash; you will be signed in straight away.
      </p>
      <p className="text-sm text-muted-foreground">
        The code works once and expires after {codeTtlMinutes} minutes. Until you enter it, no
        account exists.
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="verification-code">Confirmation code</Label>
        <Input
          id="verification-code"
          value={code}
          onChange={(event) =>
            setCode(event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH))
          }
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern={`\\d{${CODE_LENGTH}}`}
          placeholder={"0".repeat(CODE_LENGTH)}
          className="text-center text-lg tracking-[0.4em]"
          required
          autoFocus
          data-testid="verification-code"
        />
      </div>

      {error && (
        <p className="text-sm text-destructive" role="alert" data-testid="auth-error">
          {error}
        </p>
      )}

      <Button
        type="submit"
        className="w-full"
        disabled={verifying || code.length !== CODE_LENGTH}
        data-testid="verify-code-btn"
      >
        {verifying ? "Confirming..." : "Confirm email"}
      </Button>
      <Button
        type="button"
        onClick={handleResend}
        variant="outline"
        className="w-full"
        disabled={cooldown > 0 || resending}
        data-testid="resend-verification-btn"
      >
        {cooldown > 0 ? `Resend code in ${cooldown}s` : resending ? "Sending..." : "Resend code"}
      </Button>
      <Button type="button" onClick={backToSignIn} variant="ghost" className="w-full">
        Back to sign in
      </Button>
    </form>
  );

  const renderEmailForm = () => (
    <form onSubmit={handleSubmit} className="space-y-3" data-testid="email-auth-form">
      {mode === "signup" && (
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="firstName">First name</Label>
            <Input
              id="firstName"
              value={form.firstName}
              onChange={update("firstName")}
              autoComplete="given-name"
              required
              data-testid="signup-first-name"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lastName">Last name</Label>
            <Input
              id="lastName"
              value={form.lastName}
              onChange={update("lastName")}
              autoComplete="family-name"
              required
              data-testid="signup-last-name"
            />
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          value={form.email}
          onChange={update("email")}
          autoComplete="email"
          required
          data-testid="auth-email"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          value={form.password}
          onChange={update("password")}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          minLength={mode === "signup" ? MIN_PASSWORD_LENGTH : undefined}
          required
          data-testid="auth-password"
        />
        {mode === "signup" && (
          <p className="text-xs text-muted-foreground">
            At least {MIN_PASSWORD_LENGTH} characters.
          </p>
        )}
      </div>

      {error && (
        <p className="text-sm text-destructive" role="alert" data-testid="auth-error">
          {error}
        </p>
      )}

      <Button type="submit" className="w-full" disabled={submitting} data-testid="auth-submit">
        {submitting
          ? mode === "login"
            ? "Signing in..."
            : "Creating account..."
          : mode === "login"
            ? "Sign in"
            : "Create account"}
      </Button>

      <p className="text-center text-sm text-muted-foreground">
        {mode === "login" ? (
          <>
            Don&apos;t have an account?{" "}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              onClick={() => switchMode("signup")}
              data-testid="switch-to-signup"
            >
              Sign up
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              onClick={() => switchMode("login")}
              data-testid="switch-to-login"
            >
              Sign in
            </button>
          </>
        )}
      </p>
    </form>
  );

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
            {awaitingEmail ? "Check your inbox" : "Welcome to QueryWeaver"}
          </DialogTitle>
          <DialogDescription className="text-center text-muted-foreground pt-2">
            {awaitingEmail
              ? "Enter the code we emailed you to create your account"
              : "Sign in to access your databases and start querying"}
          </DialogDescription>
        </DialogHeader>

        {awaitingEmail ? (
          renderAwaitingVerification()
        ) : (
          <>
            {showOAuth && (
              <div className="space-y-4 py-6">
                {googleEnabled && (
                  <Button
                    onClick={handleGoogleLogin}
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
                    Continue with Google
                  </Button>
                )}

                {githubEnabled && (
                  <Button
                    onClick={handleGithubLogin}
                    className="w-full bg-gradient-to-r from-gray-200 to-gray-300 hover:from-gray-300 hover:to-gray-400 dark:from-[#24292e] dark:to-[#1a1e22] dark:hover:from-[#1b1f23] dark:hover:to-[#161a1d] text-gray-900 dark:text-white font-medium py-6 text-base flex items-center justify-center gap-3 shadow-md hover:shadow-lg transition-all border-2 border-gray-400 hover:border-gray-500 dark:border-gray-600"
                    data-testid="github-login-btn"
                  >
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                    </svg>
                    Continue with GitHub
                  </Button>
                )}
              </div>
            )}

            {emailEnabled && showOAuth && (
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">or</span>
                </div>
              </div>
            )}

            {emailEnabled && <div className="pt-4">{renderEmailForm()}</div>}
          </>
        )}

        {canClose && !awaitingEmail && (
          <div className="text-center text-sm text-muted-foreground pt-2">
            <p>By signing in, you agree to our Terms of Service and Privacy Policy</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default LoginModal;
