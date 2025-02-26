import Header from "@/components/Header";
import FilterBar from "@/components/FilterBar";
import ConferenceCard from "@/components/ConferenceCard";
import FilterMenu, { getCountry } from "@/components/FilterMenu";
import conferencesData from "@/data/conferences.yml";
import { Conference } from "@/types/conference";
import { useState, useMemo, useEffect } from "react";
import { Switch } from "@/components/ui/switch"
import { parseISO, isValid, isPast } from "date-fns";
import { Button } from "@/components/ui/button";

const Index = () => {
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [showPastConferences, setShowPastConferences] = useState(false);
  const [filterMenuOpen, setFilterMenuOpen] = useState<boolean>(false);
  const [selectedCountries, setSelectedCountries] = useState<Set<string>>(new Set());

  // Memoize selectedCountries to prevent unnecessary re-renders
  const selectedCountriesKey = useMemo(() => 
    JSON.stringify(Array.from(selectedCountries).sort()), 
  [selectedCountries]);


  const filteredConferences = useMemo(() => {
    if (!Array.isArray(conferencesData)) {
      console.error("Conferences data is not an array:", conferencesData);
      return [];
    }

      return conferencesData
        .filter((conf: Conference) => {
      // Filter by deadline (past/future)
      const deadlineDate = conf.deadline && conf.deadline !== 'TBD' ? parseISO(conf.deadline) : null;
      const isUpcoming = !deadlineDate || !isValid(deadlineDate) || !isPast(deadlineDate);
      if (!showPastConferences && !isUpcoming) return false;
  
      // Filter by tags and search query
      const matchesTags = selectedTags.size === 0 || 
        (Array.isArray(conf.tags) && conf.tags.some(tag => selectedTags.has(tag)));
      const matchesSearch = searchQuery === "" || 
        conf.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (conf.full_name && conf.full_name.toLowerCase().includes(searchQuery.toLowerCase()));

      const country = getCountry(conf.place);
      const matchesCountries = selectedCountries.size === 0 || (country && selectedCountries.has(country));
  
      return matchesTags && matchesSearch && matchesCountries;
    })
    .sort((a: Conference, b: Conference) => {
      const dateA = a.deadline && a.deadline !== 'TBD' ? parseISO(a.deadline).getTime() : Infinity;
      const dateB = b.deadline && b.deadline !== 'TBD' ? parseISO(b.deadline).getTime() : Infinity;
      return dateA - dateB;
    });
  }, [selectedTags, searchQuery, showPastConferences, selectedCountriesKey]);
    
  // Update handleTagsChange to handle multiple tags
  const handleTagsChange = (newTags: Set<string>) => {
    setSelectedTags(newTags);
    const searchParams = new URLSearchParams(window.location.search);
    if (newTags.size > 0) {
      searchParams.set('tags', Array.from(newTags).join(','));
    } else {
      searchParams.delete('tags');
    }
    const newUrl = `${window.location.pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    window.history.pushState({}, '', newUrl);
  };

  useEffect(() => {
    const handleUrlChange = (event: CustomEvent) => {
      const { tag } = event.detail;
      // Create new Set with existing tags plus the new one
      const newTags = new Set(selectedTags);
      if (newTags.has(tag)) {
        newTags.delete(tag);
      } else {
        newTags.add(tag);
      }
      handleTagsChange(newTags);
    };

    window.addEventListener('urlchange', handleUrlChange as EventListener);
    
    // Check URL params on mount
    const params = new URLSearchParams(window.location.search);
    const tagsParam = params.get('tags');
    if (tagsParam) {
      setSelectedTags(new Set(tagsParam.split(',')));
    }

    return () => {
      window.removeEventListener('urlchange', handleUrlChange as EventListener);
    };
  }, [selectedTags]); // Add selectedTags as dependency

  if (!Array.isArray(conferencesData)) {
    return <div>Loading conferences...</div>;
  }

  return (
    <div className="min-h-screen bg-neutral-light">
      <Header 
        onSearch={setSearchQuery} 
        showEmptyMessage={selectedTags.size > 0 && filteredConferences.length === 0 && !showPastConferences}
      />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-4 py-4">
          <FilterBar 
            selectedTags={selectedTags}
            onTagSelect={handleTagsChange}
          />
          <div className="flex items-center gap-2">
            <label htmlFor="show-past" className="text-sm text-neutral-600">
              Show past conferences
            </label>
            <Switch
              id="show-past"
              checked={showPastConferences}
              onCheckedChange={setShowPastConferences}
            />
          
          {/* Filter Button */}
          <div className="ml-auto relative">
            <Button
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
              onClick={() => setFilterMenuOpen(!filterMenuOpen)}
            >
              Filter
            </Button>

            {/* Filter Menu */}
            {filterMenuOpen && (
              <FilterMenu
              isOpen={filterMenuOpen}
              onClose={() => setFilterMenuOpen(false)}
              selectedCountries={selectedCountries}
              onCountriesChange={setSelectedCountries}
            />
            )}
          </div>
          </div>   
        </div>
      </div>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredConferences.map((conference: Conference) => (
            <ConferenceCard key={conference.id} {...conference} />
          ))}
        </div>
      </main>
    </div>
  );
};

export default Index;
