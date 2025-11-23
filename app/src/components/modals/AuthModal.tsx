import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Github } from "lucide-react";
import { useToast } from "@/components/ui/use-toast";
import { AuthService } from "@/services/auth";

interface AuthModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const AuthModal = ({ open, onOpenChange }: AuthModalProps) => {
  const { toast } = useToast();

  const handleGoogleSignIn = async () => {
    try {
      // Redirect to Google OAuth
      await AuthService.loginWithGoogle();
    } catch (error) {
      toast({
        title: "Authentication Error",
        description: error instanceof Error ? error.message : "Failed to sign in with Google",
        variant: "destructive",
      });
    }
  };

  const handleGithubSignIn = async () => {
    try {
      // Redirect to GitHub OAuth
      await AuthService.loginWithGithub();
    } catch (error) {
      toast({
        title: "Authentication Error",
        description: error instanceof Error ? error.message : "Failed to sign in with GitHub",
        variant: "destructive",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px] bg-card border-border">
        <DialogHeader className="text-center">
          <DialogTitle className="text-xl font-semibold text-card-foreground">
            Welcome to QueryWeaver
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Sign in to save your databases and queries
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-3 mt-4">
          {/* OAuth buttons - Try to use them, gracefully fall back if not configured */}
          <Button
            onClick={handleGoogleSignIn}
            className="w-full bg-google-blue hover:bg-google-blue/90 text-white font-medium py-3 h-auto"
          >
            <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
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
            Sign in with Google
          </Button>

          <Button
            onClick={handleGithubSignIn}
            className="w-full bg-github-dark hover:bg-github-dark/90 text-white font-medium py-3 h-auto"
          >
            <Github className="w-5 h-5 mr-3" />
            Sign in with GitHub
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default AuthModal;