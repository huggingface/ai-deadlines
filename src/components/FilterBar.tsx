import { useMemo } from "react";
import conferencesData from "@/utils/conferenceLoader";
import { hasUpcomingDeadlines } from "@/utils/deadlineUtils";
import { X, ChevronRight, Filter } from "lucide-react";
import { getAllCountries } from "@/utils/countryExtractor";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Conference } from "@/types/conference";

interface FilterBarProps {
  selectedTags: Set<string>;
  selectedCountries: Set<string>;
  onTagSelect: (tags: Set<string>) => void;
  onCountrySelect: (countries: Set<string>) => void;
}

const FilterBar = ({ 
  selectedTags = new Set(), 
  selectedCountries = new Set(),
  onTagSelect,
  onCountrySelect
}: FilterBarProps) => {
  const uniqueTags = useMemo(() => {
    const tags = new Set<string>();
    if (Array.isArray(conferencesData)) {
      conferencesData
        .filter(conf => hasUpcomingDeadlines(conf))
        .forEach(conf => {
          if (Array.isArray(conf.tags)) {
            conf.tags.forEach(tag => tags.add(tag));
          }
        });
    }
    return Array.from(tags).map(tag => ({
      id: tag,
      label: tag.split("-").map(word => 
        word.charAt(0).toUpperCase() + word.slice(1)
      ).join(" "),
      description: `${tag} Conferences`
    }));
  }, []);

  const isTagSelected = (tagId: string) => {
    return selectedTags?.has(tagId) ?? false;
  };

  const handleTagChange = (tagId: string) => {
    const newSelectedTags = new Set(selectedTags);
    if (newSelectedTags.has(tagId)) {
      newSelectedTags.delete(tagId);
    } else {
      newSelectedTags.add(tagId);
    }
    onTagSelect(newSelectedTags);
  };

  const clearAllFilters = () => {
    onTagSelect(new Set());
    onCountrySelect(new Set());
  };

  return (
    <div className="bg-white shadow rounded-lg p-4">
      <div className="flex flex-col space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="outline" size="sm" className="h-8 gap-1">
                <Filter className="h-4 w-4" />
                Filter by Tag
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-80 p-4" align="start">
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h4 className="text-sm font-medium text-gray-800">Tags</h4>
                    <ChevronRight className="h-4 w-4 text-gray-500" />
                  </div>
                  <div className="max-h-60 overflow-y-auto space-y-2">
                    {uniqueTags.map(tag => (
                      <div key={tag.id} className="flex items-center space-x-2 hover:bg-gray-50 p-1 rounded">
                        <Checkbox 
                          id={`tag-${tag.id}`}
                          checked={isTagSelected(tag.id)}
                          onCheckedChange={() => handleTagChange(tag.id)}
                        />
                        <label 
                          htmlFor={`tag-${tag.id}`}
                          className="text-sm font-medium text-gray-700 cursor-pointer w-full py-1"
                        >
                          {tag.label}
                        </label>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </PopoverContent>
          </Popover>

          {/* Clear all filters button */}
          {(selectedTags.size > 0 || selectedCountries.size > 0) && (
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={clearAllFilters}
              className="text-neutral-500 hover:text-neutral-700"
            >
              Clear all
            </Button>
          )}
          
          {/* Display selected tags */}
          {Array.from(selectedTags).map(tag => (
            <button
              key={tag}
              className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800 hover:bg-blue-200 font-medium"
              onClick={() => handleTagChange(tag)}
            >
              {tag.split("-").map(word => 
                word.charAt(0).toUpperCase() + word.slice(1)
              ).join(" ")}
              <X className="ml-1 h-3 w-3" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default FilterBar;
