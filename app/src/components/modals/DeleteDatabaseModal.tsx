import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";

interface DeleteDatabaseModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  databaseName: string;
  onConfirm: () => void;
  isDemo?: boolean;
}

const DeleteDatabaseModal = ({
  open,
  onOpenChange,
  databaseName,
  onConfirm,
  isDemo = false,
}: DeleteDatabaseModalProps) => {
  const handleConfirm = () => {
    onConfirm();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-gray-900 border-gray-700 text-gray-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-500">
            <AlertTriangle className="h-5 w-5" />
            Delete Database
          </DialogTitle>
          <DialogDescription className="text-gray-300">
            {isDemo ? (
              <div className="space-y-2">
                <p className="font-semibold">Demo databases cannot be deleted.</p>
                <p className="text-sm">
                  Demo databases are read-only and shared across all users.
                  Only databases you've created can be deleted.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="font-semibold">
                  Are you sure you want to delete "{databaseName}"?
                </p>
                <p className="text-sm text-gray-400">
                  This action cannot be undone. All data and schema information
                  for this database will be permanently removed.
                </p>
              </div>
            )}
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="bg-gray-800 border-gray-600 text-gray-300 hover:bg-gray-700"
          >
            Cancel
          </Button>
          {!isDemo && (
            <Button
              variant="destructive"
              onClick={handleConfirm}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              Delete Database
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DeleteDatabaseModal;
