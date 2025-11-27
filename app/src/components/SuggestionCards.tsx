import { Card, CardContent } from "@/components/ui/card";

interface SuggestionCardsProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
  disabled?: boolean;
}

const SuggestionCards = ({ suggestions, onSelect, disabled = false }: SuggestionCardsProps) => {
  return (
    <div className="grid gap-3 mb-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
      {suggestions.map((suggestion) => (
        <Card
          key={suggestion}
          className={`bg-gray-800 border-gray-600 ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-purple-500/50 transition-all duration-200 cursor-pointer'}`}
          onClick={disabled ? undefined : () => onSelect(suggestion)}
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-disabled={disabled}
          onKeyDown={(e) => {
            if (disabled) return;
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onSelect(suggestion);
            }
          }}
        >
          <CardContent className="p-3 sm:p-4">
            <div className="text-gray-300 text-xs sm:text-sm text-center line-clamp-2">
              {suggestion}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

export default SuggestionCards;
