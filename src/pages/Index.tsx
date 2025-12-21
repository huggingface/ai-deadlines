import Header from "@/components/Header";
import FilterBar from "@/components/FilterBar";
import ConferenceCard from "@/components/ConferenceCard";
import conferencesData from "@/utils/conferenceLoader";
import { Conference } from "@/types/conference";
import { useState, useMemo, useEffect } from "react";
import { Switch } from "@/components/ui/switch"
import { parseISO, isValid, isPast } from "date-fns";
import { extractCountry } from "@/utils/countryExtractor";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { X, ChevronRight, Filter, Globe } from "lucide-react";
import { getAllCountries } from "@/utils/countryExtractor";
import { getDeadlineInLocalTime } from "@/utils/dateUtils";
import { sortConferencesByDeadline } from "@/utils/conferenceUtils";
import { hasUpcomingDeadlines } from "@/utils/deadlineUtils";

const Index = () => {
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set());
  const [selectedCountries, setSelectedCountries] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [showPastConferences, setShowPastConferences] = useState(false);

  // Dynamically generate category buttons from conference data
  const categoryButtons = useMemo(() => {
    if (!Array.isArray(conferencesData)) return [];
    
    // Count occurrences of each tag
    const tagCounts = new Map<string, number>();
    conferencesData.forEach((conf: Conference) => {
      if (Array.isArray(conf.tags)) {
        conf.tags.forEach(tag => {
          tagCounts.set(tag, (tagCounts.get(tag) || 0) + 1);
        });
      }
    });
    
    // Sort by frequency (most common first) and convert to button format
    return Array.from(tagCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([tag]) => ({
        id: tag,
        label: tag.split("-").map(word => 
          word.charAt(0).toUpperCase() + word.slice(1)
        ).join(" ")
      }));
  }, []);

  const filteredConferences = useMemo(() => {
    if (!Array.isArray(conferencesData)) {
      console.error("Conferences data is not an array:", conferencesData);
      return [];
    }

    const filtered = conferencesData
      .filter((conf: Conference) => {
        // Filter by deadline (past/future) - use new deadline logic
        if (!showPastConferences && !hasUpcomingDeadlines(conf)) return false;

        // Filter by tags
        const matchesTags = selectedTags.size === 0 || 
          (Array.isArray(conf.tags) && conf.tags.some(tag => selectedTags.has(tag)));
        
        // Filter by countries
        const matchesCountry = selectedCountries.size === 0 || 
          (conf.country && selectedCountries.has(conf.country));
        
        // Filter by search query
        const matchesSearch = searchQuery === "" || 
          conf.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (conf.full_name && conf.full_name.toLowerCase().includes(searchQuery.toLowerCase()));
        
        return matchesTags && matchesCountry && matchesSearch;
      });
    
    // Use the proper sorting function that handles both deadline formats
    return sortConferencesByDeadline(filtered);
  }, [selectedTags, selectedCountries, searchQuery, showPastConferences]);

  // Update handleTagsChange to handle multiple tags
  const handleTagsChange = (newTags: Set<string>) => {
    setSelectedTags(newTags);
    const searchParams = new URLSearchParams(window.location.search);
    if (newTags.size > 0) {
      searchParams.set('tags', Array.from(newTags).join(','));
    } else {
      searchParams.delete('tags');
    }
    window.history.replaceState({}, '', `${window.location.pathname}?${searchParams}`);
  };

  const handleCountriesChange = (newCountries: Set<string>) => {
    setSelectedCountries(newCountries);
    const searchParams = new URLSearchParams(window.location.search);
    if (newCountries.size > 0) {
      searchParams.set('countries', Array.from(newCountries).join(','));
    } else {
      searchParams.delete('countries');
    }
    window.history.replaceState({}, '', `${window.location.pathname}?${searchParams}`);
  };

  // Toggle a single tag
  const toggleTag = (tag: string) => {
    const newTags = new Set(selectedTags);
    if (newTags.has(tag)) {
      newTags.delete(tag);
    } else {
      newTags.add(tag);
    }
    handleTagsChange(newTags);
  };

  // Load filters from URL on initial render
  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const tagsParam = searchParams.get('tags');
    const countriesParam = searchParams.get('countries');
    
    if (tagsParam) {
      const tags = tagsParam.split(',');
      setSelectedTags(new Set(tags));
    }
    
    if (countriesParam) {
      const countries = countriesParam.split(',');
      setSelectedCountries(new Set(countries));
    }
  }, []);

  // Listen for URL changes from tag clicks in conference cards
  useEffect(() => {
    const handleUrlChange = () => {
      const searchParams = new URLSearchParams(window.location.search);
      const tagsParam = searchParams.get('tags');
      const countriesParam = searchParams.get('countries');
      
      if (tagsParam) {
        const tags = tagsParam.split(',');
        setSelectedTags(new Set(tags));
      } else {
        setSelectedTags(new Set());
      }
      
      if (countriesParam) {
        const countries = countriesParam.split(',');
        setSelectedCountries(new Set(countries));
      } else {
        setSelectedCountries(new Set());
      }
    };

    window.addEventListener('urlchange', handleUrlChange);
    return () => window.removeEventListener('urlchange', handleUrlChange);
  }, []);

  if (!Array.isArray(conferencesData)) {
    return <div>Loading conferences...</div>;
  }

  return (
    <div className="min-h-screen bg-neutral-light">
      <Header 
        onSearch={setSearchQuery} 
        showEmptyMessage={false}
      />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="space-y-4 py-4">
          {/* Category filter buttons */}
          <div className="bg-white shadow rounded-lg p-4">
            <div className="flex flex-wrap gap-2">
              {categoryButtons.map(category => (
                <button
                  key={category.id}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    selectedTags.has(category.id) 
                      ? 'bg-blue-100 text-blue-800 hover:bg-blue-200' 
                      : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
                  }`}
                  onClick={() => {
                    const newTags = new Set(selectedTags);
                    if (newTags.has(category.id)) {
                      newTags.delete(category.id);
                    } else {
                      newTags.add(category.id);
                    }
                    handleTagsChange(newTags);
                  }}
                >
                  {category.label}
                </button>
              ))}
            </div>
          </div>
          
          {/* Controls row with past conferences toggle and country filter */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 bg-white p-2 rounded-md shadow-sm">
              <label htmlFor="show-past" className="text-sm text-neutral-600">
                Show past conferences
              </label>
              <Switch
                id="show-past"
                checked={showPastConferences}
                onCheckedChange={setShowPastConferences}
              />
            </div>
            
            <div className="flex items-center gap-2 bg-white p-2 rounded-md shadow-sm">
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 gap-1">
                    <Globe className="h-4 w-4" />
                    Filter by Country
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-4 bg-white" align="start">
                  <div className="space-y-4">
                    <div>
                      <div className="mb-4">
                        <h4 className="text-sm font-medium text-gray-800">Country</h4>
                      </div>
                      <div 
                        className="max-h-60 overflow-y-auto space-y-2 bg-white overscroll-contain touch-pan-y" 
                        style={{ WebkitOverflowScrolling: "touch" }}
                      >
                        {getAllCountries(conferencesData as Conference[]).map(country => (
                          <div key={country} className="flex items-center space-x-2 hover:bg-gray-50 p-1 rounded">
                            <Checkbox 
                              id={`country-${country}`}
                              checked={selectedCountries.has(country)}
                              onCheckedChange={() => {
                                const newCountries = new Set(selectedCountries);
                                if (newCountries.has(country)) {
                                  newCountries.delete(country);
                                } else {
                                  newCountries.add(country);
                                }
                                handleCountriesChange(newCountries);
                              }}
                            />
                            <label 
                              htmlFor={`country-${country}`}
                              className="text-sm font-medium text-gray-700 cursor-pointer w-full py-1"
                            >
                              {country}
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
              
              {/* Display selected countries */}
              {Array.from(selectedCountries).map(country => (
                <button
                  key={country}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800 hover:bg-blue-200 font-medium"
                  onClick={() => {
                    const newCountries = new Set(selectedCountries);
                    newCountries.delete(country);
                    handleCountriesChange(newCountries);
                  }}
                >
                  {country}
                  <X className="ml-1 h-3 w-3" />
                </button>
              ))}
              
              {/* Clear all filters button */}
              {(selectedTags.size > 0 || selectedCountries.size > 0) && (
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => {
                    handleTagsChange(new Set());
                    handleCountriesChange(new Set());
                  }}
                  className="text-neutral-500 hover:text-neutral-700"
                >
                  Clear all filters
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {filteredConferences.length === 0 && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-md p-4 mb-6">
            <p className="text-center">
              There are no upcoming conferences for the selected categories - enable "Show past conferences" to see previous ones
            </p>
          </div>
        )}
        
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
