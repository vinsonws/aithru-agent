import { Button } from "@/components/ui/button";

export function ClarificationOptions({
  options,
  onSelect,
}: {
  options: string[];
  onSelect: (option: string) => void;
}) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {options.map((option, index) => (
        <Button
          key={index}
          variant="outline"
          size="sm"
          className="h-auto rounded-full px-3 py-1 text-xs"
          onClick={() => onSelect(option)}
        >
          {option}
        </Button>
      ))}
    </div>
  );
}
