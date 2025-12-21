import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/components/ui/use-toast';
import { TokenService, type Token } from '@/services/tokens';
import { Copy, Eye, EyeOff, Trash2, AlertCircle } from 'lucide-react';

interface TokensModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const TokensModal: React.FC<TokensModalProps> = ({ open, onOpenChange }) => {
  const [tokens, setTokens] = useState<Token[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [deleteTokenId, setDeleteTokenId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const { toast } = useToast();

  const loadTokens = async () => {
    try {
      setLoading(true);
      const data = await TokenService.listTokens();
      setTokens(data.tokens);
    } catch (error) {
      console.error('Error loading tokens:', error);
      toast({
        title: 'Error',
        description: 'Failed to load tokens. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadTokens();
      setNewToken(null);
      setShowToken(false);
    }
  }, [open]);

  const handleGenerateToken = async () => {
    try {
      setGenerating(true);
      const token = await TokenService.generateToken();
      setNewToken(token.token_id);
      setShowToken(false);
      await loadTokens();
      toast({
        title: 'Success',
        description: 'Token generated successfully',
      });
    } catch (error) {
      console.error('Error generating token:', error);
      toast({
        title: 'Error',
        description: 'Failed to generate token. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyToken = async () => {
    if (!newToken) return;
    try {
      await navigator.clipboard.writeText(newToken);
      toast({
        title: 'Copied!',
        description: 'Token copied to clipboard',
      });
    } catch (error) {
      console.error('Error copying token:', error);
      toast({
        title: 'Copy failed',
        description: 'We could not copy the token. Please copy it manually.',
        variant: 'destructive',
      });
    }
  };

  const handleDeleteToken = async () => {
    if (!deleteTokenId) return;

    try {
      setDeleting(true);
      await TokenService.deleteToken(deleteTokenId);
      await loadTokens();
      setDeleteTokenId(null);
      toast({
        title: 'Success',
        description: 'Token deleted successfully',
      });
    } catch (error) {
      console.error('Error deleting token:', error);
      toast({
        title: 'Error',
        description: 'Failed to delete token. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (timestamp: number): string => {
    if (!timestamp) return '';
    
    // Convert to milliseconds if timestamp is in seconds
    const ms = timestamp < 1e12 ? timestamp * 1000 : timestamp;
    const date = new Date(ms);
    
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto bg-gray-800 border-gray-600">
          <DialogHeader>
            <DialogTitle className="text-gray-100">API Tokens</DialogTitle>
            <DialogDescription className="text-gray-400">
              API tokens allow you to authenticate with the QueryWeaver API without using OAuth.
              Keep your tokens secure and don't share them publicly.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Generate Token Button */}
            <div>
              <Button
                onClick={handleGenerateToken}
                disabled={generating}
                className="bg-purple-600 hover:bg-purple-700"
                data-testid="generate-token-btn"
              >
                {generating ? 'Generating...' : 'Generate New Token'}
              </Button>
            </div>

            {/* New Token Display */}
            {newToken && (
              <Alert className="bg-green-900/20 border-green-600" data-testid="new-token-alert">
                <AlertCircle className="h-4 w-4 text-green-600" />
                <AlertDescription className="text-gray-200">
                  <h4 className="font-semibold mb-2">Token Generated Successfully!</h4>
                  <p className="text-sm text-gray-300 mb-3">
                    <strong>Important:</strong> This is the only time you'll see this token. Copy it now and store it securely.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="flex-1 flex gap-2">
                      <Input
                        type={showToken ? 'text' : 'password'}
                        value={newToken}
                        readOnly
                        className="bg-gray-900 border-gray-600 text-gray-100 font-mono text-xs sm:text-sm"
                        data-testid="new-token-input"
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowToken(!showToken)}
                        className="bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600 flex-shrink-0"
                        data-testid="toggle-token-visibility"
                      >
                        {showToken ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </Button>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopyToken}
                      className="bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600"
                      data-testid="copy-token-btn"
                    >
                      <Copy className="h-4 w-4 mr-1" />
                      Copy
                    </Button>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            {/* Tokens List */}
            <div>
              <h3 className="text-lg font-semibold text-gray-100 mb-3">Your Tokens</h3>
              {loading ? (
                <p className="text-gray-400">Loading tokens...</p>
              ) : tokens.length === 0 ? (
                <p className="text-gray-400">You don't have any API tokens yet.</p>
              ) : (
                <div className="overflow-x-auto -mx-2 sm:mx-0">
                  <Table data-testid="tokens-table">
                    <TableHeader>
                      <TableRow className="border-gray-600">
                        <TableHead className="text-gray-300">Token</TableHead>
                        <TableHead className="text-gray-300 hidden sm:table-cell">Created</TableHead>
                        <TableHead className="text-gray-300">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tokens.map((token) => (
                        <TableRow key={token.token_id} className="border-gray-600" data-testid={`token-row-${token.token_id}`}>
                          <TableCell className="text-gray-200 font-mono text-xs sm:text-sm" data-testid={`token-value-${token.token_id}`}>
                            ****{token.token_id}
                          </TableCell>
                          <TableCell className="text-gray-300 text-xs sm:text-sm hidden sm:table-cell" data-testid={`token-created-${token.token_id}`}>
                            {formatDate(token.created_at)}
                          </TableCell>
                          <TableCell>
                            <Button
                              variant="destructive"
                              size="sm"
                              onClick={() => setDeleteTokenId(token.token_id)}
                              className="bg-red-600 hover:bg-red-700 h-8 px-2 sm:px-3"
                              data-testid={`delete-token-btn-${token.token_id}`}
                            >
                              <Trash2 className="h-4 w-4 sm:mr-1" />
                              <span className="hidden sm:inline">Delete</span>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTokenId} onOpenChange={(open) => !open && setDeleteTokenId(null)}>
        <AlertDialogContent className="bg-gray-800 border-gray-600" data-testid="delete-token-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-gray-100">Delete Token</AlertDialogTitle>
            <AlertDialogDescription className="text-gray-300">
              Are you sure you want to delete this token? This action cannot be undone.
              <br />
              <br />
              <strong>Token ending in:</strong> {deleteTokenId?.slice(-6)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              className="bg-gray-700 border-gray-600 text-gray-200 hover:bg-gray-600"
              disabled={deleting}
              data-testid="delete-token-cancel-btn"
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteToken}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700"
              data-testid="delete-token-confirm-action"
            >
              {deleting ? 'Deleting...' : 'Delete Token'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export default TokensModal;
