import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TimelineSort } from "@/utils/conferenceTimeline";

interface TimelineControlsProps {
  sortBy: TimelineSort;
  onSortChange: (sort: TimelineSort) => void;
  selectedTags: Set<string>;
  tagOptions: string[];
  onToggleTag: (tag: string) => void;
}

const formatTag = (tag: string) =>
  tag
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

const TimelineControls = ({
  sortBy,
  onSortChange,
  selectedTags,
  tagOptions,
  onToggleTag,
}: TimelineControlsProps) => {
  return (
    <div className="space-y-3 rounded-lg bg-white p-4 shadow">
      <div className="w-[220px]">
        <Select value={sortBy} onValueChange={(value) => onSortChange(value as TimelineSort)}>
          <SelectTrigger>
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="upcoming-deadline">Upcoming deadline</SelectItem>
            <SelectItem value="alphabetical">Alphabetical</SelectItem>
            <SelectItem value="conference-date">Conference date</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap gap-2">
        {tagOptions.map((tag) => (
          <Button
            key={tag}
            size="sm"
            variant={selectedTags.has(tag) ? "default" : "secondary"}
            onClick={() => onToggleTag(tag)}
          >
            {formatTag(tag)}
          </Button>
        ))}
      </div>
    </div>
  );
};

export default TimelineControls;
